from contextvars import ContextVar
from typing import Optional

# Variable global segura para la petición asíncrona actual
TENANT_ORG_ID: ContextVar[Optional[int]] = ContextVar("tenant_org_id", default=None)