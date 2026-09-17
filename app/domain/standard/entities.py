from dataclasses import dataclass


@dataclass
class StandardRecord:
    """
    检测标准记录。

    字段名和类型严格对应数据库表 StandardRecord（STRICT 表），
    改这个类之前先改表，两边必须一致。

    每次调整标准都新增一条，最新创建的那条即当前有效标准。

    类型约定：时间是 "2026-09-05 08:30:15" 格式的字符串，
    "是否"用 0/1 整数不用 bool（原因见 SpheroidizationRecord）。
    """

    # 标准球化时间（秒），库里限定在 65~75 之间
    standard_spheroidization_time: float

    # 标准进线长度，库里限定大于 0
    standard_entry_length: float

    # 称重标准
    weighing_standard: float

    # 创建人
    created_by: str

    # 备注 / 调整原因，可为空
    remark: str | None = None

    # 创建时间，由仓储实现方生成，调用方不传
    created_at: str | None = None

    # 主键，由数据库自增分配（AUTOINCREMENT），调用方不传。
    # 放在最后：dataclass 要求有默认值的字段必须排在没默认值的字段后面。
    standard_record_id: int | None = None
