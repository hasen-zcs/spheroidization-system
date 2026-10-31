from dataclasses import dataclass


@dataclass
class StandardSwitchLog:

    # 切换时刻，由应用层传入（要和日志里的"操作时间"一致，不靠仓储自己取）
    switched_at: str
    # 切到哪一套标准
    to_standard_record_id: int
    # 操作人，取登录账号，不接受前端填
    operated_by: str
    # 切换原因，不能为空或全空格，表上有 CHECK 兜底
    reason: str
    # 从哪一套切过来。可空：库里还没有任何标准时的第一次切换没有"原标准"
    from_standard_record_id: int | None = None
    # 放在最后：dataclass 要求有默认值的字段必须排在没默认值的字段后面。
    switch_log_id: int | None = None
