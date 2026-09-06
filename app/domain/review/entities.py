
class ReviewRecord:
    """
    人工复核记录。

    保存：
    - 对应的球化检测记录
    - 人工复核结果
    - 复核说明
    - 复核人员
    - 复核时间

    复核记录采用追加方式保存。
    """
    
    id: int

    spheroidization_record_id: int

    review_result: str
    review_remark: str

    reviewer: str
    reviewed_at: str