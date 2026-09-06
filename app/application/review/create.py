# 创建复核记录
class CreateReviewUseCase:
    """
    创建人工复核记录。

    流程：
    1. 检查球化检测记录是否存在
    2. 创建人工复核记录
    3. 保存人工复核记录

    注意：
    不允许修改原始机器检测结果。
    """
    
    def execute(self, request):
        raise NotImplementedError