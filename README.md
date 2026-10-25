# 球化监测系统

浇注工位（AI 智能化）球化检测记录管理系统：上游 AI 设备负责"检"，本系统负责"记、查、核、管"。

## 快速开始

**后端**（项目根目录，Python 3）：

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0
```

- 后端地址：`http://127.0.0.1:8000`
- API 文档：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/api/health`

**前端**：

```bash
cd frontend
npm install
npm run dev
```

- 前端地址：`http://localhost:5173`
- Vite 已配置代理：`/api` → `127.0.0.1:8000`，`/api/video_feed` → `127.0.0.1:5080`（摄像头视频流）

**测试**（项目根目录）：

```bash
pytest
```

> 数据持久化在 `data/spheroidization.db`（SQLite）。重置数据：停掉后端，删除该文件后重启即可。

## 技术栈

| 端 | 技术 |
|---|---|
| 后端 | Python + FastAPI + Pydantic + SQLite（sqlite3 原生实现） |
| 前端 | Vue 3 + TypeScript + Vite + Vue Router |
| 测试 | Pytest（API 契约测试） |

## 系统页面

| 页面 | 路径 | 用途 |
|---|---|---|
| 浇注工位监控（首页） | `/` | 摄像头画面 + 最新 5 条检测数据 + 状态栏 |
| 首页统计 | `/records/home` | 总记录数 / 异常 / 已处理 / 未处理 |
| 球化记录 | `/records/spheroidization` | 记录列表、查询；确需补录时才新增记录 |
| 异常记录 | `/records/abnormal` | 只看机器判"异常"的记录，复核、处理 |
| 记录详情 | `/spheroidization/:id` | 亮光分析曲线、人工复核、标记已处理 |
| 检测标准 | `/records/standard` | 查看 / 创建 / 应用检测标准 |

## 核心业务规则

1. **机器检测结果不可修改**——人工复核结论单独保存，与机器结果并存、互不覆盖。
2. **复核与处理相互独立**——复核 ≠ 处理，两者独立操作、分别留痕。
3. **"标记为已处理"不可撤销**——一次性操作，点击前确认异常已实际处置完成。
4. **标准快照机制**——记录创建时保存当时生效的标准快照；新标准只影响之后的记录，历史记录的对比结果不变。
5. **记录由检测模块自动推送**——检测数据正常由上游检测模块自动写入系统，不需要人工录入；页面与 API 的新增功能仅用于特殊情况补录，非必要不要新增，以免产生重复记录、影响统计与追溯。

## API 一览

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/spheroidization` | 新增球化检测记录（自动保存标准快照）；正常由检测模块自动推送，仅特殊情况补录 |
| GET | `/api/spheroidization` | 记录列表（按结果 / 处理状态筛选，分页） |
| GET | `/api/spheroidization/abnormal` | 异常记录列表 |
| GET | `/api/spheroidization/stats` | 首页统计（总数 / 异常 / 已处理 / 未处理） |
| GET | `/api/spheroidization/{id}` | 记录详情（含复核记录） |
| GET | `/api/spheroidization/{id}/image` | 记录检测图片 |
| POST | `/api/spheroidization/{id}/process` | 标记为已处理 |
| POST | `/api/reviews` | 新增人工复核 |
| GET | `/api/reviews/{record_id}` | 某条记录的复核记录列表 |
| POST | `/api/standards` | 新增检测标准（立即生效） |
| GET | `/api/standards/current` | 当前生效标准 |
| GET | `/api/standards/history` | 标准历史版本 |
| POST | `/api/standards/{id}/apply` | 应用历史标准（只影响之后的记录） |
| GET | `/api/health` | 健康检查 |

完整接口字段说明见 [API接口总览.md](API接口总览.md)。

## 项目结构

```text
spheroidization-system/
├── app/                          # 后端（分层架构）
│   ├── api/                      # API 路由（spheroidization / review / standard）
│   ├── application/              # 用例（create / query / process / apply）
│   ├── domain/                   # 实体 + 仓储接口
│   ├── schemas/                  # Pydantic 请求 / 响应模型
│   ├── infrastructure/           # SQLite 数据库实现（schema.sql + sqlite.py）
│   ├── core/                     # 配置 / 日志 / 异常
│   └── main.py                   # 应用入口
├── frontend/                     # Vue 3 前端
│   └── src/views/                # Monitor / Home / Records / Spheroidization / Detail / Standard
├── tests/                        # Pytest 测试（API 契约 + 冒烟）
├── data/spheroidization.db       # SQLite 数据库
├── docx/                         # 培训手册（详细版存档 + 精简版一线操作）
├── API接口总览.md                 # 接口字段说明
├── 前端接口说明.md
└── 问题修复记录.md
```

## 相关文档

- [API接口总览.md](API接口总览.md)——接口与字段详细说明
- [前端接口说明.md](前端接口说明.md)——前端调用方式
- [问题修复记录.md](问题修复记录.md)——历史问题与修复记录
- `docx/`——《球化监测系统用户培训手册（详细版）》（项目存档）、《球化监测系统用户培训手册（精简版）》（一线操作工）
