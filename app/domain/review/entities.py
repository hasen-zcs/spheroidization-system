from dataclasses import dataclass


@dataclass
class ReviewRecord:
    """
    人工复核记录。

    字段名和类型严格对应数据库表 ReviewRecord（STRICT 表），
    改这个类之前先改表，两边必须一致。

    复核记录追加保存，只增不改不删。

    类型约定：时间是 "2026-09-05 08:30:15" 格式的字符串，
    "是否"用 0/1 整数不用 bool（原因见 SpheroidizationRecord）。
    """

    # 外键，指向 SpheroidizationRecord.spheroidization_record_id
    spheroidization_record_id: int

    # 复核结果：0 正常 / 1 异常。是 0/1 整数，不是"正常"/"异常"字符串。
    review_result: int

    # 复核人
    reviewer: str

    # 复核备注，可为空
    review_remark: str | None = None

    # 复核时间，由仓储实现方生成，调用方不传
    reviewed_at: str | None = None

    # 主键，由数据库自增分配（AUTOINCREMENT），调用方不传。
    # 放在最后：dataclass 要求有默认值的字段必须排在没默认值的字段后面。
    review_record_id: int | None = None
