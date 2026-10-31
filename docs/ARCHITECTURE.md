# 球化监测系统架构与业务设计

## 1. 系统定位

球化监测系统用于管理球化检测完成后的业务数据。

系统主要负责：

* 保存球化检测结果
* 查询历史检测记录
* 查询异常检测记录
* 人工复核检测记录
* 标记检测记录是否已经处理
* 管理检测标准

系统不负责球化检测算法本身。

---

## 2. 系统边界

### 上游检测模块负责

* 摄像头/视频采集
* ROI 区域处理
* 图像分析
* 亮度分析
* 球化时间检测
* 进线长度检测
* 球化结果判断
* 铁水重量等检测数据产生

上游模块产生完整检测结果后，交给本系统。

---

### 本系统负责

```text
检测结果
    ↓
球化记录
    ↓
查询 / 异常查看
    ↓
人工复核
    ↓
处理状态管理
```

本阶段不定义上游检测模块与本系统之间的具体通信方式。

该部分作为外部输入边界处理。

---

## 3. 系统核心业务对象

系统当前有三个核心业务对象：

```text
StandardRecord
SpheroidizationRecord
ReviewRecord
```

---

## 4. StandardRecord

表示一个检测标准版本。

标准不是一个被不断修改的单一对象。

每次产生新标准时：

```text
旧标准
   ↓
保留历史
   ↓
创建新 StandardRecord
   ↓
新 StandardRecord 成为当前标准
```

因此系统同时存在：

* 当前标准
* 历史标准

---

## 5. SpheroidizationRecord

表示一次已经完成的球化检测。

一个检测事件对应一个 SpheroidizationRecord。

记录由三部分组成：

```text
机器检测事实
+
检测标准快照
+
处理状态
```

### 机器检测事实

来自上游检测模块。

例如：

* 检测时间
* 铁水重量
* 球化开始时间
* 球化结束时间
* 实际球化时间
* 实际进线长度
* 机器检测结果
* 球化异常状态
* 进线异常状态

这些数据创建后原则上不可修改。

---

### 检测标准快照

创建球化记录时，系统获取当时的当前标准，并保存标准快照。

例如：

```text
当前标准 A
    ↓
发生球化检测
    ↓
SpheroidizationRecord
    ↓
保存标准 A 的快照
```

以后即使当前标准变成 B，该历史球化记录仍然使用标准 A 的快照。

---

### 处理状态

记录工作人员是否已经处理。

```text
processed
processed_at
processed_by
```

处理状态与人工复核相互独立。

---

## 6. ReviewRecord

表示一次人工复核行为。

一个球化记录可以存在多个 ReviewRecord：

```text
SpheroidizationRecord
        │
        ├── ReviewRecord
        ├── ReviewRecord
        └── ReviewRecord
```

每一次人工复核都作为新的记录保存。

ReviewRecord 不修改原始机器检测结果。

---

## 7. 机器结果与人工结果

系统必须区分：

```text
机器检测结果
人工复核结果
```

例如：

```text
机器检测：
异常

人工复核：
正常

复核说明：
人工确认检测结果正常
```

最终数据中应该同时存在两种判断。

禁止通过修改机器结果的方式保存人工判断。

核心原则：

> 机器生成的事实不可篡改；人的判断和处理可以追加。

---

## 8. 复核与处理

复核和处理是两个独立概念。

### 复核

表示工作人员对检测结果进行了人工判断。

产生：

```text
ReviewRecord
```

### 处理

表示工作人员已经对这条业务记录进行了处理。

修改：

```text
SpheroidizationRecord.processed
```

两者不存在强制先后关系。

例如：

```text
情况 A：

检测记录
   ↓
人工复核
   ↓
处理完成
```

也允许：

```text
情况 B：

检测记录
   ↓
直接处理完成
```

因此：

```text
ReviewRecord 是否存在
```

不能作为：

```text
processed
```

的判断依据。

---

## 9. 核心业务流程

### 9.1 创建球化记录

```text
上游检测模块
      ↓
完整检测结果
      ↓
CreateSpheroidizationUseCase
      ↓
获取当前 StandardRecord
      ↓
复制标准快照
      ↓
创建 SpheroidizationRecord
      ↓
Repository.save()
```

---

### 9.2 人工复核

```text
工作人员
    ↓
提交复核
    ↓
CreateReviewUseCase
    ↓
检查 SpheroidizationRecord 是否存在
    ↓
创建 ReviewRecord
    ↓
Repository.save()
```

原机器检测结果不修改。

---

### 9.3 标记处理

```text
工作人员
    ↓
标记处理完成
    ↓
ProcessSpheroidizationUseCase
    ↓
找到 SpheroidizationRecord
    ↓
修改处理状态
```

不要求存在 ReviewRecord。

---

### 9.4 修改检测标准

```text
工作人员
    ↓
提交新标准
    ↓
CreateStandardUseCase
    ↓
创建新的 StandardRecord
    ↓
成为当前有效标准
```

旧标准继续保留。

历史球化记录不修改。

---

## 10. 系统分层

系统采用：

```text
API
 ↓
Application
 ↓
Domain
 ↓
Repository Interface
```

未来：

```text
Repository Interface
        ↑
Infrastructure
        ↓
数据库
```

---

## 11. API 层

负责：

* HTTP 请求
* 参数接收
* Schema 校验
* 调用 UseCase
* 返回响应

不负责核心业务逻辑。

---

## 12. Application 层

Application 层以业务用例为单位组织代码。

当前用例：

```text
CreateSpheroidizationUseCase
QuerySpheroidizationUseCase
ProcessSpheroidizationUseCase

CreateReviewUseCase
QueryReviewUseCase

CreateStandardUseCase
QueryStandardUseCase
```

Application 负责组织完整业务流程。

---

## 13. Domain 层

Domain 层负责：

* 核心业务对象
* 核心业务规则
* Repository 接口

Domain 不依赖：

* FastAPI
* SQLAlchemy
* MySQL
* HTTP
* 具体数据库

---

## 14. Repository

Repository 是持久化抽象。

当前只定义接口：

```text
SpheroidizationRepository
ReviewRepository
StandardRepository
```

当前阶段不实现数据库。

未来由 Infrastructure 实现。

---

## 15. 数据库设计边界

当前阶段不设计数据库表。

数据库开发人员需要根据：

* Domain Entity
* API Schema
* Repository Interface
* 业务规则

完成具体数据库设计。

数据库设计不能反过来改变已经确定的业务边界。

---

## 16. 当前架构原则

系统遵循以下原则：

### 原则一：业务优先

代码结构服务于业务，而不是为了使用某种设计模式。

### 原则二：事实与判断分离

机器检测事实与人工判断不能混为一谈。

### 原则三：历史数据可追溯

标准变化不能影响历史检测记录。

人工复核采用追加记录方式。

### 原则四：模块职责明确

每一层只负责自己的事情。

### 原则五：暂不进行过度设计

当前没有实际业务需求的：

* 复杂领域服务
* 事件总线
* 消息队列
* 缓存系统
* 微服务拆分

暂不加入。

后续出现实际需求时再进行扩展。
