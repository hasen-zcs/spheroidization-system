"""合并层主循环：读 → 配 → 装 → 传。

一轮做四件事，顺序有讲究：
1. **先读按钮**：按钮是锚点，晚读一轮不影响配对（配对是全量重扫未配对事件），
   但先读能让这一轮的日志好看。
2. **读事件并入队**：事件入库和游标推进在**同一个事务**里。
   先入队再推游标——反过来的话，中间崩溃就永久丢那批数据。
3. **配对组包**：未配对的亮光每轮都重扫（量很小），所以晚到的进线也能配上。
4. **上传队列**：所有包先进 pending_upload，投递成功才删。

任何一步失败都不影响下一轮：状态都在库里，进程重启从断点继续。
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from .assemble import AssembleError, body_json, build_payload, plc_skew
from .config import Config
from .pair import pair_events, parse_time
from .sources import button as button_src
from .sources import plc as plc_src
from .sources import temp as temp_src
from .sources import vpmin as vpmin_src
from .state import MergeState
from .upload import TransportError, Uploader


def _log(message: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}", flush=True)


class MergeService:
    def __init__(
        self,
        cfg: Config,
        state: Optional[MergeState] = None,
        uploader: Optional[Uploader] = None,
        log: Callable[[str], None] = _log,
    ):
        self.cfg = cfg
        self.state = state or MergeState(cfg.state_db)
        self.uploader = uploader or Uploader(cfg)
        self.log = log
        self._guard_until: Optional[float] = None
        self._last_guard_log = 0.0

    # ---------------- 主循环 ----------------

    def run_once(self) -> dict:
        stats = {
            "lights": 0,
            "plcs": 0,
            "temps": 0,
            "buttons": 0,
            "pairs": 0,
            "uploaded": 0,
            "existing": 0,
            "failed": 0,
            "dead": 0,
            "no_plc_streak": 0,
        }
        self._ingest(stats)
        self._match(stats)
        self._flush_uploads(stats)
        self._guard(stats)
        self.state.purge_unmatched_lights(self.cfg.pending_ttl)
        self.state.commit()
        return stats

    def run_forever(self) -> None:
        self.log(f"合并层启动：{self.cfg.describe()}")
        while True:
            try:
                stats = self.run_once()
                if stats["pairs"] or stats["uploaded"] or stats["dead"]:
                    self.log(
                        "一轮：配对 {pairs} 上传 {uploaded} 幂等 {existing} "
                        "失败 {failed} 死信 {dead}".format(**stats)
                    )
            except KeyboardInterrupt:
                self.log("收到中断，退出")
                return
            except Exception as exc:                     # 主循环不能因为一轮异常就死
                self.log(f"[ERROR] 本轮异常：{exc}")
                self.state.conn.rollback()
            time.sleep(self.cfg.poll_interval)

    # ---------------- 1. 读 ----------------

    def _ingest(self, stats: dict) -> None:
        cfg = self.cfg

        events, inode, offset = button_src.read_new(
            cfg.button_file, self._cursor(cfg.button_file)
        )
        with self.state:
            for event in events:
                if self.state.add_button(event["fp"], event["pressed_at"]):
                    stats["buttons"] += 1
            if inode:
                self.state.set_cursor(cfg.button_file, inode, offset)

        events, inode, offset = temp_src.read_new(
            cfg.temp_all_file, cfg.temp_rolling_dir, self._cursor(cfg.temp_all_file)
        )
        with self.state:
            for event in events:
                if self.state.add_temp(
                    event["fp"], event["gun_no"], event["value"], event["measured_at"]
                ):
                    stats["temps"] += 1
            if inode:
                self.state.set_cursor(cfg.temp_all_file, inode, offset)

        events, inode, offset = vpmin_src.read_new(
            cfg.vpmin_file, self._cursor(cfg.vpmin_file)
        )
        with self.state:
            for event in events:
                if event["kind"] == "bad":
                    self.state.dead_letter(
                        sha=f"bad-{event['raw'][:32]}",
                        source="vpmin",
                        external_id=None,
                        raw=event["raw"][:2000],
                        error="jsonl 行解析失败",
                    )
                    continue
                if self.state.add_light(
                    event["fp"],
                    vpmin_src.encode(event["record"]),
                    event["start"],
                    event["end"],
                    event["duration"],
                    event["reaction_count"],
                ):
                    stats["lights"] += 1
            if inode:
                self.state.set_cursor(cfg.vpmin_file, inode, offset)

        events, inode, offset = plc_src.read_new(
            cfg.plc_all_file, cfg.plc_rolling_file, self._cursor(cfg.plc_all_file)
        )
        with self.state:
            for event in events:
                if event["kind"] == "bad":
                    self.state.dead_letter(
                        sha=f"bad-plc-{event['raw'][:32]}",
                        source="plc",
                        external_id=None,
                        raw=event["raw"][:2000],
                        error="plc jsonl 行解析失败",
                    )
                    continue
                if self.state.add_plc(
                    event["fp"], plc_src.encode(event["record"]),
                    event["start"], event["end"],
                ):
                    stats["plcs"] += 1

    def _cursor(self, path: Path):
        row = self.state.get_cursor(path)
        return (row["inode"], row["offset"]) if row else None

    # ---------------- 2. 配对组包 ----------------

    def _match(self, stats: dict) -> None:
        lights = [
            {
                "fp": row["fp"],
                "start": row["light_start"],
                "end": row["light_end"],
                "duration": row["duration"],
                "record": json.loads(row["payload"]),
            }
            for row in self.state.unmatched_lights()
        ]
        plcs = [
            {
                "fp": row["fp"],
                "start": row["feed_start"],
                "end": row["feed_end"],
                "record": json.loads(row["payload"]),
            }
            for row in self.state.unmatched_plcs()
        ]
        if not lights or not plcs:
            return

        buttons = [
            {"pressed_at": row["pressed_at"]}
            for row in self.state.conn.execute(
                "SELECT pressed_at FROM button_event"
            ).fetchall()
        ]

        for pair in pair_events(lights, plcs, buttons, self.cfg):
            stats["pairs"] += 1
            temperature = self._match_temperature(pair)
            try:
                payload = build_payload(
                    pair, temperature, self.cfg.device_id
                )
            except AssembleError as exc:
                self.state.dead_letter(
                    sha=f"assemble-{pair.light['fp']}",
                    source="assemble",
                    external_id=str(pair.light.get("reaction_count")),
                    raw=json.dumps(pair.light["record"], ensure_ascii=False)[:4000],
                    error=str(exc),
                )
                self.state.mark_matched(pair.light["fp"], pair.plc["fp"], None)
                stats["dead"] += 1
                continue

            skew = plc_skew(payload)
            if skew is not None and abs(skew) > 1.0:
                self.log(
                    f"[WARN] plc_skew={skew}s（进线时长与起止差对不上）"
                    f" external_id={payload['external_id']}"
                    f" anchor={pair.anchor_kind}"
                )

            body = body_json(payload)
            if self.cfg.dry_run:
                self._write_dry_run(payload, pair)
            else:
                self.state.enqueue_upload(
                    sha=_sha(body),
                    device_id=payload["device_id"],
                    external_id=payload["external_id"],
                    body=body,
                )
            self.state.mark_matched(pair.light["fp"], pair.plc["fp"], None)

    def _match_temperature(self, pair) -> Optional[dict]:
        """枪白名单 + 必须早于锚点 + ≤600s + 占用制（一条只挂一炉）。"""
        anchor = parse_time(pair.anchor)
        if anchor is None:
            return None
        best = None
        for row in self.state.unclaimed_temps(self.cfg.temp_guns):
            measured = parse_time(row["measured_at"])
            if measured is None or measured > anchor:
                continue                       # 迟到的一律不认
            if (anchor - measured).total_seconds() > self.cfg.temp_window:
                continue
            if best is None or measured > parse_time(best["measured_at"]):
                best = {"row": row, "measured_at": row["measured_at"]}
        if best is None:
            return None
        row = best["row"]
        if not self.state.claim_temp(row["fp"], None):
            return None                        # 被别的炉抢了
        return {
            "gun_no": row["gun_no"],
            "value": row["value"],
            "measured_at": row["measured_at"],
        }

    def _write_dry_run(self, payload: dict, pair) -> None:
        preview = dict(payload)
        image = preview.pop("spheroidization_image", None)
        preview["_image_bytes"] = len(image) if image else 0
        preview["_anchor"] = pair.anchor_kind
        self.cfg.dry_run_out.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cfg.dry_run_out, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(preview, ensure_ascii=False) + "\n")

    # ---------------- 3. 上传 ----------------

    def _flush_uploads(self, stats: dict) -> None:
        for row in self.state.due_uploads():
            sha = row["payload_sha"]
            if self.state.is_delivered(row["device_id"], row["external_id"]):
                self.state.mark_delivered(
                    sha, row["device_id"], row["external_id"], None
                )
                continue
            try:
                status, body = self.uploader.send(row["body"])
            except TransportError as exc:
                delay = self.uploader.backoff(row["attempts"])
                self.state.retry_later(sha, f"网络错误：{exc}", delay)
                stats["failed"] += 1
                continue

            code = body.get("code")
            if code == 200:
                record_id = (body.get("data") or {}).get("id")
                existing = bool((body.get("data") or {}).get("existing"))
                self.state.mark_delivered(
                    sha, row["device_id"], row["external_id"], record_id
                )
                stats["existing" if existing else "uploaded"] += 1
                self.log(
                    f"[上传] external_id={row['external_id']} → 记录 {record_id}"
                    f"{'（幂等命中）' if existing else ''}"
                )
            elif code in (409, 422) or (isinstance(code, int) and 400 <= code < 500):
                self.state.dead_letter(
                    sha, "upload", row["external_id"], row["body"][:4000],
                    f"HTTP {status} code={code} {body.get('message', '')}",
                )
                stats["dead"] += 1
                self.log(
                    f"[死信] external_id={row['external_id']} code={code} "
                    f"{body.get('message', '')}"
                )
            else:
                delay = self.uploader.backoff(row["attempts"])
                self.state.retry_later(sha, f"HTTP {status} code={code}", delay)
                stats["failed"] += 1

    # ---------------- 4. 守卫 ----------------

    def _guard(self, stats: dict) -> None:
        """连续多炉"有亮光没进线"→ 大概率是 PLC 采集中断，不是杂光。

        老板定的规则是"只有亮光没有 PLC 就是杂光，不入库"——这条规则不变。
        守卫只负责**喊人**：连续 N 炉都这样，说明规则的前提（采集正常）不成立了，
        继续静默丢就是一整天的数据没了。
        """
        streak = self.state.recent_light_misses(limit=max(self.cfg.no_plc_guard, 1))
        stats["no_plc_streak"] = streak
        if not self.cfg.no_plc_guard or streak < self.cfg.no_plc_guard:
            return
        now = time.time()
        if self._guard_until and now < self._guard_until:
            return
        if now - self._last_guard_log < self.cfg.guard_pause:
            return
        self._last_guard_log = now
        self._guard_until = now + self.cfg.guard_pause
        self.log(
            f"[ERROR] 已连续 {streak} 炉有亮光但没有进线 —— 疑似 PLC 采集中断，"
            "请检查 bridge/PLC 采集进程。这些亮光暂不入库（按杂光规则），"
            "事件还在状态库里，修好后可人工补。"
        )


def _sha(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()
