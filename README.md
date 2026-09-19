# 球化监测系统

## 1. 项目简介

球化监测系统用于管理球化检测完成后的业务数据。

系统主要提供：

* 球化检测记录管理
* 历史记录查询
* 异常记录查询
* 人工复核
* 处理状态管理
* 检测标准管理

上游检测模块负责实际检测和结果产生，本系统负责检测结果进入业务系统后的管理。
### 启动服务
启动后端：

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

启动前端：

```bash
cd frontend
npm install
npm run dev
npm run dev -- --host 0.0.0.0 --port 3000
```

然后访问：

```text
http://localhost:5173
```

即可进行完整业务流程测试。

系统整体架构：

```text
                    球化监测系统
                         │
        ┌────────────────┼────────────────┐
        ↓                ↓                ↓
   球化检测记录       人工复核          检测标准
        │                │                │
        └────────────────┼────────────────┘
                         ↓
                        API
                         ↓
                   Application
                         ↓
                      Domain
                         ↓
               Repository Interface
                         ↓
                   Infrastructure
                  （后续实现）
                         ↓
                       数据库
                  （后续实现）
```

---

## 2. 当前项目状态

当前版本为：

**软件系统框架版本**

目前已经完成：

* 系统分层
* 核心业务模块划分
* Domain Entity 骨架
* Application UseCase 骨架
* Repository Interface
* API 路由
* API Schema
* 统一异常处理
* Mock 测试数据
* 前端页面
* 前后端 API 联调
* 测试框架
* 项目开发规范
* 系统架构文档
* API 契约
* 前端开发文档
* 开发人员入门文档

当前暂未实现：

* 数据库
* Repository 具体实现
* 上游检测模块正式接入
* 生产环境部署

目前项目使用 **Mock 内存数据** 模拟数据库行为，用于完成框架开发、前后端联调和业务流程验证。

后续数据库设计完成后，将通过 Repository 层替换 Mock 数据。

```text
当前：

Frontend
   ↓
HTTP API
   ↓
FastAPI
   ↓
Mock 内存数据
   ↓
JSON


未来：

Frontend
   ↓
HTTP API
   ↓
Application
   ↓
Domain
   ↓
Repository Interface
   ↓
Repository 实现
   ↓
数据库
```

---

# 3. 技术栈

## 后端

```text
Python
FastAPI
Pydantic
Pytest
Uvicorn
```

## 前端

```text
Vue 3
TypeScript
Vite
Vue Router
Fetch API
```

## 数据库

当前暂未确定。

当前版本不依赖数据库即可运行。

---

# 4. 项目结构

```text
project/
│
├── app/
│   ├── main.py
│   │
│   ├── api/
│   │   ├── spheroidization.py
│   │   ├── review.py
│   │   └── standard.py
│   │
│   ├── application/
│   │   ├── spheroidization/
│   │   ├── review/
│   │   └── standard/
│   │
│   ├── domain/
│   │   ├── spheroidization/
│   │   ├── review/
│   │   └── standard/
│   │
│   ├── schemas/
│   │   ├── common.py
│   │   ├── spheroidization.py
│   │   ├── review.py
│   │   └── standard.py
│   │
│   ├── core/
│   │   ├── config.py
│   │   ├── logger.py
│   │   └── exceptions.py
│   │
│   └── mock/
│       ├── spheroidization.py
│       ├── review.py
│       └── standard.py
│
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   │   └── index.ts
│   │   ├── router/
│   │   │   └── index.ts
│   │   ├── views/
│   │   │   ├── Home.vue
│   │   │   ├── Spheroidization.vue
│   │   │   ├── SpheroidizationDetail.vue
│   │   │   └── Standard.vue
│   │   ├── App.vue
│   │   ├── main.ts
│   │   └── style.css
│   │
│   ├── package.json
│   └── vite.config.ts
│
├── tests/
│
└── docs/
    ├── DEVELOPMENT.md
    ├── API.md
    ├── ARCHITECTURE.md
    ├── FRONTEND.md
    └── GETTING_STARTED.md
```

---

# 5. Mock 测试数据

当前项目没有数据库，因此后端使用内存中的 Mock 数据模拟数据库。

Mock 数据位于：

```text
app/mock/
├── spheroidization.py
├── review.py
└── standard.py
```

分别对应：

```text
spheroidization.py
    ↓
球化检测记录

review.py
    ↓
人工复核记录

standard.py
    ↓
检测标准记录
```

---

## 5.1 球化检测 Mock 数据

文件：

```text
app/mock/spheroidization.py
```

