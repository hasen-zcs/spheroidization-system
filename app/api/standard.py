from fastapi import APIRouter

# 导入测试数据
from app.mock.standard import standards


router = APIRouter(
    prefix="/api/standards",
    tags=["检测标准"],
)


@router.post("")
def create_standard(data: dict):
    standard = {
        "id": len(standards) + 1,
        "standard_spheroidization_time": data["standard_spheroidization_time"],
        "standard_entry_length": data["standard_entry_length"],
        "weighing_standard": data["weighing_standard"],
        "created_at": "2026-09-06 18:00:00",
        "created_by": data["created_by"],
        "remark": data.get("remark", ""),
    }

    standards.append(standard)

    return {
        "code": 200,
        "message": "标准创建成功",
        "data": standard,
    }


@router.get("/current")
def get_current_standard():
    return {
        "code": 200,
        "message": "success",
        "data": standards[-1],
    }


@router.get("/history")
def get_standard_history():
    return {
        "code": 200,
        "message": "success",
        "data": standards,
    }