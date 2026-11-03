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

import hashlib
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from .assemble import (
    AssembleError,
    _strip_data_uri,
    backfill_plc_from_all_plc,
    body_json,
    build_payload,
    build_payload_from_heat,
    plc_backfill_note,
    plc_skew,
)
from .config import Config
from .pair import Pair, pair_events, parse_time
from .sources import button as button_src
from .sources import heat as heat_src
from .sources import plc as plc_src
from .sources import temp as temp_src
from .sources import vpmin as vpmin_src
from .state import MergeState
from .upload import TransportError, Uploader


def _log(message: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}", flush=True)


def _heat_file_usable(path: Path) -> bool:
    """heat 主源文件是否可读。默认路径在 /root 下，无权限时按不存在处理。"""
    try:
        return path.exists()
    except OSError:
        return False


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
        self._last_guard_log = 0
        self._vpmin_warned = False
        self._heat_path_used = False

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
            "heat": 0,
            "no_plc_streak": 0,
        }
        self._heat_path_used = False
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
                if stats["pairs"] or stats["uploaded"] or stats["dead"] or stats["heat"]:
                    self.log(
                        "一轮：heat {heat} 配对 {pairs} 上传 {uploaded} 幂等 {existing} "
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

        # heat 主源路径：一行一炉，不需要亮光/PLC 配对；类型 1/2 也能入库。
        # heat 文件不存在（或所在目录不可访问）→ 回落 reactions 老路径，行为完全不变。
        if cfg.source == "heat":
            if _heat_file_usable(cfg.heat_file):
                self._heat_path_used = True
                self._ingest_heat(stats)
                return
            self.log(
                f"[WARN] heat 主源文件不存在：{cfg.heat_file} → 回落 reactions 老路径"
            )

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

    # ---------------- 1b. heat 主源 ----------------

    def _ingest_heat(self, stats: dict) -> None:
        """heat 主源：追尾读 heat_records.jsonl，逐条组包入库。

        顺序：先读温度（_match_temperature 依赖状态库温度表），再读 heat。
        组包 + 入队 + 推游标在同一个事务里——先入队再推游标，
        中间崩溃不丢数据；重复读靠 stable sha 去重（INSERT OR IGNORE）。
        """
        cfg = self.cfg

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

        # reaction 文件同步追尾（heat 路径）：heat 记录本身不带亮光分析图，
        # 图在 reaction 里。先读它再读 heat，同一轮到的炉子图已就位；
        # 配上的行组包后立即删（图已入 pending_upload），剩下的由 pending_ttl 清理。
        # 文件不可读（未配/权限）→ 本次无图，只告警一次，其余功能不受影响。
        try:
            vpmin_readable = cfg.vpmin_file.exists() and os.access(cfg.vpmin_file, os.R_OK)
        except OSError:
            vpmin_readable = False
        if not vpmin_readable:
            if not self._vpmin_warned:
                self.log(
                    f"[WARN] reaction 文件不可读：{cfg.vpmin_file} → 新炉无图"
                    "（其余功能不受影响；要图请配 MERGE_VPMIN_FILE）"
                )
                self._vpmin_warned = True
        else:
            events, inode, offset = vpmin_src.read_new(
                cfg.vpmin_file, self._cursor(cfg.vpmin_file)
            )
            with self.state:
                for event in events:
                    if event["kind"] == "bad":
                        self.state.dead_letter(
                            sha=f"bad-vpmin-{event['raw'][:32]}",
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
                        stats["lights"] = stats.get("lights", 0) + 1
                if inode:
                    self.state.set_cursor(cfg.vpmin_file, inode, offset)

        heat_events, inode, offset = heat_src.read_new(
            cfg.heat_file, self._cursor(cfg.heat_file)
        )
        processed = 0
        with self.state:
            for event in heat_events:
                if event["kind"] == "bad":
                    self.state.dead_letter(
                        sha=f"bad-heat-{event['raw'][:32]}",
                        source="heat",
                        external_id=None,
                        raw=event["raw"][:2000],
                        error="heat jsonl 行解析失败",
                    )
                    continue
                # limit 只限处理条数，游标照常推完，不重复处理
                if cfg.limit is not None and processed >= cfg.limit:
                    continue
                rec = event["record"]
                # T-004e 回捞：进线结束/时长 null → 按进线开始时间从 all_plc.jsonl 补齐；
                # heat 已有字段不被覆盖；回捞不到维持现状（422 死信会写明原因）
                if backfill_plc_from_all_plc(rec, cfg.plc_all_file) is not None:
                    self.log(
                        f"[PLC回捞] reaction_count={rec.get('reaction_count')} "
                        "进线结束/时长已从 all_plc 补齐"
                    )
                anchor = (
                    rec.get("plc_button_time")
                    or rec.get("spheroidization_start_time")
                    or rec.get("detection_time")
                )
                pair = Pair(
                    light={"record": rec},
                    plc={"record": rec},
                    anchor=anchor,
                    anchor_kind="button" if rec.get("plc_anchor") == "button" else "light",
                )
                temperature = self._match_temperature(pair)
                # 从配对到的 reaction 行取亮光分析图（配不到就无图，行为与以前一致）
                image = self._attach_image(rec, parse_time(anchor))
                payload = build_payload_from_heat(
                    rec, temperature, cfg.device_id, image=image
                )
                body = body_json(payload)
                if cfg.dry_run:
                    self._write_dry_run(payload, pair)
                elif self.state.is_delivered(cfg.device_id, payload["external_id"]):
                    stats["existing"] += 1
                else:
                    self.state.enqueue_upload(
                        sha=hashlib.sha256(
                            payload["external_id"].encode("utf-8")
                        ).hexdigest()[:16],
                        device_id=cfg.device_id,
                        external_id=payload["external_id"],
                        body=body,
                    )
                stats["heat"] += 1
                processed += 1
            if inode:
                self.state.set_cursor(cfg.heat_file, inode, offset)

    def _attach_image(self, rec: dict, anchor_dt: Optional[datetime]) -> Optional[str]:
        """heat 炉配 reaction 图：纯时间窗 [锚点-before, 锚点+after] 内取最近的。

        不用 rc：现场 heat 与 reactions 的 reaction_count 是两套不同步计数器（实测 rc 相等命中 0）。
        命中即删该行：图已随 payload 进 pending_upload（未传成功前一直留着），
        状态库不留第二份；无图的行也删，避免反复匹配。
        注意：在调用方的 `with self.state:` 事务里执行，删行与入队同生共死。
        """
        if anchor_dt is None:
            return None
        found = self.state.find_light_for_heat(
            anchor_dt, self.cfg.image_match_before, self.cfg.image_match_after
        )
        if found is None:
            return None
        payload, fp = found
        self.state.delete_light(fp)
        image = payload.get("spheroidization_image")
        if not image:
            return None
        return _strip_data_uri(str(image))

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
                error = f"HTTP {status} code={code} {body.get('message', '')}"
                note = plc_backfill_note(row["body"])
                if note:
                    error += f"｜{note}"
                # 死信存**完整** body：这是唯一留存的报文副本，[:4000] 会把带图片的
                # payload 在 base64 中间截断成坏 JSON（2026-11-03 heat:389 实锤），
                # 导致事后补录/分析都解析不了。死信罕见（天级几条），体积不是问题。
                self.state.dead_letter(
                    sha, "upload", row["external_id"], row["body"], error,
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
        if self._heat_path_used:
            # heat 路径不读 PLC 源：light 行只为配图追尾 reactions，
            # "有亮光没进线"是常态而非告警信号，守卫不适用（E2E 曾误报）。
            stats["no_plc_streak"] = 0
            return
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