当前预置 **5 条球化检测记录**。

数据用于模拟：

```text
正常记录
异常记录
已处理记录
未处理记录
```

示例：

```text
ID    检测结果    异常       处理状态
1     正常        否         已处理
2     异常        是         未处理
3     正常        否         未处理
4     异常        是         已处理
5     正常        否         已处理
```

每条球化检测记录同时包含：

```text
检测时间
铁水重量
球化开始时间
球化结束时间
实际球化时间
实际入料长度
机器检测结果
球化异常判断
入料异常判断
检测标准快照
处理状态
处理时间
处理人员
```

---

## 5.2 人工复核 Mock 数据

文件：

```text
app/mock/review.py
```

当前预置 **3 条人工复核记录**。

用于模拟：

```text
机器检测异常
        ↓
人工复核
        ↓
人工判断结果
```

例如：

```text
球化记录 ID = 2

机器检测结果：
异常

人工复核结果：
正常

复核说明：
检测过程中存在短暂光照波动，
实际球化效果正常。
```

这个数据用于验证：

> **机器检测结果和人工复核结果可以同时存在，并且互不覆盖。**

---

## 5.3 检测标准 Mock 数据

文件：

```text
app/mock/standard.py
```

当前预置 **3 条检测标准记录**。

例如：

```text
ID    球化时间    入料长度    称重标准
1       60          120        1500
2       65          125        1500
3       70          130        1500
```

最新创建的标准作为当前有效标准。

例如：

```text
当前标准 = ID 3
```

创建新标准：

```text
ID 4
```

则：

```text
当前标准 = ID 4
```

旧标准不会被删除。

---

# 6. Mock 数据的生命周期

Mock 数据存储在 Python 进程内存中。

因此：

```text
启动 FastAPI
      ↓
加载 app/mock/ 中的初始数据
      ↓
运行系统
      ↓
新增 / 修改数据
      ↓
数据保存在内存
```

但是重新启动后端：

```text
停止 FastAPI
      ↓
重新启动 FastAPI
      ↓
重新加载 app/mock/
      ↓
恢复初始测试数据
```

因此当前版本：

> **Mock 数据不具备持久化能力。**

这是当前框架的正常设计，不属于系统故障。

---

# 7. 使用 Mock 数据进行开发

开发人员可以直接启动项目，不需要安装数据库。

启动后端：

```bash
uvicorn app.main:app --reload
```

启动前端：

```bash
cd frontend
npm install
npm run dev
```

然后访问：

```text
http://localhost:5173
```

即可进行完整业务流程测试。

---

# 8. 当前业务流程测试

可以按照以下流程验证系统：

```text
检测标准
    ↓
新增标准
    ↓
新标准立即生效
    ↓
新增球化检测记录
    ↓
自动保存检测时标准快照
    ↓
查询球化记录
    ↓
查看球化详情
    ↓
人工复核
    ↓
标记处理
    ↓
首页查看统计
```

重点验证：

### 标准立即生效

新增标准后，新创建的球化记录必须使用新标准。

### 历史标准不受影响

旧球化记录仍然保存创建时使用的标准快照。

### 人工复核不修改机器结果

机器结果：

```text
异常
```

人工复核：

```text
正常
```

两者同时保留。

### 复核与处理相互独立

存在人工复核记录并不代表该记录已经处理。

---

# 9. 环境安装

建议使用虚拟环境。

## 创建虚拟环境

```bash
python -m venv .venv
```

## Windows

```bash
.venv\Scripts\activate
```

## Linux / macOS

```bash
source .venv/bin/activate
```

## 安装后端依赖

```bash
pip install fastapi uvicorn pytest
```

前端依赖：

```bash
cd frontend
npm install
```

---

# 10. 启动项目

## 启动后端

在项目根目录执行：

```bash
uvicorn app.main:app --reload
```

后端地址：

```text
http://127.0.0.1:8000
```

API 文档：

```text
http://127.0.0.1:8000/docs
```

健康检查：

```text
http://127.0.0.1:8000/api/health
```

---

## 启动前端

进入：

```bash
cd frontend
```

执行：

```bash
npm run dev
```

前端地址：

```text
http://localhost:5173
```

---

# 11. 运行测试

后端测试：

```bash
pytest
```

前端生产构建：

```bash
cd frontend
npm run build
```

生产构建成功说明：

```text
TypeScript 类型检查通过
Vue 编译通过
Vite 构建通过
```

---

# 12. API

主要 API：

