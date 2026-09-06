# 将球化记录标记为处理完成。
class ProcessSpheroidizationUseCase:
    """
    标记球化检测记录为已处理。

    注意：
    - 是否已处理与人工复核独立
    - 不修改原始机器检测结果
    """
    
    def execute(self, record_id):
        raise NotImplementedError