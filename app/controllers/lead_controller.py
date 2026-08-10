import json
from typing import List, Union, Optional
from fastapi import Body, Depends, HTTPException, Query, Request
from app.controllers.base_controller import BaseController
from app.core.constans import DEFAULT_PAGE_SIZE, PAGE_SIZE_LIMIT
from app.core.security import get_current_user_roles
from app.models.lead import Lead
from app.models.lead_field import LeadField
from app.models.lead_field_value import LeadFieldValue
from app.schemas.filter_schema import LeadSearchRequest
from app.schemas.pagination_schema import PaginatedResponse
from app.services.lead_service import LeadService
from app.schemas.lead_schema import LeadCreate, LeadDetailedResponse, LeadResponse, LeadUpdate
from pydantic import BaseModel, Field
from app.schemas.team_member_schema import BulkAssignRequest

class LeadController(BaseController):
    router_prefix = "/leads"
    service = LeadService
    schema_in = LeadCreate
    schema_update = LeadUpdate
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
                    return data, None, None # No hay archivos
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
                avatar_file = None
                for key, value in form.items():
                    # Verificamos si tiene 'filename', lo cual confirma que es un UploadFile
                    if key.startswith("file_") and hasattr(value, "filename"):
                        try:
                            field_id = int(key.replace("file_", ""))
                            files_map[field_id] = value
                        except ValueError:
                            continue 
                    elif key == "avatar_file":
                        avatar_file = value
                
                return lead_data, files_map, avatar_file

            else:
                raise HTTPException(400, f"Content-Type no soportado: {content_type}")

        @router.post("/search", 
            response_model=ResponseModelPaginated,
            dependencies=cls._get_deps("read")
        )
        def search_leads(
            user_context = Depends(get_current_user_roles),
            page: int = Query(1, ge=1),
            #ge=0 (no ge=1): page_size=0 es la convención del resto de la app para "traer todo sin
            #paginar" (ver base_repository._paginate, que ya trata page_size<=0 como sin límite).
            #Este controller define su propia validación en vez de heredar la de BaseController,
            #así que había quedado más estricto que el resto y rechazaba ese valor con 422.
            page_size: int = Query(DEFAULT_PAGE_SIZE, ge=0, le=PAGE_SIZE_LIMIT),
            search_req: LeadSearchRequest = Body(...),
            detailed: bool = Query(False),
            only_active: bool = Query(True),
            campaign_id: Optional[str] = Query(None, description="Filtrar por UUID público de campaña"),
            query: Optional[str] = Query(None, description="Buscar leads (texto libre)"),
            order_by: str = Query(None, description="Campo por el cual ordenar"),
            ascending: bool = Query(True, description="Orden ascendente (true) o descendente (false)")
        ):

            total, items_pydantic = cls.service.search(
                user_context=user_context,
                page=page,
                page_size=page_size,
                search_req=search_req,
                detailed=detailed,
                order_by=order_by,
                ascending=ascending,
                only_active=only_active,
                campaign_id=campaign_id,
                query=query
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
            user_context = Depends(get_current_user_roles),
            page: int = Query(1, ge=1),
            #ge=0 (no ge=1): page_size=0 es la convención del resto de la app para "traer todo sin
            #paginar" (ver base_repository._paginate, que ya trata page_size<=0 como sin límite).
            #Este controller define su propia validación en vez de heredar la de BaseController,
            #así que había quedado más estricto que el resto y rechazaba ese valor con 422.
            page_size: int = Query(DEFAULT_PAGE_SIZE, ge=0, le=PAGE_SIZE_LIMIT),
            only_active: bool = True, 
            detailed: bool = Query(False),
            campaign_id: Optional[str] = Query(None, description="Filtrar por UUID público de campaña"),
            query: Optional[str] = Query(None, description="Buscar leads"),
            order_by: str = Query(None, description="Campo por el cual ordenar"), 
            ascending: bool = Query(True, description="Orden ascendente (true) o descendente (false)"),
        ):
            

            total, items_pydantic = cls.service.get_all(
                    user_context=user_context,
                    page=page, 
                    page_size=page_size, 
                    only_active=only_active,
                    detailed=detailed,
                    query=query,
                    campaign_id=campaign_id,
                    order_by=order_by,
                    ascending=ascending
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
            user_context = Depends(get_current_user_roles)
        ):
            # 1. Usamos el helper para obtener datos sin importar el formato
            lead_dict, files_map, avatar_file = await _parse_hybrid_request(request)
            
            # 2. Validamos con Pydantic
            try:
                obj_in = cls.schema_in(**lead_dict)
            except Exception as e:
                # Capturamos error de validación de Pydantic si faltan campos
                raise HTTPException(422, detail=str(e))

            # 3. Llamamos al servicio
            return cls.service.create(obj_in, user_context=user_context, files_map=files_map, avatar_file=avatar_file)


        # --- UPDATE HÍBRIDO ---
        @router.put("/{id}", response_model=LeadResponse, dependencies=cls._get_deps("update"))
        async def update_lead(
            id: str,
            request: Request,
            user_context = Depends(get_current_user_roles)
        ):
            # 1. Usamos el helper
            lead_dict, files_map, avatar_file = await _parse_hybrid_request(request)
            
            # 2. Validación parcial para Update
            # Si vino JSON, lo validamos. Si no vino (solo archivos), obj_in es None (parcial)
            obj_in = None
            if lead_dict:
                try:
                    obj_in = cls.schema_update(**lead_dict)
                except Exception as e:
                    raise HTTPException(422, detail=str(e))
            
            # Si no hay nada, error
            if not obj_in and not files_map:
                raise HTTPException(400, "Debe enviar datos JSON o archivos para actualizar.")

            # 3. Llamamos al servicio
            return cls.service.update(id, obj_in, files_map=files_map, user_context=user_context, avatar_file=avatar_file)

    
        @router.post("/simulate", response_model=LeadResponse, dependencies=cls._get_deps("create"))
        async def simulate_lead_creation(
            request: Request,
            user_context = Depends(get_current_user_roles)
        ):
            """
            Simula la creación de un lead para probar validaciones y campos calculados.
            No guarda nada en la base de datos.
            """
            # 1. Parsing (igual que create)
            lead_dict, files_map, _ = await _parse_hybrid_request(request)
            
            try:
                obj_in = cls.schema_in(**lead_dict)
            except Exception as e:
                raise HTTPException(422, detail=str(e))

            # 2. Llamada a Servicio de Simulación
            result = cls.service.simulate_create(obj_in, user_context=user_context, files_map=files_map)
            return result
        
        class ChangeStateRequest(BaseModel):
            new_state_id: str
            notes: str = None

        @router.post("/{id}/change_state", response_model=ResponseModelItem, dependencies=cls._get_deps("update"))
        async def change_lead_state(
            id: str,
            payload: ChangeStateRequest = Body(...),
            user_context = Depends(get_current_user_roles)
        ):
            return cls.service.change_state(
                obj_id=id,
                new_state_id=payload.new_state_id,
                notes=payload.notes,
                user_context=user_context
            )

        class ChangeContactStateRequest(BaseModel):
            new_contact_state_id: str
            notes: str = None

        @router.post("/{id}/change_contact_state", response_model=ResponseModelItem, dependencies=cls._get_deps("update"))
        async def change_lead_contact_state(
            id: str,
            payload: ChangeContactStateRequest = Body(...),
            user_context = Depends(get_current_user_roles)
        ):
            return cls.service.change_contact_state(
                obj_id=id,
                new_contact_state_id=payload.new_contact_state_id,
                notes=payload.notes,
                user_context=user_context
            )


        @router.patch("/bulk-assign", response_model=List[ResponseModelItem], dependencies=cls._get_deps("update"))
        async def bulk_assign_leads(
            payload: BulkAssignRequest = Body(...),
            user_context = Depends(get_current_user_roles)
        ):
            """
            Reasignación masiva de Leads a un Equipo y/o Usuario. También permite desasignar
            (clear_team/clear_user), ya que target_team_id/target_user_id en None solo significa
            "no tocar este campo".
            """
            # Validamos que al menos envíen un destino o pidan desasignar algo
            if not payload.target_team_id and not payload.target_user_id and not payload.clear_team and not payload.clear_user:
                raise HTTPException(
                    status_code=400,
                    detail="Debe especificar al menos un equipo destino, un usuario destino, o desasignar alguno de los dos."
                )

            # No tiene sentido pedir "asignar a X" y "desasignar" del mismo campo a la vez
            if payload.target_team_id and payload.clear_team:
                raise HTTPException(status_code=400, detail="No se puede asignar y desasignar el equipo al mismo tiempo.")
            if payload.target_user_id and payload.clear_user:
                raise HTTPException(status_code=400, detail="No se puede asignar y desasignar el usuario al mismo tiempo.")

            return cls.service.bulk_assign(
                lead_ids=payload.lead_ids,
                target_team_id=payload.target_team_id,
                target_user_id=payload.target_user_id,
                clear_team=payload.clear_team,
                clear_user=payload.clear_user,
                user_context=user_context
            )
        
        return router

router = LeadController.get_router()
