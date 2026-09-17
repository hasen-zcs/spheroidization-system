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
    5. 不提供 update 方法。当前标准 = 最新创建的那条（主键最大），
       新标准创建时不需要改旧标准，标准表保持纯追加。
       历史球化记录存的是标准快照，也不会因新标准生效而变化。
    """

    @abstractmethod
    def save(self, standard: StandardRecord) -> StandardRecord:
        """
        新增一条标准，只增，不修改任何历史标准。

        :param standard: 待新增的实体，主键为空
        :return: 保存后的实体，主键已填充
        场景：管理员调整检测标准。

        库表上 standard_spheroidization_time 有 65~75 的 CHECK，
        超范围会被数据库拒绝，实现方不要再写一遍校验。
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
