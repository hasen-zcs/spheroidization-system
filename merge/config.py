"""合并层配置。所有路径和阈值都能用环境变量覆盖，现场换机器不用改代码。

默认路径对应东贝现场（10.0.0.19）的目录结构；
本地演练时用 `MERGE_*` 环境变量指到样例数据。
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

# 现场默认目录（vpmin 与 PLC 采集程序都在这个根下）
DEFAULT_ROOT = Path(os.getenv("MERGE_ROOT", "/root/MR"))


def _p(env: str, default: Path) -> Path:
    return Path(os.getenv(env, str(default)))


def _f(env: str, default: float) -> float:
    return float(os.getenv(env, default))


def _i(env: str, default: int) -> int:
    return int(os.getenv(env, default))


@dataclass
class Config:
    # ---- 输入文件 ----
    # vpmin 检测结果：追加写、不轮转
    vpmin_file: Path = field(
        default_factory=lambda: _p("MERGE_VPMIN_FILE", DEFAULT_ROOT / "reactions.jsonl")
    )
    # PLC 全量（追加）；滚动文件只在全量缺失时兜底
    plc_all_file: Path = field(
        default_factory=lambda: _p("MERGE_PLC_ALL", DEFAULT_ROOT / "all_plc.jsonl")
    )
    plc_rolling_file: Path = field(
        default_factory=lambda: _p("MERGE_PLC_ROLLING", DEFAULT_ROOT / "plc.jsonl")
    )
    # 温度全量（追加）；gunN.jsonl 是裁到 50 条的滚动文件，只做兜底
    temp_all_file: Path = field(
        default_factory=lambda: _p(
            "MERGE_TEMP_ALL", DEFAULT_ROOT / "all_temperature.jsonl"
        )
    )
    temp_rolling_dir: Path = field(
        default_factory=lambda: _p(
            "MERGE_TEMP_DIR", DEFAULT_ROOT / "temperture_guns"
        )
    )
    # 按钮时刻（追加）
    button_file: Path = field(
        default_factory=lambda: _p(
            "MERGE_BUTTON_FILE",
            DEFAULT_ROOT / "button_confirm" / "all_button_confirm_time.jsonl",
        )
    )

    # ---- 状态与输出 ----
    state_db: Path = field(
        default_factory=lambda: _p("MERGE_STATE_DB", DEFAULT_ROOT / "merge_state.db")
    )
    dry_run_out: Path = field(
        default_factory=lambda: _p("MERGE_DRYRUN_OUT", DEFAULT_ROOT / "merge_dryrun.jsonl")
    )
    log_file: Path = field(
        default_factory=lambda: _p("MERGE_LOG", DEFAULT_ROOT / "merge_service.log")
    )

    # ---- 后端 ----
    backend_url: str = field(
        default_factory=lambda: os.getenv("MERGE_BACKEND", "http://127.0.0.1:8000")
    )
    # 设备标识：幂等键的一半。同一台机器只能有一个值，改了等于换设备。
    device_id: str = field(default_factory=lambda: os.getenv("MERGE_DEVICE_ID", "casting-1"))

    # ---- 配对窗口（秒）----
    # 按钮 → 亮光起点：实测 13.6s，负向留 60s 是给"按钮比别人早按"留余量
    light_after_button: float = field(default_factory=lambda: _f("MERGE_LIGHT_AFTER_BTN", 300.0))
    light_before_button: float = field(default_factory=lambda: _f("MERGE_LIGHT_BEFORE_BTN", 60.0))
    # 亮光起点必须落在 [进线开始-30, 进线结束+60]
    light_before_feed: float = field(default_factory=lambda: _f("MERGE_LIGHT_BEFORE_FEED", 30.0))
    light_after_feed: float = field(default_factory=lambda: _f("MERGE_LIGHT_AFTER_FEED", 60.0))

    # ---- 温度 ----
    temp_window: float = field(default_factory=lambda: _f("MERGE_TEMP_WINDOW", 600.0))
    # 枪白名单：只认枪 4，其余枪的数据只存档
    temp_guns: tuple[int, ...] = field(
        default_factory=lambda: tuple(
            int(x) for x in os.getenv("MERGE_TEMP_GUNS", "4").split(",") if x.strip()
        )
    )

    # ---- 保护 / 重试 ----
    # 连续多少炉"有亮光无进线"就告警；0 = 关闭
    no_plc_guard: int = field(default_factory=lambda: _i("MERGE_NO_PLC_GUARD", 3))
    # 守卫触发后暂停丢弃的秒数
    guard_pause: float = field(default_factory=lambda: _f("MERGE_GUARD_PAUSE", 600.0))
    # 未配对的亮光保留多久（够人工排查，又不至于无限涨）
    pending_ttl: float = field(default_factory=lambda: _f("MERGE_PENDING_TTL", 86400.0))
    # 网络/5xx 重试的退避上限与死信总时长
    retry_max_delay: float = field(default_factory=lambda: _f("MERGE_RETRY_MAX", 60.0))
    dead_letter_after: float = field(
        default_factory=lambda: _f("MERGE_DEAD_AFTER", 86400.0)
    )
    # 主循环间隔
    poll_interval: float = field(default_factory=lambda: _f("MERGE_POLL", 2.0))
    http_timeout: float = field(default_factory=lambda: _f("MERGE_HTTP_TIMEOUT", 20.0))

    dry_run: bool = False

    def describe(self) -> str:
        return (
            f"vpmin={self.vpmin_file} plc_all={self.plc_all_file} "
            f"temp_all={self.temp_all_file} button={self.button_file} "
            f"state={self.state_db} backend={self.backend_url} "
            f"device={self.device_id} dry_run={self.dry_run}"
        )
