from fastapi import APIRouter

# 以下是导入测试数据
from app.mock.review import reviews
from app.mock.spheroidization import spheroidization_records


router = APIRouter(
    prefix="/api/reviews",
    tags=["复核记录"],
)


@router.post("")
def create_review(data: dict):
    # 测试代码
    record_exists = any(
        record["id"] == data["spheroidization_record_id"]
        for record in spheroidization_records
    )

    if not record_exists:
        return {
            "code": 404,
            "message": "球化记录不存在",
            "data": None,
        }

    review = {
        "id": len(reviews) + 1,
        "spheroidization_record_id": data["spheroidization_record_id"],
        "review_result": data["review_result"],
        "review_remark": data["review_remark"],
        "reviewer": data["reviewer"],
        "reviewed_at": "2026-09-06 18:00:00",
    }

    reviews.append(review)

    return {
        "code": 200,
        "message": "复核成功",
        "data": review,
    }



@router.get("/{record_id}")
def query_reviews(record_id: int):
    # 测试代码
    data = [
        review
        for review in reviews
        if review["spheroidization_record_id"] == record_id
    ]

    return {
        "code": 200,
        "message": "success",
        "data": data,
    }