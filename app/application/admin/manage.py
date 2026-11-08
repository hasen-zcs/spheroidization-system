"""管理员数据管理用例：四类数据的软删除 / 恢复 / 处理状态修改。

从 API 层（app/api/admin.py）把"取整行 + 写 SQL + 审计快照"整段搬进来：
API 层只收请求、校验、按 DeleteResult 给响应，不再碰 SQL。

行为口径（和原 admin.py 一致）：
- 软删除 / 恢复是幂等的：已删再删、未删再恢复都不重复改库，返回 already。
- 目标在主键上查不到（行根本不存在）→ 返回 not_found。
- 当前生效标准不许软删：抛 BusinessException(400)。
- before / after 快照只留业务关键字段 + 软删三列，不含图片 BLOB。
"""

from dataclasses import dataclass
from typing import Optional

from app.application.standard.query import QueryStandardUseCase
from app.core.exceptions import BusinessException
from app.domain.review.repositories import ReviewRepository
from app.domain.spheroidization.repositories import SpheroidizationRepository
from app.domain.standard.repositories import StandardRepository
from app.domain.standard.switchlog_repositories import StandardSwitchLogRepository


# 各 kind 审计留痕的业务关键字段。刻意不含 spheroidization_image（BLOB，
# 几十 KB，绝不能进审计 detail）。
_KEY_FIELDS = {
    "record": ("detection_time", "processed", "processed_by", "processed_at"),
    "standard": ("standard_spheroidization_time", "weighing_standard", "created_by"),
    "switch_log": (
        "switched_at",
        "from_standard_record_id",
        "to_standard_record_id",
        "operated_by",
        "reason",
    ),
    "review": ("spheroidization_record_id", "review_result", "reviewer"),
}


@dataclass
class DeleteResult:
    """软删除 / 恢复 / 改处理状态的结果。

    status:
      not_found —— 主键上查不到行
      already   —— 目标已是目标态（已删再删 / 未删再恢复），本次没改库
      created   —— 本次真改了库
    before / after: 业务关键字段 + 软删三列的快照；not_found / already 时为 None。
    """

    status: str
    before: Optional[dict] = None
    after: Optional[dict] = None


class ManageDataUseCase:
    """四类数据的软删除 / 恢复 / 改处理状态。

    kind ∈ {"record", "standard", "switch_log", "review"}，内部按 kind 路由到
    对应仓储。standard_query_uc 用于判断"当前生效标准"，软删当前标准时拒绝。
    """

    def __init__(
        self,
        spheroid_repo: SpheroidizationRepository,
        standard_repo: StandardRepository,
        switchlog_repo: StandardSwitchLogRepository,
        review_repo: ReviewRepository,
        standard_query_uc: QueryStandardUseCase,
    ):
        self._repos = {
            "record": spheroid_repo,
            "standard": standard_repo,
            "switch_log": switchlog_repo,
            "review": review_repo,
        }
        self._standard_query_uc = standard_query_uc

    def _snapshot(self, kind: str, entity) -> dict:
        """业务关键字段 + 软删三列的快照，不含图片 BLOB。"""
        data = {k: getattr(entity, k) for k in _KEY_FIELDS[kind]}
        data["deleted_at"] = entity.deleted_at
        data["deleted_by"] = entity.deleted_by
        data["delete_reason"] = entity.delete_reason
        return data

    def soft_delete(
        self, kind: str, record_id: int, actor: str, reason: str
    ) -> DeleteResult:
        """软删除。当前生效标准不许删（抛 400）。幂等：已删返回 already。"""
        if kind == "standard":
            current = self._standard_query_uc.get_current()
            if current is not None and current.standard_record_id == record_id:
                raise BusinessException("该标准当前生效，请先切换标准后再作废", 400)

        repo = self._repos[kind]
        entity = repo.get_by_id_including_deleted(record_id)
        if entity is None:
            return DeleteResult(status="not_found")
        if entity.deleted_at is not None:
            return DeleteResult(status="already")

        before = self._snapshot(kind, entity)
        repo.soft_delete(record_id, actor, reason)
        after = self._snapshot(kind, repo.get_by_id_including_deleted(record_id))
        return DeleteResult(status="created", before=before, after=after)

    def restore(self, kind: str, record_id: int) -> DeleteResult:
        """恢复（清空软删三列）。幂等：未删返回 already。"""
        repo = self._repos[kind]
        entity = repo.get_by_id_including_deleted(record_id)
        if entity is None:
            return DeleteResult(status="not_found")
        if entity.deleted_at is None:
            return DeleteResult(status="already")

        before = self._snapshot(kind, entity)
        repo.restore(record_id)
        after = self._snapshot(kind, repo.get_by_id_including_deleted(record_id))
        return DeleteResult(status="created", before=before, after=after)

    def set_processed(
        self, record_id: int, processed: int, actor: str
    ) -> DeleteResult:
        """改球化记录人工处理状态（0↔1）。不看删除态，已删的行也能改。"""
        kind = "record"
        repo = self._repos[kind]
        entity = repo.get_by_id_including_deleted(record_id)
        if entity is None:
            return DeleteResult(status="not_found")

        before = self._snapshot(kind, entity)
        repo.set_processed(record_id, processed, actor)
        after = self._snapshot(kind, repo.get_by_id_including_deleted(record_id))
        return DeleteResult(status="created", before=before, after=after)
