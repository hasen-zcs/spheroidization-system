Application 层现在有 7 个 Use Case。

每个 UseCase 一个明确的业务操作，入参就是普通函数参数（不用 DTO、不用 dict），
业务错误统一抛 BusinessException。

类型约定：时间是 "2026-09-05 08:30:15" 格式的字符串；是否一律是整数 0/1（不是 bool）。

球化
├── CreateSpheroidizationUseCase
│     execute(detection_time, spheroidization_start_time, spheroidization_end_time,
│             actual_spheroidization_time=None, spheroidization_abnormal=None)
│     返回 SpheroidizationRecord
│     标准溯源 ID 和标准快照由本用例从当前标准取，不由调用方传
├── QuerySpheroidizationUseCase
│     list_all()            返回 List[SpheroidizationRecord]
│     list_abnormal()       返回 List[SpheroidizationRecord]（abnormal = 1）
│     get_by_id(record_id)  返回 SpheroidizationRecord 或 None
└── ProcessSpheroidizationUseCase
      execute(record_id, processed_by)   返回 SpheroidizationRecord
      已经处理过的再标记一次会抛 BusinessException —— 处置不可逆，没有撤销入口

复核
├── CreateReviewUseCase
│     execute(spheroidization_record_id, review_result, reviewer, review_remark=None)
│     review_result 是整数 0 正常 / 1 异常，不是字符串
│     返回 ReviewRecord
└── QueryReviewUseCase
      execute(spheroid_id)  返回 List[ReviewRecord]

标准
├── CreateStandardUseCase
│     execute(standard_spheroidization_time, standard_entry_length,
│             weighing_standard, created_by, remark=None)
│     返回 StandardRecord
└── QueryStandardUseCase
      get_current()         返回 StandardRecord 或 None
      get_history()         返回 List[StandardRecord]

两个约定：

- 查询类的 UseCase 不用 execute(request) 里按 type 字符串分支，
  改成同名方法直接暴露，避免字符串魔法值拼错不报错。
- 入参写普通函数参数，少传一个立刻 TypeError，签名本身就是参数清单。

完整契约（含每个方法的用途、参数、返回值、业务规则）见 docs/契约.md。
