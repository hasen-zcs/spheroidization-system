"""标准应用状态的 JSON 文件实现。

该状态不写入数据库表，而是保存到 data/active_standard.json。
写入采用同目录临时文件加 os.replace，保证正常读取到完整 JSON。
"""

import json
import os
import threading
from pathlib import Path

from app.domain.standard.application_state import (
    StandardApplication,
    StandardApplicationState,
)
from app.infrastructure.database.connection import DEFAULT_DB_PATH


class JsonStandardApplicationState(StandardApplicationState):
    """使用单个 JSON 文件保存当前应用标准。"""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else DEFAULT_DB_PATH.parent / "active_standard.json"
        self._lock = threading.Lock()

    def load(self) -> StandardApplication | None:
        with self._lock:
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError, OSError):
                return None

            standard_record_id = raw.get("standard_record_id")
            applied_at = raw.get("applied_at")
            if not isinstance(standard_record_id, int) or standard_record_id <= 0:
                return None
            if not isinstance(applied_at, str) or not applied_at:
                return None

            applied_by = raw.get("applied_by")
            return StandardApplication(
                standard_record_id=standard_record_id,
                applied_at=applied_at,
                applied_by=applied_by if isinstance(applied_by, str) else None,
            )

    def save(self, application: StandardApplication) -> None:
        payload = {
            "standard_record_id": application.standard_record_id,
            "applied_at": application.applied_at,
            "applied_by": application.applied_by,
        }

        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = self.path.with_name(f"{self.path.name}.tmp")
            temporary_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary_path, self.path)
