import pandas as pd
import io
import json
from fastapi import UploadFile, HTTPException
from sqlalchemy.orm import Session
from app.db.repository.lead_field_repository import LeadFieldRepository
from app.db.repository.lead_repository import LeadRepository
from app.db.repository.nomenclator_item_repository import NomenclatorItemRepository
from app.services.lead_service import LeadService
from app.schemas.lead_schema import LeadCreate, LeadFieldValueCreate
from app.models.lead import Lead
from app.models.lead_field_value import LeadFieldValue

class LeadImportExportService:

    @classmethod
    def get_excel_headers(cls, file: UploadFile) -> list[str]:
        try:
            contents = file.file.read()
            # Leemos solo headers, todo como string para evitar problemas de formato
            df = pd.read_excel(io.BytesIO(contents), nrows=0) 
            file.file.seek(0)
            return df.columns.tolist()
        except Exception as e:
            raise HTTPException(400, f"Error al leer archivo Excel: {str(e)}")

    # -------------------------------------------------------------------------
    # HELPERS DE IMPORTACIÓN
    # -------------------------------------------------------------------------

    @classmethod
    def _build_nomenclator_cache(cls, db: Session, campaign_fields: list) -> dict:
        """
        Crea un mapa: {(nomenclator_id, "valor_texto_lower"): item_id}
        """
        cache = {}
        nomenclator_fields = [f for f in campaign_fields if f.nomenclator_id is not None]
        nom_ids = set(f.nomenclator_id for f in nomenclator_fields)
        
        if not nom_ids: return cache

        # Traemos todos los items de golpe
        # Optimización: Query directa a la tabla de items filtrando por nomenclator_id IN (...)
        # Aquí usamos el repo por simplicidad, idealmente sería una query batch.
        for nid in nom_ids:
            items = NomenclatorItemRepository.get_all(db, nomenclator_id=nid, page=0)
            for item in items:
                # Normalizamos a minúsculas y sin espacios
                key = (item.nomenclator_id, str(item.value).strip().lower())
                cache[key] = item.id
        return cache

    @classmethod
    def _resolve_related_leads(cls, db: Session, field_def, raw_data_map: dict) -> list[int]:
        """
        Busca leads en la campaña destino usando claves primarias compuestas.
        raw_data_map: Diccionario { 'TargetFieldName': 'ValorExcel', ... } 
                      Ej: {'DNI': '123, 456', 'Email': 'a@a.com, b@b.com'}
        
        Retorna: Lista de IDs de leads encontrados.
        Lanza: ValueError con detalle si no encuentra alguno.
        """
        if not raw_data_map:
            return []

        # 1. Obtener campos PRIMARY de la campaña destino
        target_campaign_id = field_def.related_campaign_id
        target_fields = LeadFieldRepository.get_all(db, campaign_id=target_campaign_id, only_active=True)
        
        # Filtramos los que son is_primary
        primary_defs = {f.name: f for f in target_fields if f.is_primary}
        
        # SI LA CAMPAÑA DESTINO NO TIENE PRIMARY KEYS, SE IGNORA (Regla de negocio)
        if not primary_defs:
            return []

        # 2. Normalizar entradas (Split por comas para soportar múltiples relaciones)
        # Transformamos {'DNI': '1, 2', 'Email': 'a, b'} -> [{'DNI': '1', 'Email': 'a'}, {'DNI': '2', 'Email': 'b'}]
        
        # Determinamos la longitud máxima de listas (cantidad de relacionados en esta fila)
        # Separamos por coma y limpiamos espacios
        split_values = {
            k: [x.strip() for x in str(v).split(',')] 
            for k, v in raw_data_map.items()
        }
        
        # Validar consistencia de longitud (Si pongo 2 DNIs debo poner 2 Emails)
        lengths = [len(l) for l in split_values.values()]
        max_len = max(lengths) if lengths else 0
        
        # Rellenamos con el último valor o vacío si faltan (o lanzamos error estricto)
        # Aquí asumimos consistencia estricta por seguridad
        if any(l != max_len for l in lengths):
            raise ValueError(f"Campo '{field_def.name}': Cantidad desigual de valores en las columnas de claves primarias. Verifica las comas.")

        resolved_ids = []

        # 3. Buscar Lead por Lead
        for i in range(max_len):
            criteria = {} # {field_id: valor_buscado}
            criteria_repr = [] # Para el mensaje de error

            valid_criteria = True

            for target_fname, val_list in split_values.items():
                val = val_list[i]
                target_field_def = primary_defs.get(target_fname)
                
                # Si el usuario mapeó una columna que NO es primary en el destino, se ignora o error?
                # Asumimos que el mapeo es correcto, si no está en primary_defs no podemos buscar por ahí.
                if not target_field_def:
                    continue # O lanzar error "El campo X no es clave primaria en destino"
                
                if not val: 
                    valid_criteria = False
                    break # Clave vacía, saltar
                
                criteria[target_field_def.id] = val
                criteria_repr.append(f"{target_fname}={val}")

            if not valid_criteria or not criteria:
                continue # No hay datos suficientes para buscar este lead

            # BUSQUEDA EN DB
            # Buscamos un lead en target_campaign_id que cumpla TODAS las condiciones
            # Esto es complejo en EAV. Hacemos una intersección de IDs.
            
            # Query base: IDs de la campaña destino
            candidates_query = db.query(Lead.id).filter(Lead.campaign_id == target_campaign_id, Lead.active.is_(True))
            
            for fid, search_val in criteria.items():
                # Intersectamos con leads que tengan ese valor en ese campo
                # Nota: Usamos ilike para texto, o cast para otros. Asumimos texto/exacto por ahora.
                subquery = db.query(LeadFieldValue.lead_id).filter(
                    LeadFieldValue.field_id == fid,
                    LeadFieldValue.value == str(search_val) # Comparación string exacta (o ilike si prefieres laxo)
                )
                candidates_query = candidates_query.filter(Lead.id.in_(subquery))

            found_lead_id = candidates_query.first() # Scalar subquery or first result

            if found_lead_id:
                resolved_ids.append(found_lead_id[0])
            else:
                # REGLA: Si no existe, error específico.
                raise ValueError(f"Campo '{field_def.name}': No se encontró el lead relacionado con ({', '.join(criteria_repr)}) en la campaña destino.")

        return resolved_ids

    # -------------------------------------------------------------------------
    # MÉTODO PRINCIPAL
    # -------------------------------------------------------------------------
    @classmethod
    def import_leads(cls, db: Session, file: UploadFile, mapping_json: str, campaign_id: int, user_id: int):
        try:
            mapping = json.loads(mapping_json) # {"Header": "Field"} o {"Header": "Field.TargetAttr"}
        except json.JSONDecodeError:
            raise HTTPException(400, "El mapeo no es un JSON válido.")

        try:
            contents = file.file.read()
            df = pd.read_excel(io.BytesIO(contents))
            df = df.fillna("") # Strings vacíos
            # Forzamos todo a string para procesar comas y textos
            df = df.astype(str) 
            # Reemplazar "nan" literal de pandas string conversion
            df = df.replace("nan", "") 
        except Exception as e:
            raise HTTPException(400, f"Error al procesar Excel: {str(e)}")

        # 1. Preparar Definiciones
        campaign_fields = LeadFieldRepository.get_all(db, campaign_id=campaign_id, only_active=True)
        # Mapa: "NombreCampo" -> Objeto Field
        field_def_map = {f.name: f for f in campaign_fields}
        
        # 2. Analizar el Mapeo (Detectar campos simples vs complejos)
        # Estructura: row_processors[field_name] = [ {type: 'simple', col: 'A'}, {type: 'complex', attr: 'DNI', col: 'B'} ]
        fields_to_process = {}
        
        for excel_col, map_target in mapping.items():
            if excel_col not in df.columns:
                raise HTTPException(400, f"La columna '{excel_col}' no existe en el Excel.")
            
            # Detectar Notación de Punto: "Socio.DNI"
            if "." in map_target:
                parts = map_target.split(".")
                field_name = parts[0]
                target_attr = parts[1]
                
                if field_name not in field_def_map: continue # Campo no existe, ignorar o error
                
                if field_name not in fields_to_process: fields_to_process[field_name] = {"def": field_def_map[field_name], "cols": {}}
                
                # Guardamos: Para el campo "Socio", el atributo "DNI" viene de la columna "excel_col"
                fields_to_process[field_name]["cols"][target_attr] = excel_col
                
            else:
                # Campo Simple: "Nombre"
                field_name = map_target
                if field_name not in field_def_map: continue
                
                if field_name not in fields_to_process: fields_to_process[field_name] = {"def": field_def_map[field_name], "cols": {}}
                
                # Guardamos: Para el campo "Nombre", el valor 'raw' viene de "excel_col"
                fields_to_process[field_name]["cols"]["__value__"] = excel_col

        # 3. Cache de Nomencladores
        nom_cache = cls._build_nomenclator_cache(db, campaign_fields)

        # 4. Iterar Filas
        success_count = 0
        errors = []

        for index, row in df.iterrows():
            row_idx = index + 2 # Fila Excel (Header es 1)
            try:
                lead_values = []
                
                for field_name, info in fields_to_process.items():
                    field_def = info["def"]
                    col_map = info["cols"] # {'__value__': 'ColA'} o {'DNI': 'ColB', 'Email': 'ColC'}
                    
                    # --- CASO 1: CAMPOS CALCULADOS & FILES ---
                    if field_def.field_type_code in ["CALCULATED", "FILE"]:
                        continue # Se ignoran

                    final_val = None

                    # --- CASO 2: NOMENCLADORES (Validación Estricta) ---
                    if field_def.nomenclator_id is not None:
                        # Asumimos que viene por '__value__' (mapeo simple)
                        if "__value__" in col_map:
                            raw_val = row[col_map["__value__"]]
                            if not raw_val.strip(): continue

                            raw_items = [x.strip() for x in raw_val.split(',')]
                            resolved_ids = []
                            for txt in raw_items:
                                key = (field_def.nomenclator_id, txt.lower())
                                if key not in nom_cache:
                                    raise ValueError(f"Campo '{field_name}': El valor '{txt}' no existe en el nomenclador.")
                                resolved_ids.append(nom_cache[key])
                            
                            final_val = resolved_ids

                    # --- CASO 3: LEADS RELACIONADOS (Búsqueda por PK) ---
                    elif field_def.field_type_code == "LEAD":
                        # Recolectamos los valores crudos para la búsqueda
                        # raw_lookup = {'DNI': '111', 'Email': 'a@a'}
                        raw_lookup = {}
                        for target_attr, excel_col in col_map.items():
                            if target_attr == "__value__": continue # Ignorar mapeos directos incorrectos en leads
                            raw_lookup[target_attr] = row[excel_col]
                        
                        if raw_lookup:
                            # Delegamos la búsqueda compleja
                            final_val = cls._resolve_related_leads(db, field_def, raw_lookup)
                            # Si vuelve lista vacía (porque no había configuración primary), final_val será [] y LeadService lo guardará vacío (correcto).

                    # --- CASO 4: SIMPLES (String, Int, Date) ---
                    else:
                        if "__value__" in col_map:
                            val = row[col_map["__value__"]].strip()
                            if val:
                                final_val = val

                    # Agregar al payload si hay valor
                    if final_val is not None:
                         lead_values.append(LeadFieldValueCreate(
                            field_id=field_def.id,
                            value=final_val 
                        ))

                if not lead_values: continue

                # CREACIÓN (LeadService se encarga de validaciones de tipo, required, masks)
                payload = LeadCreate(campaign_id=campaign_id, values=lead_values)
                LeadService.create(payload, created_by=user_id)
                success_count += 1

            except Exception as e:
                # Capturamos el error específico y lo reportamos limpio
                errors.append(f"Fila {row_idx}: {str(e)}")

        return {
            "total_rows": len(df),
            "imported": success_count,
            "failed": len(errors),
            "errors": errors[:20] # Limite de errores
        }

    @classmethod
    def export_leads(cls, db: Session, campaign_id: int) -> io.BytesIO:
        """
        Genera un Excel con todos los leads de la campaña.
        Columnas = Nombres de los campos.
        Filas = Leads.
        """
        # 1. Obtener campos (Columnas)
        fields = LeadFieldRepository.get_all(db, campaign_id=campaign_id, only_active=True)
        # Ordenamos por 'order' para que el Excel salga ordenado
        fields.sort(key=lambda x: x.order)
        
        field_map = {f.id: f.name for f in fields}
        columns = [f.name for f in fields]

        # 2. Obtener Leads (Filas)
        # Usamos get_all sin paginación (cuidado con volumen masivo)
        leads = LeadRepository.get_all(db, campaign_id=campaign_id, only_active=True, page=0, page_size=0)

        # 3. Construir Dataset
        data = []
        for lead in leads:
            row = {}
            # Por defecto llenamos todo con vacío
            for col in columns:
                row[col] = ""
            
            # Llenamos con los valores reales
            for fv in lead.field_values:
                col_name = field_map.get(fv.field_id)
                if col_name:
                    # Lógica simple para extraer el valor visible
                    val = fv.value
                    
                    # Si es nomenclator o related, deberíamos procesarlo para que sea legible
                    # Por ahora exportamos el valor crudo o procesado básico
                    if hasattr(fv, 'nomenclator_items') and fv.nomenclator_items:
                        val = ", ".join([item.value for item in fv.nomenclator_items])
                    
                    row[col_name] = val
            
            data.append(row)

        # 4. Crear DataFrame y Excel
        df = pd.DataFrame(data, columns=columns)
        
        output = io.BytesIO()
        # Usamos el engine 'openpyxl'
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Leads')
        
        output.seek(0)
        return output