"""创建球化检测记录。

两条路径，同一条业务规则，区别只在"怎么防重"：

1. **老路径**（不带 device_id / external_id）：人工补录、旧上传器。
   直接建档，不做幂等——它们每次都是人盯着点的，重了就是人点重了，
   服务端替它猜反而容易吞掉真数据。

2. **幂等路径**（带 device_id + external_id）：合并层用这条。
   - 台账里没有这个键 → 建档 + 写分段 + 写台账，**一个事务**
   - 台账里有、内容指纹一致 → 不重复建，返回已有记录（existing=true）
   - 台账里有、指纹不同 → 409 拒收。同号不同内容说明上游流水号撞了
     （计数器被重置之类），这种情况绝不能覆盖，也不能悄悄返回旧记录。

事务边界为什么在用例层
----------------------
建档、分段、台账必须同生共死：只建了档没写分段，类型 5 就丢了证据；
建了档写了台账但分段失败，台账会把这个键永久占掉（之后重传都返回 existing，
那条记录的分段永远补不上）。所以三个仓储的写方法都不自带提交，
由这里用 `with self.conn:` 统一包住。

标准快照、异常透传这些规则跟老路径完全一样，没有第二套口径。
"""

import hashlib
import json
import sqlite3
from datetime import datetime

from app.core.exceptions import BusinessException
from app.domain.flash.entities import FlashSegment, UploadLedgerEntry
from app.domain.flash.repositories import (
    FlashSegmentRepository,
    UploadLedgerRepository,
)
from app.domain.spheroidization.entities import SpheroidizationRecord
from app.domain.spheroidization.repositories import SpheroidizationRepository
from app.domain.standard.repositories import StandardRepository


def _r3(value: float | None) -> float | None:
    """指纹里的浮点统一 3 位，避免 95.45499999999998 这种噪声让同一份数据算出两个指纹。"""
    return None if value is None else round(float(value), 3)


