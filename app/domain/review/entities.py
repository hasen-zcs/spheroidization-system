from dataclasses import dataclass


@dataclass
class ReviewRecord:
    """
    人工复核记录。
    复核记录追加保存，只增不改不删。
    类型约定：时间是 "2026-09-05 08:30:15" 格式的字符串，
    "是否"用 0/1 整数不用 bool（原因见 SpheroidizationRecord）。
    """
    # 外键
    spheroidization_record_id: int
    review_result: int
    reviewer: str
    # 复核备注，可为空
    review_remark: str | None = None
    # 复核时间，由仓储实现方生成，调用方不传
    reviewed_at: str | None = None
    # 放在最后：dataclass 要求有默认值的字段必须排在没默认值的字段后面。
    review_record_id: int | None = None
