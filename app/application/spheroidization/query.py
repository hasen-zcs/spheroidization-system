# 查询球化记录、异常记录和单条记录。
class QuerySpheroidizationUseCase:
    """
    查询球化检测记录。

    支持：
    - 历史记录查询
    - 异常记录查询
    - 单条记录查询
    """
    def execute(self, request):
        raise NotImplementedError