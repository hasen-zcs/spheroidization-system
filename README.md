# 球化监测系统 · 正式版（2026-10-31 基线）

上游 AI 检测设备负责「检」，本系统负责「记、查、核、管」。

本目录是在老板提供的两份开发成果（后端更新包 / 前端更新包）基础上
整合、对齐契约、补迁移与自检后的正式版基线。

## 目录

```
app/           后端（FastAPI + 分层：api / application / domain / schemas / infrastructure / core）
frontend/      前端（Vue 3 + TS + Vite）
tests/         pytest（93 个用例：业务规则 + 账号权限 + 前后端契约）
scripts/       init_admin.py（首个管理员）/ migrate_db.py（旧库迁移）
data/          SQLite 库（不入库，运行时生成）
```

## 快速开始

```bash
# 依赖
pip install -r requirements.txt

# 全新部署：启动即建库
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1

# 老库升级：必须先迁移，不能直接换代码（启动自检会拦）
python scripts/migrate_db.py
python scripts/init_admin.py admin

# 前端开发
cd frontend && npm install && npm run dev     # 5173，代理到 8000
# 前端生产构建
cd frontend && npm run build                  # dist/
```

**必须 `--workers 1`**：会话存在进程内存里，多 worker 会随机 401、重启即掉线。

## 与旧版（2026-09 v1.2）的关键差异

1. 账号权限：9 个权限点（4 页面 + 5 动作），`UserAccount` / `UserPermission` 两表。
2. 温度拆表：主表不再存温度，新增 `TemperatureRecord` + `POST /api/temperature`。
3. 标准切换：`POST /api/standards/switch` + `GET /api/standards/switch-logs`（替代 `/{id}/apply`）。
4. 异常分类：主表新增 `abnormal_type`（1~6）/ `abnormal_reason`；球化三列放开 NULL。
5. 启动自检：表/列不齐直接报错退出，不再拖到第一个请求才 500。

## 契约兼容说明（2026-10-31）

两份开发成果的接口对不上，已在后端做兼容、前端做适配：

- 登录返回同时有扁平字段和 `user:{username,is_admin,permission_keys}`；
- 用户对象同时有 `permission_keys` 与 `permissions`；
- 切标准同时接受 `standard_id`（前端）与 `to_standard_record_id`（原生）；
- 切换日志返回分页对象 `{items,page,page_size}`，item 同时带原生字段与契约字段 + `summary`；
- 人工补录可随记录带 `temperature` / `temperature_time`（写入温度表，`gun_no=0` 表示人工）。

## 测试

```bash
pytest -q                     # 93 passed
cd frontend && npm run build  # 含 vue-tsc 类型检查
```

契约用例在 `tests/test_formal_contract.py`，改动接口字段时先看它。
