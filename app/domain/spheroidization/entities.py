from dataclasses import dataclass


@dataclass
class SpheroidizationRecord:
    """
    球化检测记录。
    字段名和类型严格对应数据库表 SpheroidizationRecord（STRICT 表），
    改这个类之前先改表，两边必须一致。
    类型约定：
    - 图片是 bytes（库里是 BLOB）。接口层收发时按 base64 编解码，
      这一层手上拿到的始终是原始字节，不是 base64 字符串。
    原始机器检测结果创建后不可修改。
    """

    # 溯源：这条记录用了哪套标准。仅作标识，算法和报表用下面的快照值。
    standard_record_id: int
    detection_time: str
    # 下面三个时间可空。进站未球化、进线提前中止这两种异常下，
    # 球化根本没完整跑完，本来就没有开始/结束/时长可填。
    # 表上也不给 NOT NULL，这里跟着放开，两边必须一致。
    spheroidization_start_time: str | None
    spheroidization_end_time: str | None
    actual_spheroidization_time: float | None
    # 机器检测的物性数据。表上 NOT NULL，必填。
    # 温度已经不在这张表里了，独立成 TemperatureRecord，
    # 因为一根测温枪一次测量对应多条球化记录，塞进主表会重复存。
    spheroidization_wire_entry_start_time: str
    spheroidization_wire_entry_end_time: str
    spheroidization_wire_entry_total_duration: float
    spheroidization_weight: float
    # 建这条记录那一刻的标准球化时间（快照）
    standard_spheroidization_time: float
    # 机器判定球化是否异常：0 正常 / 1 异常，可为空
    spheroidization_abnormal: int | None = None
    # 异常分类：1 进站未球化 / 2 球化线滑动、进线提前中止 / 3 超过标准 / 4 低于标准
    # 和 abnormal_reason 都由上游检测设备给出，原样存，这一层不做推导。
    abnormal_type: int | None = None
    # 异常的文字说明，同样原样存
    abnormal_reason: str | None = None
    # 检测图片的二进制内容。表上允许为 NULL——上游首帧可能没有图，
    # 这里不补空值，没有就是 None。
    spheroidization_image: bytes | None = None
    # 人工处理状态：0 未处理 / 1 已处理
    processed: int = 0
    # 人工处理时间，未处理时为 None
    processed_at: str | None = None
    # 处理人，未处理时为 None
    processed_by: str | None = None
    # 放在最后：dataclass 要求有默认值的字段必须排在没默认值的字段后面。
    # abnormal_type / abnormal_reason 之所以带 = None 放在 spheroidization_abnormal 后面，
    # 也是为了这个顺序——放到前面会 TypeError: non-default argument follows default argument。
    spheroidization_record_id: int | None = None
