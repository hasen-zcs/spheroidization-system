"""配对：一条亮光 + 一条进线（+ 可选按钮）配成一炉。

为什么按"进线"为主遍历
----------------------
一炉的物理顺序是：按按钮 → 喂丝开始（进线）→ 亮光起 → 亮光止 → 喂丝结束。
进线是必有的一环（没有进线就没有重量、没有进线起止，后端四字段也填不满），
所以拿进线当主轴去找亮光最稳；反过来找也行，但"有亮光没进线"那类
按规则就该丢掉，不该占着配对队列。

锚点（detection_time）
---------------------
有按钮用按钮（实测按钮比进线早 40s、比亮光早 26s）；
没有按钮退回亮光起点，并在日志标 anchor=light，
方便以后统计"多少炉是靠回退口径"。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Optional

TIME_FORMATS = ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S")


def parse_time(value) -> Optional[datetime]:
    if value in (None, ""):
        return None
    text = str(value).strip()
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


@dataclass
class Pair:
    light: dict
    plc: dict
    anchor: str
    anchor_kind: str  # button | light


def _light_in_feed_window(light_start: datetime, plc: dict, cfg) -> bool:
    feed_start = parse_time(plc["start"])
    if feed_start is None:
        return False
    feed_end = parse_time(plc.get("end")) or feed_start
    return (
        feed_start - timedelta(seconds=cfg.light_before_feed)
        <= light_start
        <= feed_end + timedelta(seconds=cfg.light_after_feed)
    )


def _pick_button(light_start: datetime, buttons: list[tuple[datetime, str]], cfg):
    """按钮必须落在 [亮光起点-300s, 亮光起点+60s]；取离亮光最近的那一个。"""
    best = None
    for pressed, text in buttons:
        delta = (light_start - pressed).total_seconds()
        if -cfg.light_before_button <= delta <= cfg.light_after_button:
            if best is None or pressed > best[0]:
                best = (pressed, text)
    return best


def pair_events(lights: Iterable[dict], plcs: Iterable[dict],
                buttons: Iterable[dict], cfg) -> list[Pair]:
    """按进线遍历，每条进线挑一条亮光；同一条亮光不会被两条进线抢走。

    同一条进线窗口里有多条亮光时取**最长**的那条——
    和现场老合并器的口径一致（短的通常是开门反光/补光）。
    """
    button_list = []
    for btn in buttons:
        pressed = parse_time(btn.get("pressed_at") or btn.get("button_confirm_time"))
        if pressed is not None:
            button_list.append((pressed, str(btn.get("pressed_at"))))
    button_list.sort()

    remaining = [l for l in lights if parse_time(l.get("start")) is not None]
    pairs: list[Pair] = []

    for plc in sorted(plcs, key=lambda p: str(p.get("start"))):
        candidates = [
            light
            for light in remaining
            if _light_in_feed_window(parse_time(light["start"]), plc, cfg)
        ]
        if not candidates:
            continue
        best = max(candidates, key=lambda l: _duration(l))
        remaining.remove(best)

        light_start = parse_time(best["start"])
        hit = _pick_button(light_start, button_list, cfg)
        if hit is not None:
            pairs.append(Pair(best, plc, anchor=hit[1], anchor_kind="button"))
        else:
            pairs.append(Pair(best, plc, anchor=str(best["start"]), anchor_kind="light"))

    return pairs


def _duration(light: dict) -> float:
    value = light.get("duration")
    if isinstance(value, (int, float)):
        return float(value)
    start, end = parse_time(light.get("start")), parse_time(light.get("end"))
    if start and end:
        return (end - start).total_seconds()
    return 0.0
