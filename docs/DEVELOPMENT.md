# 球化监测系统开发规范

## 1. 项目简介

本项目为球化监测业务系统，用于管理球化检测结果、历史记录、异常记录、人工复核以及检测标准。

系统接收上游检测模块产生的完整检测结果，并负责后续业务管理。

---

## 2. 项目目录

```text
app/
├── api/
├── application/
├── domain/
├── schemas/
└── core/

tests/
└── ...
```

### api

负责 HTTP 接口。

职责：

* 接收 HTTP 请求
* 参数校验
* 调用 Application 层
* 返回 HTTP 响应

API 层不直接编写核心业务逻辑。

---

### application

负责完整业务用例。

例如：

```text
CreateSpheroidizationUseCase
QuerySpheroidizationUseCase
ProcessSpheroidizationUseCase

CreateReviewUseCase
QueryReviewUseCase

CreateStandardUseCase
QueryStandardUseCase
```

一个 UseCase 对应一个明确的业务操作。

---

### domain

负责核心业务对象和业务规则。

当前核心业务对象：

```text
StandardRecord
SpheroidizationRecord
ReviewRecord
```

Domain 不依赖 FastAPI、数据库框架等具体技术。

---

### schemas

负责 API 数据模型。

用于定义：

* 请求参数
* 响应数据
* API 数据结构

Schema 不等同于 Domain Entity。

---

### core

存放系统级通用能力。

例如：

* 配置
* 日志
* 通用异常

---

## 3. 依赖规则

项目采用以下依赖方向：

```text
API
 ↓
Application
 ↓
Domain
 ↑
Repository Interface
 ↑
Infrastructure（未来实现）
```

具体规则：

1. API 可以调用 Application。
2. Application 可以调用 Domain。
3. Application 可以依赖 Repository Interface。
4. Domain 不依赖 API。
5. Domain 不依赖 FastAPI。
6. Domain 不直接操作数据库。
7. Infrastructure 负责实现 Repository Interface。
8. API 不直接操作数据库。

---

## 4. 业务对象

### StandardRecord

检测标准。

负责保存检测标准及其历史版本。

新标准创建后立即成为当前有效标准。

历史标准不能被新的标准覆盖。

---

### SpheroidizationRecord

一次完整的球化检测结果。

系统只接收已经完成的检测结果。

机器生成的原始检测事实创建后不可修改。

记录需要保存检测时使用的标准快照。

---

### ReviewRecord

人工复核记录。

人工复核不能修改原始机器检测结果。

一个球化记录可以存在多条复核记录。

复核记录当前采用追加方式创建，不直接修改或删除历史复核记录。

---

## 5. 重要业务规则

### 5.1 机器结果不可篡改

机器检测结果属于事实数据。

例如机器检测结果为：

```text
异常
```

人工认为：

```text
正常
```

不能直接把机器结果修改成正常。

应该保存：

```text
原始检测结果：异常
人工复核结果：正常
复核说明：人工判断原因
```

---

### 5.2 复核和处理是两个独立概念

复核完成不代表处理完成。

因此：

```text
是否存在复核记录
```

和：

```text
是否已处理
```

是两个独立状态。

工作人员可以在没有复核记录的情况下直接将记录标记为已处理。

---

### 5.3 标准采用历史记录方式保存

每次修改检测标准，都创建一个新的 StandardRecord。

例如：

```text
标准 A
   ↓
标准 B
   ↓
标准 C
```

标准 A、B 不删除。

最新标准 C 为当前有效标准。

已经产生的历史球化记录不因为标准 C 生效而发生变化。

---

### 5.4 检测标准快照

创建球化记录时，需要记录当时使用的检测标准。

例如：

```text
StandardRecord A
       ↓
检测发生
       ↓
SpheroidizationRecord
       ↓
保存 StandardRecord A 的标准快照
```

即使以后 StandardRecord A 不再是当前标准，该球化记录仍然能够知道当时使用的标准。

---

## 6. 新增业务代码的基本规则

新增业务功能时，按照以下顺序考虑：

```text
API
 ↓
UseCase
 ↓
Domain
 ↓
Repository Interface
```

如果需要数据库等具体技术实现，再由 Infrastructure 实现 Repository。

不要为了“结构完整”而创建没有实际职责的类。

---

## 7. 数据库

当前阶段暂不实现数据库。

数据库设计由后续负责数据库实现的开发人员根据最终业务模型完成。

当前代码只保留 Repository Interface。

---

## 8. 测试

测试代码统一放在：

```text
tests/
```

按照业务模块划分：

```text
tests/
├── test_spheroidization.py
├── test_review.py
└── test_standard.py
```

后续实现具体业务后，在对应测试文件中增加测试。

---

## 9. 当前开发原则

本项目优先保证：

1. 业务边界清晰
2. 模块职责明确
3. 依赖方向清晰
4. 接口稳定
5. 代码容易被其他开发人员接手

不为了使用设计模式而使用设计模式。

不为了增加目录而增加目录。

只有实际存在业务职责时，才增加新的模块或类。
