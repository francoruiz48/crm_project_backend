import json
from typing import List, Union, Optional
from fastapi import Body, Depends, HTTPException, Query, Request, UploadFile
from app.controllers.base_controller import BaseController
from app.core.constans import DEFAULT_PAGE_SIZE, PAGE_SIZE_LIMIT
from app.core.security import PermissionChecker, get_current_user
from app.models.lead import Lead
from app.models.lead_field import LeadField
from app.models.lead_field_value import LeadFieldValue
from app.schemas.filter_schema import LeadSearchRequest
from app.schemas.pagination_schema import PaginatedResponse
from app.services.lead_service import LeadService
from app.schemas.lead_schema import LeadCreate, LeadDetailedResponse, LeadResponse
from pydantic import BaseModel, Field

class LeadController(BaseController):
    router_prefix = "/leads"
    service = LeadService
    schema_in = LeadCreate
    schema_out = LeadResponse
    schema_out_detail = LeadDetailedResponse

    relationships = [
        (Lead.field_values, LeadFieldValue.field, LeadField.field_type),
        (Lead.field_values, LeadFieldValue.field, LeadField.campaign)
    ]
    
    enabled_methods = {"GET_ONE", "DELETE"}

    @classmethod
    def get_router(cls):
        # Generamos el router con los métodos base (GET_ONE, POST, etc.)
        router = super().get_router()

        # Preparamos el modelo de respuesta (para Swagger)
        if cls.schema_out_detail:
            ResponseModelItem = Union[cls.schema_out_detail, cls.schema_out]
        else:
            ResponseModelItem = cls.schema_out
            
        ResponseModelPaginated = PaginatedResponse[ResponseModelItem]

        # ---------------------------------------------------------------------
        # HELPER PRIVADO: Parsea Request (JSON o Multipart)
        # ---------------------------------------------------------------------
        async def _parse_hybrid_request(request: Request):
            """
            Detecta si es JSON o Multipart y devuelve (obj_dict, files_map)
            """
            content_type = request.headers.get("content-type", "")
            
            # CASO 1: JSON (Tests y llamadas normales)
            if "application/json" in content_type:
                try:
                    data = await request.json()
                    return data, None # No hay archivos
                except Exception:
                    raise HTTPException(400, "JSON inválido en el cuerpo del request.")

            # CASO 2: Multipart (Subida de archivos)
            elif "multipart/form-data" in content_type:
                form = await request.form()
                
                # A. Extraer JSON
                data_str = form.get("data")
                lead_data = {}
                if data_str:
                    try:
                        lead_data = json.loads(data_str)
                    except Exception as e:
                        raise HTTPException(400, f"JSON Error: {str(e)}")
                
                # B. Extraer Archivos
                files_map = {}
                for key, value in form.items():
                    # --- CAMBIO AQUÍ: Usamos hasattr en lugar de isinstance ---
                    # Verificamos si tiene 'filename', lo cual confirma que es un UploadFile
                    if key.startswith("file_") and hasattr(value, "filename"):
                        try:
                            field_id = int(key.replace("file_", ""))
                            files_map[field_id] = value
                        except ValueError:
                            continue 
                
                return lead_data, files_map

            else:
                raise HTTPException(400, f"Content-Type no soportado: {content_type}")

        @router.post("/search", 
            response_model=ResponseModelPaginated,
            dependencies=cls._get_deps("read")
        )
        def search_leads(
            page: int = Query(1, ge=1),
            page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=PAGE_SIZE_LIMIT),
            search_req: LeadSearchRequest = Body(...),
            detailed: bool = Query(False)
        ):

            total, items_pydantic = cls.service.search(
                page=page,
                page_size=page_size,
                search_req=search_req, 
                detailed=detailed
            )
            
            return PaginatedResponse.create(
                items=items_pydantic,
                total=total,
                page=page,
                page_size=page_size
            )


        @router.get("/", response_model=ResponseModelPaginated,
                dependencies=cls._get_deps("read"))
        def get_all(
            page: int = Query(1, ge=1),
            page_size: int = DEFAULT_PAGE_SIZE,
            only_active: bool = True, 
            detailed: bool = Query(False),
            campaign_id: Optional[int] = Query(None, description="Filtrar por ID de campaña"),
            query: Optional[str] = Query(None, description="Buscar leads")
        ):

            total, items_pydantic = cls.service.get_all(
                    page=page, 
                    page_size=page_size, 
                    only_active=only_active,
                    detailed=detailed,
                    query=query,
                    campaign_id=campaign_id
                )

            return PaginatedResponse.create(
                items=items_pydantic,
                total=total,
                page=page,
                page_size=page_size
            )
   

        @router.post("/", response_model=LeadResponse, dependencies=cls._get_deps("create"))
        async def create_lead(
            request: Request,
            current_user = Depends(get_current_user)
        ):
            # 1. Usamos el helper para obtener datos sin importar el formato
            lead_dict, files_map = await _parse_hybrid_request(request)
            
            # 2. Validamos con Pydantic
            try:
                obj_in = cls.schema_in(**lead_dict)
            except Exception as e:
                # Capturamos error de validación de Pydantic si faltan campos
                raise HTTPException(422, detail=str(e))

            # 3. Llamamos al servicio
            return cls.service.create(obj_in, created_by=current_user.id, files_map=files_map)


        # --- UPDATE HÍBRIDO ---
        @router.put("/{id}", response_model=LeadResponse, dependencies=cls._get_deps("update"))
        async def update_lead(
            id: int,
            request: Request,
            current_user = Depends(get_current_user)
        ):
            # 1. Usamos el helper
            lead_dict, files_map = await _parse_hybrid_request(request)
            
            # 2. Validación parcial para Update
            # Si vino JSON, lo validamos. Si no vino (solo archivos), obj_in es None (parcial)
            obj_in = None
            if lead_dict:
                try:
                    obj_in = cls.schema_in(**lead_dict)
                except Exception as e:
                    raise HTTPException(422, detail=str(e))
            
            # Si no hay nada, error
            if not obj_in and not files_map:
                raise HTTPException(400, "Debe enviar datos JSON o archivos para actualizar.")

            # 3. Llamamos al servicio
            return cls.service.update(id, obj_in, files_map=files_map)

    
        @router.post("/simulate", response_model=LeadResponse) # O usa un schema específico si prefieres
        async def simulate_lead_creation(
            request: Request,
            current_user = Depends(get_current_user)
        ):
            """
            Simula la creación de un lead para probar validaciones y campos calculados.
            No guarda nada en la base de datos.
            """
            # 1. Parsing (igual que create)
            lead_dict, files_map = await _parse_hybrid_request(request)
            
            try:
                obj_in = cls.schema_in(**lead_dict)
            except Exception as e:
                raise HTTPException(422, detail=str(e))

            # 2. Llamada a Servicio de Simulación
            result = cls.service.simulate_create(obj_in, created_by=current_user.id, files_map=files_map)
            return result
        
        class ChangeStateRequest(BaseModel):
            new_state_id: int = Field(gt=0)
            notes: str = None

        @router.post("/{id}/change_state", response_model=ResponseModelItem, dependencies=cls._get_deps("update"))
        async def change_lead_state(
            id: int,
            payload: ChangeStateRequest = Body(...),
            current_user = Depends(get_current_user)
        ):
            return cls.service.change_state(
                obj_id=id, 
                new_state_id=payload.new_state_id, 
                notes=payload.notes, 
                user_id=current_user.id
            )
        
        return router

router = LeadController.get_router()