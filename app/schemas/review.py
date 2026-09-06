from pydantic import BaseModel


class ReviewCreateRequest(BaseModel):
    spheroidization_record_id: int
    review_result: str
    review_remark: str
    reviewer: str


class ReviewResponse(BaseModel):
    id: int
    spheroidization_record_id: int
    review_result: str
    review_remark: str
    reviewer: str
    reviewed_at: str