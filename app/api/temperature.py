"""测温枪读数的路由。

只开一个上报接口，给检测程序调用，不挂权限、不需要登录。
不提供"按记录查温度"的 GET：温度已经随球化记录的响应一起返回了，
再开一个既多余、又要多配一份鉴权。排查"一炉多条"直接查库更快。
"""

from fastapi import APIRouter, Depends

from app.application.temperature.create import CreateTemperatureUseCase
from app.dependencies import get_create_temperature_uc
from app.schemas.common import ok
from app.schemas.temperature import TemperatureCreateRequest, to_response

router = APIRouter(
    prefix="/api/temperature",
    tags=["测温"],
)


@router.post("")
def create_temperature(
    data: TemperatureCreateRequest,
    uc: CreateTemperatureUseCase = Depends(get_create_temperature_uc),
):
    # 机器调用接口，不走登录态，所以这里没有任何 require_permission。
    # 白名单按精确路径匹配（/api/temperature），不是按前缀——
    # 写成前缀放行的话，将来加的 POST 子路径会一起漏出去。
    record = uc.execute(
        gun_no=data.gun_no,
        temperature=data.temperature,
        measured_at=data.measured_at,
        spheroidization_record_id=data.spheroidization_record_id,
    )
    return ok(to_response(record), "温度上报成功")
