from abc import ABC, abstractmethod
from typing import List, Optional

from app.domain.standard.entities import StandardRecord


class StandardRepository(ABC):
    """
    检测标准仓储抽象接口。实现由 infrastructure 层提供。
    跨方法约定（实现方必须遵守，调用方可依赖）：
    1. 主键由实现方生成：调用方传的实体主键为空，写入后由数据库自增分配，
       实现方回填再返回。
    2. 时间由实现方生成：created_at 调用方不传，
       格式 "2026-09-05 08:30:15"。
    3. 查单条无结果返回 None；查列表无结果返回空列表。
    4. 不提供删除方法。标准是历史记录，不删除。
       球化记录通过 standard_record_id 外键引用标准（ON DELETE RESTRICT），
       删了会让溯源 ID 变孤儿。
    5. 提供 update 方法：只做 5 个业务字段的修订
       （球化时间 / 上限 / 下限 / 称重标准 / 备注），
       不改 created_at / created_by——标准是谁、什么时候建的一律保持原样。
       历史球化记录存的是标准快照，也不会因标准修订而变化。
    """

    @abstractmethod
    def save(self, standard: StandardRecord) -> StandardRecord:
        """
        新增一条标准，只增，不修改任何历史标准。
        :param standard: 待新增的实体，主键为空
        :return: 保存后的实体，主键已填充
        场景：管理员调整检测标准。
        库表上 standard_spheroidization_time 只有 > 0 的 CHECK，
        非法值会被数据库拒绝，实现方不要再写一遍校验。
        """
        ...

    @abstractmethod
    def update(
        self,
        standard_record_id: int,
        standard_spheroidization_time: float,
        standard_spheroidization_time_upper: float | None,
        standard_spheroidization_time_lower: float | None,
        weighing_standard: float,
        remark: str,
    ) -> Optional[StandardRecord]:
        """
        按主键修订 5 个业务字段，created_at / created_by 一律不动。
        :param standard_record_id: 标准主键
        :param standard_spheroidization_time: 标准球化时间（秒），库里限定大于 0
        :param standard_spheroidization_time_upper: 球化时长上限（秒），可为空
        :param standard_spheroidization_time_lower: 球化时长下限（秒），可为空
        :param weighing_standard: 称重标准
        :param remark: 备注 / 调整原因
        :return: 更新后的完整实体；行不存在（含已软删除）返回 None
        场景：管理员修订某条标准参数。
        球化记录存的是标准快照，历史判定不受影响。
        """
        ...

    @abstractmethod
    def get_current(self) -> Optional[StandardRecord]:
        """
        查当前有效标准 = 主键最大的那条，即最新创建的标准。
        :return: 实体；一条标准都没有时返回 None
        场景：创建球化记录时取标准做快照。
        按主键倒序取第一条即可，不需要额外的"是否生效"标记字段。
        """
        ...

    @abstractmethod
    def get_history(self) -> List[StandardRecord]:
        """
        查全部标准，含当前和历史。
        :return: 实体列表，无数据返回空列表
        场景：标准历史页面。
        """
        ...

    @abstractmethod
    def get_by_id_including_deleted(self, standard_record_id: int) -> Optional[StandardRecord]:
        """
        按主键查单条，**含已软删除的行**。
        :param standard_record_id: 标准主键
        :return: 实体；行根本不存在返回 None
        场景：管理员软删除 / 恢复前取整行做审计快照。
        """
        ...

    @abstractmethod
    def soft_delete(self, standard_record_id: int, deleted_by: str, delete_reason: str) -> bool:
        """
        软删除：置 deleted_at / deleted_by / delete_reason，绝不物理 DELETE。
        :param standard_record_id: 标准主键
        :param deleted_by: 删除人（登录账号）
        :param delete_reason: 删除原因
        :return: True=本次真删了；False=行不存在或已删除（幂等）
        """
        ...

    @abstractmethod
    def restore(self, standard_record_id: int) -> bool:
        """
        恢复：清空软删除三列。
        :param standard_record_id: 标准主键
        :return: True=本次真恢复了；False=行不存在或本来未删（幂等）
        """
        ...