class CreateSpheroidizationUseCase:
    """
    创建球化检测记录。
    接收上游推送的一条检测结果，取当前有效标准生成快照，建档保存。

    步骤
    ----
    1. 取当前有效标准；取不到抛业务异常
    2. 记下标准主键（溯源）和标准球化时间（快照）
    3. 组装实体，人工处理状态初始为未处理
    4. 保存并返回

    业务规则
    --------
    - 快照取自"创建这一刻的当前标准"，之后标准怎么改都不影响这条记录。
    - 原始机器检测结果创建后不可修改。
    - 是否已处理、是否已复核都在创建之后才产生，本用例不涉及。
    - 异常类型和异常说明由上游检测程序判定，这里原样落库，不做推导。
    - 分段明细只存不算：判定结果归上游，本系统负责留证据。

    依赖：SpheroidizationRepository、StandardRepository，
         幂等路径还需要 UploadLedgerRepository、FlashSegmentRepository 和连接本身。
    """

    def __init__(
        self,
        spheroid_repo: SpheroidizationRepository,
        standard_repo: StandardRepository,
        ledger_repo: UploadLedgerRepository | None = None,
        segment_repo: FlashSegmentRepository | None = None,
        conn: sqlite3.Connection | None = None,
    ):
        self.spheroid_repo = spheroid_repo
        self.standard_repo = standard_repo
        self.ledger_repo = ledger_repo
        self.segment_repo = segment_repo
        self.conn = conn

    # ---------------- 对外：老路径 ----------------

    def execute(
        self,
        detection_time: str,
        spheroidization_wire_entry_start_time: str,
        spheroidization_wire_entry_end_time: str,
        spheroidization_wire_entry_total_duration: float,
        spheroidization_weight: float,
        spheroidization_start_time: str | None = None,
        spheroidization_end_time: str | None = None,
        actual_spheroidization_time: float | None = None,
        spheroidization_abnormal: int | None = None,
        abnormal_type: int | None = None,
        abnormal_reason: str | None = None,
        plc_button_time: str | None = None,
        spheroidization_image: bytes | None = None,
        device_id: str | None = None,
        external_id: str | None = None,
        segments=None,
    ) -> SpheroidizationRecord:
        """建档。带 device_id+external_id 时自动走幂等路径，只返回记录本体。

        返回值保持原样（一条实体），是为了不惊动已有调用方；
        需要知道"这次到底是新建还是幂等命中"的调用方用 execute_idempotent。
        """
        record, _existing = self.execute_idempotent(
            detection_time=detection_time,
            spheroidization_wire_entry_start_time=spheroidization_wire_entry_start_time,
            spheroidization_wire_entry_end_time=spheroidization_wire_entry_end_time,
            spheroidization_wire_entry_total_duration=spheroidization_wire_entry_total_duration,
            spheroidization_weight=spheroidization_weight,
            spheroidization_start_time=spheroidization_start_time,
            spheroidization_end_time=spheroidization_end_time,
            actual_spheroidization_time=actual_spheroidization_time,
            spheroidization_abnormal=spheroidization_abnormal,
            abnormal_type=abnormal_type,
            abnormal_reason=abnormal_reason,
            plc_button_time=plc_button_time,
            spheroidization_image=spheroidization_image,
            device_id=device_id,
            external_id=external_id,
            segments=segments,
        )
        return record

    # ---------------- 对外：幂等路径 ----------------

    def execute_idempotent(
        self,
        detection_time: str,
        spheroidization_wire_entry_start_time: str,
        spheroidization_wire_entry_end_time: str,
        spheroidization_wire_entry_total_duration: float,
        spheroidization_weight: float,
        spheroidization_start_time: str | None = None,
        spheroidization_end_time: str | None = None,
        actual_spheroidization_time: float | None = None,
        spheroidization_abnormal: int | None = None,
        abnormal_type: int | None = None,
        abnormal_reason: str | None = None,
        plc_button_time: str | None = None,
        spheroidization_image: bytes | None = None,
        device_id: str | None = None,
        external_id: str | None = None,
        segments=None,
    ) -> tuple[SpheroidizationRecord, bool]:
        """:return: (记录实体, 是否幂等命中已有记录)"""
        segs = list(segments or [])
        fields = dict(
            detection_time=detection_time,
            spheroidization_wire_entry_start_time=spheroidization_wire_entry_start_time,
            spheroidization_wire_entry_end_time=spheroidization_wire_entry_end_time,
            spheroidization_wire_entry_total_duration=spheroidization_wire_entry_total_duration,
            spheroidization_weight=spheroidization_weight,
            spheroidization_start_time=spheroidization_start_time,
            spheroidization_end_time=spheroidization_end_time,
            actual_spheroidization_time=actual_spheroidization_time,
            spheroidization_abnormal=spheroidization_abnormal,
            abnormal_type=abnormal_type,
            abnormal_reason=abnormal_reason,
            plc_button_time=plc_button_time,
            spheroidization_image=spheroidization_image,
        )

        # 没给幂等键 = 老路径，行为跟改造前一模一样：建档即提交
        if not device_id or not external_id:
            return self.spheroid_repo.save(self._build(**fields)), False

        if self.ledger_repo is None or self.segment_repo is None or self.conn is None:
            raise BusinessException(
                "服务未装配幂等组件（台账/分段/连接），无法按幂等模式建档", 500
            )

        payload_sha = self._payload_sha(fields, segs)
        hit = self.ledger_repo.find(device_id, external_id)
        if hit is not None:
            return self._resolve_hit(hit, payload_sha)

        record = self._build(**fields)
        try:
            with self.conn:
                saved = self.spheroid_repo.save_no_commit(record)
                self.segment_repo.save_many_no_commit(
                    saved.spheroidization_record_id, segs
                )
                self.ledger_repo.add_no_commit(
                    UploadLedgerEntry(
                        device_id=device_id,
                        external_id=external_id,
                        record_id=saved.spheroidization_record_id,
                        payload_sha=payload_sha,
                        created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    )
                )
            return saved, False
        except sqlite3.IntegrityError:
            # 并发重放：另一个请求刚刚把同一个键写进去了。
            # 回滚之后查台账，按"同内容 / 不同内容"分别处理。
            hit = self.ledger_repo.find(device_id, external_id)
            if hit is None:
                raise
            return self._resolve_hit(hit, payload_sha)

    # ---------------- 内部 ----------------

    def _resolve_hit(
        self, entry: UploadLedgerEntry, payload_sha: str
    ) -> tuple[SpheroidizationRecord, bool]:
        if entry.payload_sha != payload_sha:
            raise BusinessException(
                "幂等键冲突：device_id="
                f"{entry.device_id}、external_id={entry.external_id} 已有记录且内容不同。"
                "上游流水号可能被重置或复用，拒绝覆盖已有数据，请人工核对。",
                409,
            )
        record = self.spheroid_repo.get_by_id(entry.record_id)
        if record is None:
            raise BusinessException(
                f"上传台账指向的记录不存在：record_id={entry.record_id}，数据可能被人工删除",
                500,
            )
        return record, True

    def _build(self, **fields) -> SpheroidizationRecord:
        """取当前标准、组实体。老路径和幂等路径共用这一份。"""
        current_standard = self.standard_repo.get_current()
        if current_standard is None:
            raise BusinessException("不存在生效检测标准，无法创建球化检测记录")

        return SpheroidizationRecord(
            # 溯源：这条记录用了当前这套标准。仅作标识，
            # 业务运算用的是下面的快照值，不是实时去查标准表。
            standard_record_id=current_standard.standard_record_id,
            # 机器检测事实，原样搬自上游
            detection_time=fields["detection_time"],
            spheroidization_start_time=fields["spheroidization_start_time"],
            spheroidization_end_time=fields["spheroidization_end_time"],
            actual_spheroidization_time=fields["actual_spheroidization_time"],
            spheroidization_wire_entry_start_time=fields[
                "spheroidization_wire_entry_start_time"
            ],
            spheroidization_wire_entry_end_time=fields[
                "spheroidization_wire_entry_end_time"
            ],
            spheroidization_wire_entry_total_duration=fields[
                "spheroidization_wire_entry_total_duration"
            ],
            spheroidization_weight=fields["spheroidization_weight"],
            spheroidization_abnormal=fields["spheroidization_abnormal"],
            # 异常分类和说明原样存：判定是上游的事，后端只记录。
            # 这里一推导，将来两边口径不一致就查不清是谁改的。
            abnormal_type=fields["abnormal_type"],
            abnormal_reason=fields["abnormal_reason"],
            plc_button_time=fields["plc_button_time"],
            spheroidization_image=fields["spheroidization_image"],
            # 标准快照：创建这一刻的标准球化时间
            standard_spheroidization_time=(
                current_standard.standard_spheroidization_time
            ),
            # 人工处理状态：新建一律未处理
            processed=0,
            # processed_at / processed_by 未处理时为 None。
            # spheroidization_record_id 由仓储实现方生成并回填。
        )

    @staticmethod
    def _payload_sha(fields: dict, segments) -> str:
        """请求内容指纹。

        规范化要点：
        - 键排序、UTF-8、不舍弃非 ASCII（中文原因也算进指纹）
        - 浮点统一 3 位（库里也是 3 位，避免同一份数据算出两个指纹）
        - 图片只取 sha256，不把几万字节塞进指纹原文
        """
        image = fields["spheroidization_image"]
        canonical = {
            "detection_time": fields["detection_time"],
            "plc_button_time": fields["plc_button_time"],
            "spheroidization_start_time": fields["spheroidization_start_time"],
            "spheroidization_end_time": fields["spheroidization_end_time"],
            "actual_spheroidization_time": _r3(
                fields["actual_spheroidization_time"]
            ),
            "wire_entry_start": fields["spheroidization_wire_entry_start_time"],
            "wire_entry_end": fields["spheroidization_wire_entry_end_time"],
            "wire_entry_duration": _r3(
                fields["spheroidization_wire_entry_total_duration"]
            ),
            "weight": _r3(fields["spheroidization_weight"]),
            "abnormal": fields["spheroidization_abnormal"],
            "abnormal_type": fields["abnormal_type"],
            "abnormal_reason": fields["abnormal_reason"],
            "segments": [
                [
                    seg.seg_index,
                    _r3(seg.start_offset),
                    _r3(seg.end_offset),
                    _r3(seg.gap_before),
                    _r3(seg.duration),
                ]
                for seg in segments
            ],
            "image_sha256": (
                None
                if image is None
                else hashlib.sha256(bytes(image)).hexdigest()
            ),
        }
        blob = json.dumps(
            canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()
