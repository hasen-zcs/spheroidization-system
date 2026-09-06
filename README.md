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

```
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

当前版本是：

**软件系统框架版本**

已经完成：

* 系统分层
* 核心业务模块划分
* Domain Entity 骨架
* Application UseCase 骨架
* Repository Interface
* API 路由骨架
* API Schema
* 统一异常处理
* 测试框架
* 项目开发规范
* 系统架构文档
* API 契约

当前暂未实现：

* 数据库
* Repository 具体实现
* 完整业务逻辑
* 上游检测模块接入
* 前端系统

目前本项目的数据为测试数据，我们没有设立数据库，所以我们之后需要设计数据库后接入

~~~

   当前：
   Mock 内存数据
      ↓
   未来：
   Repository Interface
      ↓
   数据库实现
~~~

---

## 3. 技术栈

当前框架：

```text
Python
FastAPI
Pydantic
Pytest
Uvicorn
```

数据库暂未确定。

---

## 4. 项目结构

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
│   └── core/
│       ├── config.py
│       ├── logger.py
│       └── exceptions.py
│
├── tests/
│
└── docs/
    ├── DEVELOPMENT.md
    ├── API.md
    └── ARCHITECTURE.md
```

---

## 5. 环境安装

建议使用虚拟环境。

### 创建虚拟环境

```bash
python -m venv .venv
```

### Windows

```bash
.venv\Scripts\activate
```

### Linux / macOS

```bash
source .venv/bin/activate
```

### 安装依赖

```bash
pip install fastapi uvicorn pytest
```

---

## 6. 启动项目

在项目根目录执行：

```bash
uvicorn app.main:app --reload
```

启动成功后：

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

## 7. 运行测试

在项目根目录执行：

```bash
pytest
```

---

## 8. 开发一个新业务功能

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

## 9. 当前核心业务对象

### StandardRecord

检测标准。

负责保存检测标准及其历史版本。

### SpheroidizationRecord

一次完整的球化检测结果。

包含：

* 机器检测事实
* 检测标准快照
* 处理状态

### ReviewRecord

一次人工复核记录。

用于保存：

* 人工复核结果
* 复核说明
* 复核人员
* 复核时间

---

## 10. 重要业务规则

### 原始机器结果不可修改

机器检测结果和人工复核结果必须分开保存。

---

### 复核与处理独立

是否存在人工复核记录，不决定是否已经处理。

---

### 标准采用历史版本

创建新标准时产生新的 StandardRecord。

旧标准保留。

---

### 历史记录保存标准快照

球化检测记录保存检测发生时使用的标准。

未来标准变化不会影响历史检测记录。

---

## 11. 开发人员应该先阅读什么

第一次接手项目时，推荐按照以下顺序阅读：

```text
README.md
   ↓
docs/ARCHITECTURE.md
   ↓
docs/DEVELOPMENT.md
   ↓
docs/API.md
   ↓
app/domain/
   ↓
app/application/
   ↓
app/api/
```

阅读完成后再开始编写业务代码。

---

## 12. 当前开发边界

当前框架暂时不处理：

* 数据库具体实现
* 上游检测模块通信方式
* 前端实现
* 多生产线管理
* 分布式架构
* 消息队列
* 缓存

这些功能在产生实际需求后再扩展。

---

## 13. 核心设计原则

```text
业务边界优先
职责清晰
依赖单向
事实不可篡改
历史可追溯
接口统一
不过度设计
```
