from pydantic import BaseModel


class StandardCreateRequest(BaseModel):
    standard_spheroidization_time: float
    standard_entry_length: float
    weighing_standard: float
    created_by: str
    remark: str = ""


class StandardResponse(BaseModel):
    id: int
    standard_spheroidization_time: float
    standard_entry_length: float
    weighing_standard: float
    created_at: str
    created_by: str
    remark: str