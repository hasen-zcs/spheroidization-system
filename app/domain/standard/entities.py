
class StandardRecord:
    """
    检测标准记录。

    每次创建新的检测标准，都产生新的 StandardRecord。
    最新创建的标准作为当前有效标准。

    下面是部分数据：
        标准球化时间
        标准进线长度
        称重标准
        创建时间
        创建人
        备注/原因
    """

    id: int

    standard_spheroidization_time: float
    standard_entry_length: float
    weighing_standard: float

    created_at: str
    created_by: str
    remark: str