```text
POST   /api/spheroidization
GET    /api/spheroidization
GET    /api/spheroidization/abnormal
GET    /api/spheroidization/{record_id}
POST   /api/spheroidization/{record_id}/process

POST   /api/reviews
GET    /api/reviews/{record_id}

POST   /api/standards
GET    /api/standards/current
GET    /api/standards/history

GET    /api/health
```

完整接口说明：

```text
docs/API.md
```

---

# 13. 开发一个新业务功能

按照以下顺序进行：

```text
1. 明确业务规则
        ↓
2. Domain
        ↓
3. Application UseCase
        ↓
4. Repository Interface
        ↓
5. Schema
        ↓
6. API
        ↓
7. Infrastructure
        ↓
8. Test
```

不要直接在 API 函数里面编写完整业务逻辑。

---

# 14. 当前核心业务对象

## StandardRecord

检测标准。

负责保存检测标准及其历史版本。

---

## SpheroidizationRecord

一次完整的球化检测结果。

包含：

* 机器检测事实
* 检测标准快照
* 处理状态

---

## ReviewRecord

一次人工复核记录。

用于保存：

* 人工复核结果
* 复核说明
* 复核人员
* 复核时间

---

# 15. 重要业务规则

## 原始机器结果不可修改

机器检测结果和人工复核结果必须分开保存。

```text
机器检测结果
      +
人工复核结果
```

不能使用人工复核结果覆盖机器原始结果。

---

## 复核与处理独立

```text
是否复核
    ≠
是否处理
```

一条记录可以：

```text
未复核 + 已处理
```

也可以：

```text
已复核 + 未处理
```

---

## 标准采用历史版本

创建新标准时：

```text
新增 StandardRecord
```

而不是修改旧标准。

旧标准必须保留。

---

## 历史记录保存标准快照

球化检测记录保存检测发生时使用的标准。

未来标准变化不会影响历史检测记录。

---

# 16. 当前开发边界

当前框架暂时不处理：

* 数据库具体实现
* Repository 具体实现
* 上游检测模块通信方式
* 多生产线管理
* 分布式架构
* 消息队列
* 缓存
* 权限系统
* 用户管理

这些功能在产生实际需求后再扩展。

---

# 17. 数据库后续设计

当前版本没有数据库。

后续数据库设计应以核心业务实体为基础。

当前确定的核心实体：

```text
StandardRecord
        │
        │ 标准快照
        ↓
SpheroidizationRecord
        │
        │ 1 : N
        ↓
ReviewRecord
```

数据库设计流程：

```text
业务实体
    ↓
实体字段
    ↓
字段类型
    ↓
主键 / 外键
    ↓
索引
    ↓
数据库表
    ↓
Repository 实现
```

数据库具体设计另行维护。

---

# 18. 开发人员应该先阅读什么

第一次接手项目时，推荐按照以下顺序阅读：

```text
README.md
    ↓
docs/GETTING_STARTED.md
    ↓
docs/ARCHITECTURE.md
    ↓
docs/DEVELOPMENT.md
    ↓
docs/API.md
    ↓
docs/FRONTEND.md
    ↓
app/domain/
    ↓
app/application/
    ↓
app/api/
    ↓
app/mock/
```

阅读完成后再开始编写业务代码。

---

# 19. 核心设计原则

```text
业务边界优先

职责清晰

依赖单向

事实不可篡改

历史可追溯

接口统一

前后端分离

Mock 与真实数据源解耦

不过度设计
```

---

# 20. 当前系统定位

当前系统不是最终生产版本。

当前版本的主要目标是：

> **建立一个结构清晰、业务边界明确、前后端可以运行、API 契约明确、能够被其他开发人员继续扩展的软件系统框架。**

当前：

```text
              ┌──────────────┐
              │    前端       │
              └──────┬───────┘
                     ↓
                HTTP API
                     ↓
              ┌──────────────┐
              │   FastAPI    │
              └──────┬───────┘
                     ↓
              Application
                     ↓
                 Domain
                     ↓
          Repository Interface
                     ↓
              ┌──────────────┐
              │ Mock 数据     │
              └──────────────┘
```

未来：

```text
              ┌──────────────┐
              │    前端       │
              └──────┬───────┘
                     ↓
                HTTP API
                     ↓
              Application
                     ↓
                 Domain
                     ↓
          Repository Interface
                     ↓
          Repository 实现
                     ↓
                数据库
```

上游检测模块未来接入：

```text
上游检测模块
      ↓
完整检测结果
      ↓
球化监测系统
      ↓
SpheroidizationRecord
```

上游检测模块的具体通信方式不属于当前框架设计范围。
