
class SpheroidizationRecord:
    """
    球化检测记录。

    保存：
    - 机器检测产生的事实数据
    - 检测时使用的标准快照
    - 处理状态

    原始机器检测结果创建后不可修改。
    """
    
    id: int

    # =========================
    # 机器检测事实
    # =========================

    detection_time: str

    iron_water_weight: float

    spheroidization_start_time: str
    spheroidization_end_time: str

    actual_spheroidization_time: float
    actual_entry_length: float

    machine_result: str
    spheroidization_abnormal: bool
    entry_abnormal: bool

    # =========================
    # 检测时使用的标准快照
    # =========================

    standard_spheroidization_time: float
    standard_entry_length: float
    weighing_standard: float

    # =========================
    # 人工处理状态
    # =========================

    processed: bool
    processed_at: str | None
    processed_by: str | None