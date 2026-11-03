# 代码审计 · 发现清单（初稿，小白独立扫描 2026-11-04）

> 基准：`~/spheroidization-lab` @ `c807501`（278 测试全绿）。级别：P0 数据/安全 bug · P1 架构侵蚀 · P2 重复/异味 · P3 润色。
> 状态：待与 opencode AUDIT.md 对照合并。

## 干净项（审计确认无问题，防止误伤）
- **domain 层零外部依赖**：纯 abc + 标准库，无 cv2/numpy/infrastructure 倒挂 ✅
- **application 不引 infrastructure 具体类** ✅（唯一例外见 A-02）
- **merge/ 与 app/ 零 import 耦合**：独立状态库 merge_state.db、独立数据类 ✅
- **前端 0 个 any**，请求全走 api/index.ts 统一封装，token 集中处理 ✅
- **测试**：27 文件 275 用例，mock 用得到位，无空断言，conftest autouse 隔离真实库 ✅
- **魔法数字**：关键阈值已命名（FEED_END_LAG_LIMIT_S 等）✅
- **TODO 全库仅 1 条**（T-011c 强制改密，属未做功能，非技术债）✅

## 发现清单

### P1 架构侵蚀

**A-01｜app/api/admin.py:85-200｜API 层直连 SQL，绕过仓储/用例层**
- `_fetch_row`/`_soft_delete`/`_restore`/`_set_processed` 4 个函数直接 `container.conn.execute(...)` 写裸 SQL（含动态表名拼接）
- 为什么有害：TASK-8 快速迭代产物。软删除/处理状态是跨 4 类数据的写操作，却放在 API 层拼 SQL——绕开了仓储的事务边界、实体映射、用例编排。以后改表结构要同时改 SQL 字符串；审计留痕逻辑（before/after 快照）也和 SQL 混在一层
- 建议：①4 个仓储各加 `soft_delete/restore/get_including_deleted` 方法（SQL 回基础设施层）②新增 `ManageDataUseCase`（application 层）编排「取行→校验→改→快照」③API 层只调用例 + 写审计。`_set_processed` 下沉到 SpheroidizationRepository + 用例
- 工作量：约 150-200 行改动，中

**A-02｜app/application/reports/service.py｜application 层 12 处裸 SQL + summary 221 行上帝函数**
- `summary()` 单函数 221 行；全文件 12 处 `self._conn.execute` 直连 SQL，绕开仓储
- 为什么有害：报表是 TASK-2 加的，为了快直接裸 SQL。application 层本应只编排用例，不该自己写 SQL。现在报表统计口径（异常判定/分桶/趋势）散在 SQL 字符串里，和主链路（走仓储）是两套取数路径，口径易漂移
- 建议：①抽 `ReportRepository`（infrastructure）把 12 处 SQL 收进去，按统计维度分方法 ②`summary` 拆成 `_total/_by_type/_trend/_detail` 等私有方法 ③统计口径常量（异常判定条件）抽成共享定义，和主链路对齐
- 工作量：约 200-300 行改动，中偏大

### P2 重复 / 异味

**A-03｜merge/service.py:205-330｜_ingest_heat 三段「read_new→入队→推游标」高度重复**
- 温度/vpmin/heat 三个源各写一遍几乎一样的「读新行→事务里 add_*→推游标」，中间还夹 dead_letter 分支
- 建议：抽 `_drain_source(source, on_record)` 公共 helper，三个源各自只给「怎么读 + 怎么 add」
- 工作量：约 60-80 行，小

**A-04｜app/infrastructure/database/sqlite.py:853 行｜5 个仓储挤一个文件**
- 单文件 853 行，Spheroidization/Standard/SwitchLog/Review/User/Flash 等仓储全堆一起
- 建议：按仓储拆成 `sqlite/spheroidization.py`、`sqlite/standard.py` 等（纯搬移，不改逻辑），降低单文件认知负荷
- 工作量：纯重排，低（但要跑全量测试确认 import 没漏）

**A-05｜前端分页逻辑重复｜Admin.vue(11处)/Spheroidization.vue(8处) 各写一套分页**
- `changePage/totalPages/page_size/上一页下一页` 每个列表页重复实现
- 建议：抽 `usePagination` composable（state + 翻页 + 总页数），各页复用
- 工作量：约 80-120 行，小偏中

**A-06｜大文件｜Monitor.vue 1270 / Admin.vue 1215 / Reports.vue 968**
- 单组件过大，难维护难测
- 建议：Monitor 拆（视频流/状态/控制分开）；Reports 拆（趋势图/明细表/筛选）；Admin 四 tab 各拆子组件。属重构非 bug，优先级靠后
- 工作量：大，建议单独排期

### P3 润色
- 前端 4 个列表页的「列渲染/空值 display()」逻辑重复，可抽
- merge/assemble.py 94 行 build_payload_from_heat 可拆（温度/图片/迟到判定三段）

## 实施路线（建议）
1. **先 P1**：A-01（admin 直连 SQL 下沉）→ A-02（reports 裸 SQL 收口）——这两个是真正的架构侵蚀，修完分层才干净
2. **再 P2**：A-03（merge 去重）→ A-04（sqlite 拆文件）→ A-05（前端分页 composable）
3. **最后 P3/大重构**：A-06 大文件拆分单独排
- 每条一 commit 一验证（全量测试只增不减），行为不变（纯重构）
