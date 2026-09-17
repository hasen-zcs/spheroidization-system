"""球化检测记录的路由。

只做四件事：收请求 → 转参数 → 调 UseCase → 包响应。
业务规则（标准快照、处置不可逆）全在 UseCase 里，这里一行都不写。
"""

from fastapi import APIRouter, Depends

from app.application.spheroidization.create import CreateSpheroidizationUseCase
from app.application.spheroidization.process import ProcessSpheroidizationUseCase
from app.application.spheroidization.query import QuerySpheroidizationUseCase
from app.dependencies import (
    get_create_spheroidization_uc,
    get_process_spheroidization_uc,
    get_query_spheroidization_uc,
)
from app.schemas.common import fail, ok
from app.schemas.spheroidization import (
    SpheroidizationCreateRequest,
    SpheroidizationProcessRequest,
    to_response,
)

router = APIRouter(
    prefix="/api/spheroidization",
    tags=["球化记录"],
)


@router.post("")
def create_spheroidization(
    data: SpheroidizationCreateRequest,
    uc: CreateSpheroidizationUseCase = Depends(get_create_spheroidization_uc),
):
    record = uc.execute(
        detection_time=data.detection_time,
        spheroidization_start_time=data.spheroidization_start_time,
        spheroidization_end_time=data.spheroidization_end_time,
        actual_spheroidization_time=data.actual_spheroidization_time,
        # 前端发的是 bool，实体要 0 / 1
        spheroidization_abnormal=(
            None
            if data.spheroidization_abnormal is None
            else int(data.spheroidization_abnormal)
        ),
    )
    return ok(to_response(record), "球化记录创建成功")


@router.get("")
def query_spheroidization(
    uc: QuerySpheroidizationUseCase = Depends(get_query_spheroidization_uc),
):
    return ok([to_response(record) for record in uc.list_all()])


# 注意：/abnormal 必须声明在 /{record_id} 前面。
# 反过来的话，"abnormal" 会被当成 record_id 去转 int，直接 422。
@router.get("/abnormal")
def query_abnormal_spheroidization(
    uc: QuerySpheroidizationUseCase = Depends(get_query_spheroidization_uc),
):
    return ok([to_response(record) for record in uc.list_abnormal()])


@router.get("/{record_id}")
def get_spheroidization(
    record_id: int,
    uc: QuerySpheroidizationUseCase = Depends(get_query_spheroidization_uc),
):
    record = uc.get_by_id(record_id)
    if record is None:
        return fail("记录不存在", 404)
    return ok(to_response(record))


@router.post("/{record_id}/process")
def process_spheroidization(
    record_id: int,
    data: SpheroidizationProcessRequest,
    uc: ProcessSpheroidizationUseCase = Depends(get_process_spheroidization_uc),
):
    # 记录不存在、或已经是已处理状态，都会抛 BusinessException，
    # 由 main.py 的处理器统一转成 {code: 400, message, data: null}
    record = uc.execute(record_id=record_id, processed_by=data.processed_by)
    return ok(to_response(record), "处理成功")
