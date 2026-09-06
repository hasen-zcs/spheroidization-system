from fastapi import APIRouter
from app.schemas.spheroidization import (
    SpheroidizationCreateRequest,
    SpheroidizationProcessRequest,
)
# 下面两条为测试数据导入
from app.mock.spheroidization import spheroidization_records
from app.mock.review import reviews
from app.mock.standard import standards

router = APIRouter(
    prefix="/api/spheroidization",
    tags=["球化记录"],
)


@router.post("")
def create_spheroidization(data: SpheroidizationCreateRequest):
    new_id = len(spheroidization_records) + 1
    current_standard = standards[-1]
    record = {
        "id": new_id,
        "detection_time": data.detection_time,
        "iron_water_weight": data.iron_water_weight,
        "spheroidization_start_time": data.spheroidization_start_time,
        "spheroidization_end_time": data.spheroidization_end_time,
        "actual_spheroidization_time": data.actual_spheroidization_time,
        "actual_entry_length": data.actual_entry_length,
        "machine_result": data.machine_result,
        "spheroidization_abnormal": data.spheroidization_abnormal,
        "entry_abnormal": data.entry_abnormal,

        # 新记录使用当前标准
        "standard_spheroidization_time": current_standard[
            "standard_spheroidization_time"
        ],
        "standard_entry_length": current_standard[
            "standard_entry_length"
        ],
        "weighing_standard": current_standard[
            "weighing_standard"
        ],

        "processed": False,
        "processed_at": None,
        "processed_by": None,
    }

    spheroidization_records.append(record)

    return {
        "code": 200,
        "message": "球化记录创建成功",
        "data": record,
    }


@router.get("")
def query_spheroidization():

    # 测试代码
    return {
        "code": 200,
        "message": "success",
        "data": spheroidization_records,
    }


@router.get("/abnormal")
def query_abnormal_spheroidization():

    # 测试代码
    data = [
        record
        for record in spheroidization_records
        if record["spheroidization_abnormal"]
        or record["entry_abnormal"]
    ]

    return {
        "code": 200,
        "message": "success",
        "data": data,
    }


@router.get("/{record_id}")
def get_spheroidization(record_id: int):
    # 测试代码
    for record in spheroidization_records:
        if record["id"] == record_id:
            return {
                "code": 200,
                "message": "success",
                "data": record,
            }

    return {
        "code": 404,
        "message": "记录不存在",
        "data": None,
    }


@router.post("/{record_id}/process")
def process_spheroidization(record_id: int,
                            data: SpheroidizationProcessRequest,):
    # 测试代码
    for record in spheroidization_records:
        if record["id"] == record_id:
            record["processed"] = True
            record["processed_at"] = "2026-09-06 18:00:00"
            record["processed_by"] = data.processed_by

            return {
                "code": 200,
                "message": "处理成功",
                "data": record,
            }

    return {
        "code": 404,
        "message": "记录不存在",
        "data": None,
    }