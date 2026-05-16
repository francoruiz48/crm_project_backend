from typing import Optional, Tuple
import pandas as pd
import io
import json
import re
import unicodedata
from fastapi import UploadFile, HTTPException
from sqlalchemy.orm import Session
from app.db.repository.lead_field_repository import LeadFieldRepository
from app.db.repository.lead_repository import LeadRepository
from app.db.repository.campaign_repository import CampaignRepository
from app.db.repository.nomenclator_item_repository import NomenclatorItemRepository
from app.services.lead_service import LeadService
from app.schemas.lead_schema import LeadCreate, LeadFieldValueCreate
from app.models.lead import Lead
from app.models.lead_field_value import LeadFieldValue
from app.core.security import UserContext

class LeadImportExportService:

    @classmethod
    def get_excel_headers(cls, file: UploadFile) -> list[str]:
        try:
            contents = file.file.read()
            df = pd.read_excel(io.BytesIO(contents), nrows=0) 
            file.file.seek(0)
            return df.columns.tolist()
        except Exception as e:
            raise HTTPException(400, f"Error al leer archivo Excel: {str(e)}")

    # -------------------------------------------------------------------------
    # HELPERS DE IMPORTACIÓN
    # -------------------------------------------------------------------------

    @classmethod
    def _build_nomenclator_cache(cls, db: Session, campaign_fields: list, user_context: Optional[UserContext] = None) -> dict:
        """
        Crea un mapa: {(nomenclator_id, "valor_texto_lower"): item_id}
        """
        cache = {}
        nomenclator_fields = [f for f in campaign_fields if f.nomenclator_id is not None]
        nom_ids = set(f.nomenclator_id for f in nomenclator_fields)
        
        if not nom_ids: return cache

        for nid in nom_ids:
            # INYECTADO: user_context a la búsqueda de nomencladores
            items = NomenclatorItemRepository.get_all(db, nomenclator_id=nid, page=0, user_context=user_context)
            for item in items:
                key = (item.nomenclator_id, str(item.value).strip().lower())
                cache[key] = item.id
        return cache

    @classmethod
    def _resolve_related_leads(cls, db: Session, field_def, raw_data_map: dict, user_context: Optional[UserContext] = None) -> list[int]:
        if not raw_data_map:
            return []

        target_campaign_id = field_def.related_campaign_id
        # INYECTADO: user_context para respetar permisos cross-campaign
        target_fields = LeadFieldRepository.get_all(db, campaign_id=target_campaign_id, only_active=True, user_context=user_context)
        
        primary_defs = {f.name: f for f in target_fields if f.is_primary}
        
        if not primary_defs:
            return []

        split_values = {
            k: [x.strip() for x in str(v).split(',')] 
            for k, v in raw_data_map.items()
        }
        
        lengths = [len(l) for l in split_values.values()]
        max_len = max(lengths) if lengths else 0
        
        if any(l != max_len for l in lengths):
            raise ValueError(f"Campo '{field_def.name}': Cantidad desigual de valores en claves primarias.")

        resolved_ids = []

        for i in range(max_len):
            criteria = {}
            criteria_repr = []
            valid_criteria = True

            for target_fname, val_list in split_values.items():
                val = val_list[i]
                target_field_def = primary_defs.get(target_fname)
                
                if not target_field_def:
                    continue 
                if not val: 
                    valid_criteria = False
                    break 
                
                criteria[target_field_def.id] = val
                criteria_repr.append(f"{target_fname}={val}")

            if not valid_criteria or not criteria:
                continue 

            candidates_query = db.query(Lead.id).filter(Lead.campaign_id == target_campaign_id, Lead.active.is_(True))
            
            for fid, search_val in criteria.items():
                subquery = db.query(LeadFieldValue.lead_id).filter(
                    LeadFieldValue.field_id == fid,
                    LeadFieldValue.value == str(search_val) 
                )
                candidates_query = candidates_query.filter(Lead.id.in_(subquery))

            found_lead_id = candidates_query.first() 

            if found_lead_id:
                resolved_ids.append(found_lead_id[0])
            else:
                raise ValueError(f"Campo '{field_def.name}': No se encontró el lead relacionado con ({', '.join(criteria_repr)}) en la campaña destino.")

        return resolved_ids

    # -------------------------------------------------------------------------
    # MÉTODO PRINCIPAL DE IMPORTACIÓN
    # -------------------------------------------------------------------------
    @classmethod
    def import_leads(cls, db: Session, file: UploadFile, mapping_json: str, campaign_id: int, user_context: Optional[UserContext] = None):
        # --- NUEVA VALIDACIÓN: Verificar campaña ANTES de procesar ---
        campaign = CampaignRepository.get_by_id(db, campaign_id, user_context=user_context, only_active=True)
        if not campaign:
            raise HTTPException(404, "Campaña no encontrada o no tienes acceso.")

        try:
            mapping = json.loads(mapping_json) 
        except json.JSONDecodeError:
            raise HTTPException(400, "El mapeo no es un JSON válido.")

        try:
            contents = file.file.read()
            df = pd.read_excel(io.BytesIO(contents))
            df = df.fillna("") 
            df = df.astype(str) 
            df = df.replace("nan", "") 
        except Exception as e:
            raise HTTPException(400, f"Error al procesar Excel: {str(e)}")

        # 1. Preparar Definiciones (Ahora seguro de que la campaña existe)
        campaign_fields = LeadFieldRepository.get_all(db, campaign_id=campaign_id, only_active=True, user_context=user_context)
        field_def_map = {f.name: f for f in campaign_fields}
        
        # 2. Analizar el Mapeo
        fields_to_process = {}
        for excel_col, map_target in mapping.items():
            if excel_col not in df.columns:
                raise HTTPException(400, f"La columna '{excel_col}' no existe en el Excel.")
            
            if "." in map_target:
                parts = map_target.split(".")
                field_name = parts[0]
                target_attr = parts[1]
                
                if field_name not in field_def_map: continue 
                if field_name not in fields_to_process: fields_to_process[field_name] = {"def": field_def_map[field_name], "cols": {}}
                
                fields_to_process[field_name]["cols"][target_attr] = excel_col
            else:
                field_name = map_target
                if field_name not in field_def_map: continue
                if field_name not in fields_to_process: fields_to_process[field_name] = {"def": field_def_map[field_name], "cols": {}}
                
                fields_to_process[field_name]["cols"]["__value__"] = excel_col

        # 3. Cache de Nomencladores (Pasamos el user_context)
        nom_cache = cls._build_nomenclator_cache(db, campaign_fields, user_context)

        # 4. Iterar Filas
        success_count = 0
        errors = []

        for index, row in df.iterrows():
            row_idx = index + 2 
            try:
                lead_values = []
                for field_name, info in fields_to_process.items():
                    field_def = info["def"]
                    col_map = info["cols"] 
                    
                    if field_def.field_type_code in ["CALCULATED", "FILE"]:
                        continue 

                    final_val = None

                    if field_def.nomenclator_id is not None:
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

                    elif field_def.field_type_code == "LEAD":
                        raw_lookup = {}
                        for target_attr, excel_col in col_map.items():
                            if target_attr == "__value__": continue 
                            raw_lookup[target_attr] = row[excel_col]
                        
                        if raw_lookup:
                            # Pasamos el user_context para la búsqueda relacional
                            final_val = cls._resolve_related_leads(db, field_def, raw_lookup, user_context)

                    else:
                        if "__value__" in col_map:
                            val = row[col_map["__value__"]].strip()
                            if val:
                                final_val = val

                    if final_val is not None:
                         lead_values.append(LeadFieldValueCreate(
                            field_id=field_def.id,
                            value=final_val 
                        ))

                if not lead_values: continue

                payload = LeadCreate(campaign_id=campaign_id, values=lead_values)
                LeadService.create(payload, user_context=user_context)
                success_count += 1

            except Exception as e:
                errors.append(f"Fila {row_idx}: {str(e)}")

        return {
            "total_rows": len(df),
            "imported": success_count,
            "failed": len(errors),
            "errors": errors[:20] 
        }

    # -------------------------------------------------------------------------
    # EXPORTACIÓN
    # -------------------------------------------------------------------------
    @classmethod
    def export_leads(cls, db: Session, campaign_id: int, user_context: Optional[UserContext] = None) -> Tuple[io.BytesIO, str]:
        campaign = CampaignRepository.get_by_id(db, campaign_id, user_context=user_context, only_active=True)
        if not campaign:
            raise HTTPException(404, "Campaña no encontrada o acceso denegado.")

        fields = LeadFieldRepository.get_all(db, campaign_id=campaign_id, only_active=True, user_context=user_context)
        fields.sort(key=lambda x: x.order)
        
        field_map = {f.id: f.name for f in fields}
        columns = [f.name for f in fields]

        leads = LeadRepository.get_all(db, user_context=user_context, campaign_id=campaign_id, only_active=True, page=0, page_size=0)

        data = []
        for lead in leads:
            row = {}
            for col in columns:
                row[col] = ""
            
            for fv in lead.field_values:
                col_name = field_map.get(fv.field_id)
                if col_name:
                    val = fv.value
                    if hasattr(fv, 'nomenclator_items') and fv.nomenclator_items:
                        val = ", ".join([item.value for item in fv.nomenclator_items])
                    
                    row[col_name] = val
            
            data.append(row)

        df = pd.DataFrame(data, columns=columns)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Leads')
        
        output.seek(0)
        
        # 1. Normalizar: Quita tildes y transforma 'ñ' en 'n'
        normalized_name = unicodedata.normalize('NFKD', campaign.name).encode('ASCII', 'ignore').decode('utf-8')
        
        # 2. Reemplazar espacios por guiones bajos para que sea legible
        normalized_name = normalized_name.replace(' ', '_')
        
        # 3. Limpiar cualquier otro símbolo raro que haya quedado
        safe_campaign_name = re.sub(r'[^a-zA-Z0-9_\-]', '', normalized_name)
        
        # Devolvemos el archivo Y el nombre seguro de la campaña
        return output, safe_campaign_name