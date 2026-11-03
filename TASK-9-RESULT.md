# TASK-9 完成结果：管理员「数据管理」页面（前端）+ 两个后端小接口

- 全量 pytest：**275 passed**（基线 273 + 新增 2，无失败、无跳过）
- 前端 build：**成功**（`vue-tsc -b` 类型检查 + `vite build`，`dist/` 已产出）
- 未 git commit；未改后端既有接口签名；未动 merge / 检测 / auth 登录逻辑

## 文件清单

### 新增
| 文件 | 说明 |
|---|---|
| `frontend/src/views/Admin.vue` | 数据管理页：四 tab（球化记录/检测标准/切换记录/复核记录），各自独立分页（page_size=20）、右上角「显示已删除」开关、删除（原因必填，trim 后为空禁用确定）、恢复（无需原因）、处理状态 0↔1（原因必填） |
| `frontend/src/api/admin.ts` | 管理页 API 封装：任务书点名的 9 个函数 `deleteRecord/restoreRecord/changeProcessed/deleteStandard/restoreStandard/deleteSwitchLog/restoreSwitchLog/deleteReview/restoreReview` + 4 个列表函数 `adminQueryRecords/adminQueryStandards/adminGetCurrentStandardId/adminQuerySwitchLogs/adminQueryReviews`。统一走 `index.ts` 的 `request`/`jsonOptions`（带 token、统一信封处理），不另造 fetch |

### 改动（后端，B0）
| 文件 | 改动 |
|---|---|
| `app/api/admin.py` | 追加 2 个 GET 接口：`/api/admin/reviews`、`/api/admin/switch-logs`（均挂 `require_permission(P.ACTION_MANAGE_DATA)`，`ok()` 信封，分页结构 `{items, total, page, page_size, has_more}` 对齐 `GET /api/spheroidization`，行带 `deleted_at/deleted_by/delete_reason`）。复用 `QueryReviewUseCase` / `SwitchStandardUseCase` 与既有 `to_response` |
| `app/infrastructure/database/sqlite.py` | `SqliteReviewRepository` 增 `list_page(offset, limit, include_deleted)` / `count(include_deleted)`；`SqliteStandardSwitchLogRepository` 增 `count(include_deleted)` |
| `app/domain/review/repositories.py` | 抽象接口同步声明上述两个方法 |
| `app/domain/standard/switchlog_repositories.py` | 抽象接口增 `count`；`list_all` 签名补上实现里已有的 `include_deleted` 参数（对齐，不改行为） |
| `app/application/review/query.py` | `QueryReviewUseCase` 增 `list_all_page(page, page_size, include_deleted) -> (items, total)` |
| `app/application/standard/switch.py` | `SwitchStandardUseCase` 增 `count_logs(include_deleted)`（`list_logs` 不返回总数） |
| `tests/test_admin_data.py` | 新增 2 条测试（见下） |

### 改动（前端）
| 文件 | 改动 |
|---|---|
| `frontend/src/api/index.ts` | `request`/`jsonOptions` 加 `export`（供 `admin.ts` 复用同一套请求封装）；`SpheroidizationQuery` 增可选 `include_deleted`（不传行为不变） |
| `frontend/src/router/index.ts` | 新增顶层路由 `/admin`（**不挂在 /records 下**），`meta: { title: "数据管理", permission: "action:manage_data" }`，复用既有守卫（未登录跳登录、无权限跳 /403） |
| `frontend/src/App.vue` | 导航栏「用户管理」后加 `<router-link v-if="can('action:manage_data')" to="/admin">数据管理</router-link>`（已确认 `can()` 支持任意权限码、超管直接 true） |
| `frontend/src/constants.ts` | `ACTION_PERMISSIONS` 增 `{ key: "action:manage_data", label: "数据管理" }`，放在 `action:manage_users` 前面（操作类组）；注释 9→10 个。`Users.vue` 权限勾选面板由 `PERMISSION_GROUPS` 驱动，无需改代码 |

## 每个 tab 用的真实接口与字段

