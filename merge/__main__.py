"""命令行入口。

    python -m merge --dry-run          # 影子跑：只写 merge_dryrun.jsonl，不调接口
    python -m merge                    # 正常跑（常驻）
    python -m merge --once             # 跑一轮就退出（调试/定时用）
    python -m merge --replay-dead-letter
"""

import argparse
import json
import sys

from .config import Config
from .service import MergeService
from .state import MergeState


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="检测结果合并层")
    parser.add_argument("--dry-run", action="store_true", help="不调接口，只写预览文件")
    parser.add_argument("--once", action="store_true", help="只跑一轮")
    parser.add_argument("--replay-dead-letter", action="store_true",
                        help="把死信重新入队（人工改完数据后用）")
    parser.add_argument("--backend", default=None, help="覆盖后端地址")
    parser.add_argument("--device-id", default=None, help="覆盖设备标识")
    args = parser.parse_args(argv)

    cfg = Config()
    cfg.dry_run = args.dry_run
    if args.backend:
        cfg.backend_url = args.backend
    if args.device_id:
        cfg.device_id = args.device_id

    state = MergeState(cfg.state_db)

    if args.replay_dead_letter:
        rows = state.dead_letter_rows()
        if not rows:
            print("没有死信")
            return 0
        requeued = 0
        for row in rows:
            try:
                body = json.loads(row["raw"])
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(body, dict) or "external_id" not in body:
                continue
            state.enqueue_upload(
                sha=row["raw"][:0] or f"replay-{row['id']}",
                device_id=body.get("device_id", cfg.device_id),
                external_id=str(body["external_id"]),
                body=json.dumps(body, ensure_ascii=False, separators=(",", ":")),
            )
            requeued += 1
        state.clear_dead_letter([row["id"] for row in rows])
        state.commit()
        print(f"死信 {len(rows)} 条，重新入队 {requeued} 条")
        return 0

    service = MergeService(cfg, state=state)
    if args.once:
        stats = service.run_once()
        print(json.dumps(stats, ensure_ascii=False))
        return 0

    service.run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
