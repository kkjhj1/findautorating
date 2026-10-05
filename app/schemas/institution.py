from typing import Optional, List
from pydantic import BaseModel, ConfigDict

class AgencyMappingSchema(BaseModel):
    mapping_id: int
    agency_code: str
    search_name: str
    alias_name: Optional[str] = None
    mapping_status: str
    confidence: float

    model_config = ConfigDict(from_attributes=True)

class InstitutionResponse(BaseModel):
    institution_id: str
    institution_name: str
    original_name: str
    industry_type: str
    rating_type: str
    search_name_1: Optional[str] = None
    search_name_2: Optional[str] = None
    search_name_3: Optional[str] = None
    kr_target_rating: Optional[str] = None
    kis_target_rating: Optional[str] = None
    nice_target_rating: Optional[str] = None
    dart_corp_code: Optional[str] = None
    business_no: Optional[str] = None
    use_yn: str = "Y"
    user_modified: bool = False
    memo: Optional[str] = None
    mappings: List[AgencyMappingSchema] = []

    model_config = ConfigDict(from_attributes=True)

class SearchNamesUpdate(BaseModel):
    search_name_1: Optional[str] = None
    search_name_2: Optional[str] = None
    search_name_3: Optional[str] = None

class InstitutionCreate(BaseModel):
    institution_name: str
    industry_type: str
    rating_type: Optional[str] = None
    search_name_1: Optional[str] = None
    search_name_2: Optional[str] = None
    search_name_3: Optional[str] = None
    kr_target_rating: Optional[str] = None
    kis_target_rating: Optional[str] = None
    nice_target_rating: Optional[str] = None
    memo: Optional[str] = None
    use_yn: str = "Y"

class InstitutionUpdate(BaseModel):
    institution_name: Optional[str] = None
    industry_type: Optional[str] = None
    rating_type: Optional[str] = None
    search_name_1: Optional[str] = None
    search_name_2: Optional[str] = None
    search_name_3: Optional[str] = None
    kr_target_rating: Optional[str] = None
    kis_target_rating: Optional[str] = None
    nice_target_rating: Optional[str] = None
    memo: Optional[str] = None
    use_yn: Optional[str] = None

class ManualMappingUpdate(BaseModel):
    institution_id: str
    agency_code: str
    search_name: str
    alias_name: Optional[str] = None
    status: str = "MANUAL_CONFIRMED"