| Tab | 接口 | 行字段（前端实际读取） |
|---|---|---|
| 球化记录 | `GET /api/spheroidization?page=&page_size=&include_deleted=`（现有接口） | `detection_time` / `actual_spheroidization_time` / `spheroidization_abnormal`（判定）/ `processed` + `processed_by` + `processed_at`（有值时显示）/ `deleted_at` `deleted_by` `delete_reason`；操作走 `POST /api/admin/records/{id}/processed {processed: 0|1, reason}`、`.../delete {reason}`、`.../restore`（空 body） |
| 检测标准 | `GET /api/standards/history?include_deleted=`（现有接口，**返回全量数组、不分页**，分页在前端切，page_size=20） | `id` / `standard_spheroidization_time` / `standard_spheroidization_time_lower~upper` / `weighing_standard` / `created_at` / `created_by` / `remark` / 软删三字段；当前生效标准用 `GET /api/standards/current` 的 `id` 对比（history 无 `is_current` 字段）→ 该行删除按钮禁用，hover 提示「当前生效标准不能作废，请先切换」；操作走 `/api/admin/standards/{id}/delete|restore` |
| 切换记录 | `GET /api/admin/switch-logs?page=&page_size=&include_deleted=`（**本次新增**） | `switched_at` / `from_standard_record_id` + `from_value`（显示「标准X（Ys）」，标准已作废时 value 为 null）/ `to_standard_record_id` + `to_value` / `operated_by` / `reason` / 软删三字段；操作走 `/api/admin/switch-logs/{id}/delete|restore` |
| 复核记录 | `GET /api/admin/reviews?page=&page_size=&include_deleted=`（**本次新增**） | `spheroidization_record_id`（记录ID）/ `review_result`（"正常"/"异常"）/ `reviewer` / `reviewed_at` / `review_remark` / 软删三字段；操作走 `/api/admin/reviews/{id}/delete|restore` |

已删除行：整行 `opacity: 0.55` + 「已删除」标签 + `deleted_by · deleted_at · delete_reason` 小字；成功用现有 notice-bar（`flashNotice`，同 Users.vue），失败沿用现有 `alert`，403 走 App 全局 forbidden-toast（请求层自动派发）。

## B0 两个新接口

- `GET /api/admin/reviews?page=1&page_size=20&include_deleted=false`
  走 `QueryReviewUseCase.list_all_page` → `SqliteReviewRepository.list_page/count`，按 `review_record_id` 倒序。
- `GET /api/admin/switch-logs?page=1&page_size=20&include_deleted=false`
  走 `SwitchStandardUseCase.list_logs`（既有用例，逐条带回原/目标标准实体）+ 新增 `count_logs`，响应行 = `switch_log_to_response` 全字段 + `from_value`/`to_value`。

**一处与任务书口径的偏差（已尽量贴近）**：任务书要求「复用现有仓储/UseCase，别新写 SQL」，但复核仓储原本只有按单条球化记录查的方法、切换日志仓储没有 `count`，两张表都拿不出「全库分页 + total」。为满足 `{items, total, page, page_size}` 契约，在**仓储层**（SQL 本该在的层，API 层一行 SQL 未写）补了 3 条最小语句：`ReviewRecord` 的 `SELECT ... LIMIT/OFFSET` + `COUNT(*)`、`StandardSwitchLogs` 的 `COUNT(*)`，均带 `deleted_at IS NULL` 默认过滤与 `include_deleted` 开关，写法照抄同文件既有仓储。

## 新增测试（2 条，`tests/test_admin_data.py`）

1. `test_全库列表接口权限游客401无权限403`：两个新接口游客 401；登录但只有 `page:records`+`page:standard`（能看标准页切换日志）的用户仍 403 —— 管理员页只认 `action:manage_data`。
2. `test_全库列表include_deleted能拿到已删行`：造 1 条复核 + 1 条切换日志并软删 → 默认列表 total=0/items=[]；`include_deleted=true` 能拿到，`deleted_by=="root"`、`delete_reason` 正确，分页键集合与 `/api/spheroidization` 一致。
3. 变异验证：把 `list_all_reviews` 里的 `include_deleted` 硬编码成 False，测试 2 当场变红；还原后恢复绿。

## 验收结果

```
$ cd frontend && npm run build
vue-tsc -b 通过，vite build 成功（dist/assets 已重新产出）

$ cd .. && .venv/bin/python -m pytest tests/ -q
275 passed, 1 warning in 80.03s
```

`tests/test_api_frontend_parity.py` 未改动（它锁的是既有契约；新接口是新增路由，不涉及既有断言；前端新调用的路径已逐一对照 `app/api/admin.py` / `standard.py` / `spheroidization.py` 实际注册确认存在）。

## 风格（F 节）

- 无新增 CSS 文件；`Admin.vue` 的 scoped 样式只复用 `style.css` 及既有页面的既有色值（#f0f2f5 / #fff / #d9d9d9 / #e8e8e8 / #fafafa / #003399 / #1890ff / #c62828 / #16803c / #d48806 / #fff7e6 / #ffd591 / #f6ffed / #b7eb8f 等），无玻璃拟态、无渐变、无新色值
- 880px 内容中轴（`.page-shell { max-width: 880px; margin: 0 auto; }`），卡片 1px 发丝描边（#d9d9d9），无圆角大阴影
- 小标签大写疏排：页头 overline「DATA MANAGEMENT」（uppercase + letter-spacing 2px，照抄 Monitor.vue 的疏排口径）；「已删除」「生效中」小标签 letter-spacing 1px；tab 选中态用暗金 #d48806 下划线强调
