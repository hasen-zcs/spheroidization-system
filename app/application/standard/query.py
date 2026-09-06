# 查询当前标准和标准历史。
class QueryStandardUseCase:
    """
    查询检测标准。

    支持：
    - 查询当前有效标准
    - 查询历史标准
    """
    
    def execute(self, request=None):
        raise NotImplementedError