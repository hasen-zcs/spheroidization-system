"""分段明细与上传台账的实体。

两张表都是 v3（2026-11-01 第一刀）新增，主表一列没动。

为什么分段要单独存
------------------
类型 5「球化过程中间亮光停顿」的判定条件本身就是"分段 ≥ 2 且存在停顿"。
只把结论（abnormal_type=5）和总时长入库，复核时没法还原"停在哪、停了多久"，
等于判了异常却拿不出证据。分段表就是这条证据链。

为什么上传要台账
----------------
合并层会重放、重试、崩溃重启，同一条检测结果可能被提交多次。
"同一个 (device_id, external_id) 只建一条档"必须由服务端保证——
合并层本地记一份只是第一道闸，脚本手工补传、别的调用方绕过它的时候，
只有服务端台账拦得住。
"""

from dataclasses import dataclass


@dataclass
class FlashSegment:
    """一段亮光。偏移相对"亮光首段起点"，单位秒。"""

    # 段号，从 1 开始连续。落库前由服务端校验，不连续直接 422。
    seg_index: int
    start_offset: float
    end_offset: float
    # 与上一段的停顿秒数；第一段为 None（不是 0，"没有上一段"和"没有停顿"是两回事）
    gap_before: float | None
    duration: float

    # 落库后由数据库回填
    segment_id: int | None = None
    spheroidization_record_id: int | None = None


@dataclass
class UploadLedgerEntry:
    """一条上传台账。幂等键 = (device_id, external_id)。"""

    device_id: str
    external_id: str
    record_id: int
    # 请求内容指纹（sha256 十六进制）。同键同指纹 = 重放；同键不同指纹 = 撞号。
    payload_sha: str
    created_at: str

    ledger_id: int | None = None
