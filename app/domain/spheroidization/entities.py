from dataclasses import dataclass


@dataclass
class SpheroidizationRecord:
    """
    球化检测记录。

    字段名和类型严格对应数据库表 SpheroidizationRecord（STRICT 表），
    改这个类之前先改表，两边必须一致。

    类型约定：
    - 时间是 "2026-09-05 08:30:15" 这种字符串（库里是 TEXT）。
      必须零填充，因为字符串比大小和排序要等于时间先后。
    - 时长是 float（秒数），不是字符串，别和时间点搞混。
    - "是否"一律是 0 / 1 整数，不是 bool——STRICT 表没有 BOOLEAN 类型，
      用 bool 存进去读回来会变成 int。
    - 图片是 bytes（库里是 BLOB）。接口层收发时按 base64 编解码，
      这一层手上拿到的始终是原始字节，不是 base64 字符串。

    原始机器检测结果创建后不可修改。
    """

    # 溯源：这条记录用了哪套标准。仅作标识，算法和报表用下面的快照值。
    standard_record_id: int

    # 机器检测事实（三个时间都是 "2026-09-05 08:30:15" 格式的字符串）
    detection_time: str
    spheroidization_start_time: str
    spheroidization_end_time: str

    # 实际反应时间（秒）。表上是 NOT NULL，必填。
    actual_spheroidization_time: float

    # 机器检测的物性数据。表上全部 NOT NULL，必填。
    # 2026-09 新增，原样搬自上游推送，本系统只存储、不做任何运算。
    spheroidization_temperature: float
    spheroidization_temperature_time: str
    spheroidization_wire_entry_start_time: str
    spheroidization_wire_entry_end_time: str
    spheroidization_wire_entry_total_duration: float
    spheroidization_weight: float

    # 建这条记录那一刻的标准球化时间（快照）
    standard_spheroidization_time: float

    # 机器判定球化是否异常：0 正常 / 1 异常，可为空
    spheroidization_abnormal: int | None = None

    # 检测图片的二进制内容。表上允许为 NULL——上游首帧可能没有图，
    # 这里不补空值，没有就是 None。
    spheroidization_image: bytes | None = None

    # 人工处理状态：0 未处理 / 1 已处理
    processed: int = 0

    # 人工处理时间，未处理时为 None
    processed_at: str | None = None

    # 处理人，未处理时为 None
    processed_by: str | None = None

    # 主键，由数据库自增分配（AUTOINCREMENT），调用方不传。
    # 放在最后：dataclass 要求有默认值的字段必须排在没默认值的字段后面。
    spheroidization_record_id: int | None = None
