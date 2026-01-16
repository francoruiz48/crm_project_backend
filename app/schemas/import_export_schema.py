from pydantic import BaseModel
from typing import List, Dict

class ImportHeadersResponse(BaseModel):
    headers: List[str]

class ImportResultResponse(BaseModel):
    total_rows: int
    imported: int
    failed: int
    errors: List[str] = []