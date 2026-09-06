from pydantic import BaseModel


class SpheroidizationCreateRequest(BaseModel):
    detection_time: str
    iron_water_weight: float
    spheroidization_start_time: str
    spheroidization_end_time: str
    actual_spheroidization_time: float
    actual_entry_length: float
    machine_result: str
    spheroidization_abnormal: bool
    entry_abnormal: bool


class SpheroidizationQueryRequest(BaseModel):
    abnormal_only: bool = False
    processed: bool | None = None


class SpheroidizationProcessRequest(BaseModel):
    processed_by: str


class SpheroidizationResponse(BaseModel):
    id: int
    detection_time: str
    iron_water_weight: float
    spheroidization_start_time: str
    spheroidization_end_time: str
    actual_spheroidization_time: float
    actual_entry_length: float
    machine_result: str
    spheroidization_abnormal: bool
    entry_abnormal: bool

    standard_spheroidization_time: float
    standard_entry_length: float
    weighing_standard: float

    processed: bool
    processed_at: str | None
    processed_by: str | None