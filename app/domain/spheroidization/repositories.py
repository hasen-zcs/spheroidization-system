from abc import ABC, abstractmethod
from typing import List, Optional

from app.domain.spheroidization.entities import SpheroidizationRecord


class SpheroidizationRepository(ABC):
    """
    球化检测记录仓储抽象接口。只定义能做什么，不管底层是什么。
    实现由 infrastructure 层提供，入口负责注入。

    跨方法约定（实现方必须遵守，调用方可依赖）：
    1. 主键由实现方生成：调用方传的实体主键为空，写入后由数据库自增分配，
       实现方回填再返回。
    2. 时间由实现方生成：processed_at 调用方不传。
    3. 查单条无结果返回 None；查列表无结果返回空列表。
    4. 不提供删除方法：机器检测结果不可改，人工处置不可回退。

    类型约定（对齐底层 STRICT 表）：
    - 时间是 "2026-09-05 08:30:15" 格式的字符串（库里是 TEXT）。
    - "是否"一律是 0 / 1 整数，不是 bool。读出来不要转 bool，
      否则调用方的 == True 判断会静默失效。
    """

    @abstractmethod
    def save(self, record: SpheroidizationRecord) -> SpheroidizationRecord:
        """
        新增一条记录，对应 INSERT，不负责更新。

        :param record: 待新增的实体，主键为空
        :return: 保存后的实体，主键已填充
        场景：上游推送检测结果，建档入库。
        """
        ...

    @abstractmethod
    def update(self, record: SpheroidizationRecord) -> SpheroidizationRecord:
        """
        更新一条已有记录，对应 UPDATE。

        :param record: 已有实体，主键必填
        :return: 更新后的实体
        场景：人工把记录标记为"已处理"。

        实现方负责：
        - 只改 processed、processed_at、processed_by，机器检测事实一律不动。
        - 由"未处理"变"已处理"时生成 processed_at；已经是已处理则保留原值。

        处置不可逆：一条记录只允许一次人工处置，不回退状态，
        所以本接口不提供任何"撤销处理"的方法。

        本方法不判断"是不是已经处理过"，那是业务规则，
        由 ProcessSpheroidizationUseCase 负责。
        """
        ...

    @abstractmethod
    def get_by_id(self, record_id: int) -> Optional[SpheroidizationRecord]:
        """
        按主键查单条。

        :param record_id: 记录主键
        :return: 实体；查不到返回 None
        场景：记录详情页、标记处理前查记录。
        """
        ...

    @abstractmethod
    def list_all(self) -> List[SpheroidizationRecord]:
        """
        查全部记录。

        :return: 实体列表，无数据返回空列表
        场景：检测历史列表页。
        """
        ...

    @abstractmethod
    def list_abnormal(self) -> List[SpheroidizationRecord]:
        """
        查所有异常记录，定义为 spheroidization_abnormal = 1。

        该字段可为空，NULL 按"不异常"处理。实现上写
        WHERE spheroidization_abnormal = 1 即可——
        SQL 里 NULL = 1 不成立，空值自然被排除。

        :return: 实体列表，无数据返回空列表
        场景：异常记录页面。
        """
        ...
