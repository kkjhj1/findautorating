from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, ConfigDict

class JobRunRequest(BaseModel):
    execution_type: str = "MANUAL_ALL" # MANUAL_ALL, MANUAL_SELECT
    institution_ids: Optional[List[str]] = None

class JobResponse(BaseModel):
    job_id: str
    execution_type: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    total_count: int
    success_count: int
    no_rating_count: int
    error_count: int
    manual_check_count: int
    status: str

    model_config = ConfigDict(from_attributes=True)

class LogResponse(BaseModel):
    log_id: int
    job_id: str
    institution_id: str
    institution_name: Optional[str] = None
    agency_code: str
    status: str
    message: Optional[str] = None
    source_url: Optional[str] = None
    started_at: datetime
    finished_at: datetime

    model_config = ConfigDict(from_attributes=True)
