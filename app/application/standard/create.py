# 创建新的检测标准。
class CreateStandardUseCase:
    """
    创建新的检测标准。

    新标准创建后立即成为当前有效标准。
    历史标准保留，不修改历史球化检测记录。
    """
    
    def execute(self, request):
        raise NotImplementedError