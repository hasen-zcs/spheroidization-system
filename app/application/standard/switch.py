from datetime import datetime

from app.application.standard.apply import ApplyStandardUseCase
from app.core.exceptions import BusinessException
from app.domain.standard.application_state import StandardApplicationState
from app.domain.standard.entities import StandardRecord
from app.domain.standard.repositories import StandardRepository
from app.domain.standard.switchlog_entities import StandardSwitchLog
from app.domain.standard.switchlog_repositories import StandardSwitchLogRepository


class SwitchStandardUseCase:
    """
    切换当前应用标准，并留一条切换日志。

    和 ApplyStandardUseCase 的区别：apply 只管"把状态改成这套"，
    本用例在它前面加"必须填原因"、在它后面加"记一笔日志"，
    对外暴露的是这次带审计的切换动作。

    业务规则
    --------
    - 原因不能为空或全空格。切换标准会改变之后新建记录的判定基准，
      事后必须能查出是谁、什么时候、为什么换的。
    - 操作人只能来自登录态，由路由层从当前会话取，不接受前端传值。
    - 写日志必须在 apply 成功之后。反过来先写日志再 apply，
      apply 一失败就会留下"日志说切了、实际没切"的假账。
    - 切换只影响之后新建的记录——新建记录取当前标准做快照，
      这是既有机制，本用例不需要额外处理。

    依赖：StandardRepository、StandardApplicationState、
          StandardSwitchLogRepository
    """

    def __init__(
        self,
        standard_repo: StandardRepository,
        application_state: StandardApplicationState,
        switch_log_repo: StandardSwitchLogRepository,
    ):
        self.standard_repo = standard_repo
        self.application_state = application_state
        self.switch_log_repo = switch_log_repo

    def _current_standard(self) -> StandardRecord | None:
        """取当前应用标准：先看状态文件，文件缺失或指向无效 ID 时回退到最新标准。

        和 QueryStandardUseCase.get_current() 同一套逻辑。这里没有复用那个类，
        是因为它要额外注入一份状态依赖，为一个方法把两个 UseCase 串起来更绕。
        """
        application = self.application_state.load()
        if application is not None:
            standard = self.standard_repo.get_by_id(application.standard_record_id)
            if standard is not None:
                return standard
        return self.standard_repo.get_current()

    def execute(
        self,
        to_standard_record_id: int,
        reason: str,
        operated_by: str,
    ) -> StandardRecord:
        """
        :param to_standard_record_id: 要切换到的标准主键
        :param reason: 切换原因，不能为空
        :param operated_by: 操作人，由路由层从登录态取
        :return: 切换后的当前标准实体
        """
        if not reason or not reason.strip():
            raise BusinessException("切换标准必须填写原因")

        target = self.standard_repo.get_by_id(to_standard_record_id)
        if target is None:
            raise BusinessException("目标标准不存在", 404)

        # 先记下原标准：apply 之后状态文件已经指向新标准，回查就拿不到旧的了
        current = self._current_standard()

        # 状态切换交给专门的应用用例，这里不重复写一遍
        ApplyStandardUseCase(self.standard_repo, self.application_state).execute(
            to_standard_record_id,
            applied_by=operated_by,
        )

        self.switch_log_repo.save(
            StandardSwitchLog(
                switched_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                from_standard_record_id=(
                    current.standard_record_id if current is not None else None
                ),
                to_standard_record_id=to_standard_record_id,
                operated_by=operated_by,
                reason=reason,
            )
        )

        return target

    def list_logs(
        self,
        page: int,
        page_size: int,
    ) -> list[tuple[StandardSwitchLog, StandardRecord | None, StandardRecord | None]]:
        """分页查切换日志，并把每条日志对应的"原标准 / 目标标准"一起取出来。

        :return: [(日志, 原标准或 None, 目标标准或 None), ...]，最新的在前

        为什么在应用层拼而不是让路由自己去查：路由拿到仓储就等于绕开了
        "业务规则都在 UseCase 里"这条线，以后加个"隐藏已删除标准"之类的
        规则，就得回头挨个改路由。日志量小，逐条单查两次不碍事。
        """
        offset = (page - 1) * page_size
        logs = self.switch_log_repo.list_all(offset=offset, limit=page_size)

        result = []
        for log in logs:
            from_standard = (
                self.standard_repo.get_by_id(log.from_standard_record_id)
                if log.from_standard_record_id is not None
                else None
            )
            to_standard = (
                self.standard_repo.get_by_id(log.to_standard_record_id)
                if log.to_standard_record_id is not None
                else None
            )
            result.append((log, from_standard, to_standard))
        return result
