# TASK-9 管理员「数据管理」页面（前端）

## 背景
TASK-8 后端已上线（commit 27ca7e1）：`/api/admin/*` 9 个接口，权限码 `action:manage_data`，四类数据软删/恢复，处理状态 0↔1。
本轮只做前端。**不许改后端接口签名，不许改 merge/检测/auth 登录逻辑。**

## A. 路由与导航
1. `frontend/src/router/index.ts`：新增顶层路由 `/admin`（**不要挂在 /records 下面**）：
   - `component: Admin`，`meta: { title: "数据管理", permission: "action:manage_data" }`
2. `frontend/src/App.vue` 导航栏：在「用户管理」后加
   `<router-link v-if="can('action:manage_data')" to="/admin">数据管理</router-link>`
   - `can()` 已支持任意权限码（超管直接 true），先确认再写

## B0. 先补两个后端小接口（app/api/admin.py，追加即可）
现有接口不够用，管理员页需要全量分页：
1. `GET /api/admin/reviews?page=1&page_size=20&include_deleted=false`
   → 全库复核记录分页列表（现有 `/api/reviews/{record_id}` 只能按单条记录查）
2. `GET /api/admin/switch-logs?page=1&page_size=20&include_deleted=false`
   → 全库切换记录分页列表（现有接口要求 page:standard 权限，管理员页只认 action:manage_data）

要求：
- 都挂 `require_permission(P.ACTION_MANAGE_DATA)`
- 响应走 `ok()` 信封，分页结构参照 `GET /api/spheroidization` 的 `{items, total, page, page_size}`
- 行里必须带 `deleted_at / deleted_by / delete_reason`
- 复用现有仓储/UseCase，别新写 SQL（仓储已支持 include_deleted）
- 补 2 条测试：无权限 403、include_deleted 能拿到已删行

## B. 页面 Admin.vue（frontend/src/views/Admin.vue，新建）
四个 tab：**球化记录 / 检测标准 / 切换记录 / 复核记录**。每个 tab 独立分页（page_size=20）。

### 通用交互
- 每个 tab 右上角一个「显示已删除」开关（默认关）→ 打开时列表请求带 `include_deleted=true`
- 已删除行：整行降低不透明度 + 「已删除」标签，显示 `delete_reason` / `deleted_by` / `deleted_at`
- 删除：点「删除」弹窗要原因（必填，trim 后为空禁用确定）→ `POST .../delete {reason}`
- 恢复：已删除行显示「恢复」→ `POST .../restore`（无需原因）
- 操作成功/失败用现有 toast 机制（看 Spheroidization.vue 现在怎么提示，沿用，不要新造）

### Tab1 球化记录
- 列：检测时间 / 实际球化时长 / 判定 / 处理状态 / 删除状态 / 操作
- 操作：「标记已处理」或「撤销处理」（按当前 processed 显示）→ 弹窗要原因 →
  `POST /api/admin/records/{id}/processed {processed: 0|1, reason}`
- 数据源：`GET /api/spheroidization?page=&page_size=&include_deleted=`
- 处理状态列显示 `processed_by` + `processed_at`（有值时）

### Tab2 检测标准
- 列：ID / 球化时长 / 上下限 / 称重标准 / 创建时间 / 创建人 / 备注 / 状态 / 操作
- 数据源：`GET /api/standards/history?include_deleted=`
- 当前生效标准（`is_current` 字段或与 `/api/standards/current` 对比）**删除按钮禁用**，hover 提示「当前生效标准不能作废，请先切换」

### Tab3 标准切换记录
- 列：切换时间 / 原标准 / 新标准 / 操作人 / 原因 / 状态 / 操作
- 数据源：`GET /api/admin/switch-logs?page=&page_size=&include_deleted=`

### Tab4 球化复核记录
- 列：记录ID / 复核结果 / 复核人 / 复核时间 / 备注 / 状态 / 操作
- 数据源：`GET /api/admin/reviews?page=&page_size=&include_deleted=`

> ⚠️ 列表接口以 `app/api/admin.py` 实际实现的为准，前端按真实字段写，不许猜字段名。

## C. 用户管理页加权限勾选
`frontend/src/views/Users.vue`：权限勾选列表加一项「数据管理」（键 `action:manage_data`），
和现有页面/操作权限组放在一起（操作类），顺序放在 `action:manage_users` 前面。

## D. API 客户端
`frontend/src/api/` 里新增 admin 相关函数（按现有文件组织方式，不要全塞 index）：
`deleteRecord/restoreRecord/changeProcessed/deleteStandard/restoreStandard/deleteSwitchLog/restoreSwitchLog/deleteReview/restoreReview`
统一走现有 request 封装（带 token、统一信封处理）。

## E. 验收
- `cd frontend && npm run build` 必须成功（vue-tsc 类型检查 + vite）
- `cd .. && .venv/bin/python -m pytest tests/ -q` 全量必须通过（基线 273）
  - 注意 `tests/test_api_frontend_parity.py` 可能校验前端 API 调用与后端路由一致，新接口要同步登记
- 不许 git commit、不许提问、不许等确认
- 产出 TASK-9-RESULT.md：新增/改动文件清单、每个 tab 用的真实接口和字段、build 结果

## F. 风格（老板审美，硬要求）
- 沿用 `frontend/src/style.css` 的 :root token（米白纸底/墨字/发丝线/暗金强调），**禁止新增色值、禁止玻璃拟态、禁止渐变**
- 880px 内容中轴，卡片 1px 发丝描边，无圆角大阴影
- 中文宋体系标题、小标签大写疏排（照抄现有页面的 class）
