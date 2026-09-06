# 球化监测系统 API 契约

## 1. 球化检测记录

基础路径：

```text
/api/spheroidization
```

### 1.1 创建球化检测记录

```http
POST /api/spheroidization
```

用途：

接收一条已经完成的球化检测结果。

处理规则：

1. 获取当前有效检测标准。
2. 保存检测时使用的标准快照。
3. 创建 SpheroidizationRecord。
4. 原始机器检测结果创建后不可修改。

请求：

```json
{
    "detection_time": "2026-09-06T10:00:00",
    "iron_water_weight": 1500.0,
    "spheroidization_start_time": "2026-09-06T10:01:00",
    "spheroidization_end_time": "2026-09-06T10:01:30",
    "actual_spheroidization_time": 30.0,
    "actual_entry_length": 2.5,
    "machine_result": "正常",
    "spheroidization_abnormal": false,
    "entry_abnormal": false
}
```

---

### 1.2 查询球化检测记录

```http
GET /api/spheroidization
```

用途：

查询历史球化检测记录。

支持：

* 正常/异常筛选
* 已处理/未处理筛选
* 后续可增加时间范围等查询条件

---

### 1.3 查询异常记录

```http
GET /api/spheroidization/abnormal
```

用途：

只查询异常球化检测记录。

---

### 1.4 查询单条记录

```http
GET /api/spheroidization/{record_id}
```

用途：

查询指定球化检测记录的详细信息。

---

### 1.5 标记处理完成

```http
POST /api/spheroidization/{record_id}/process
```

请求：

```json
{
    "processed_by": "worker01"
}
```

规则：

* 只修改处理状态。
* 不修改机器检测结果。
* 不要求必须存在 ReviewRecord。
* 处理状态与人工复核独立。

---

# 2. 人工复核

基础路径：

```text
/api/reviews
```

### 2.1 创建复核记录

```http
POST /api/reviews
```

请求：

```json
{
    "spheroidization_record_id": 10001,
    "review_result": "正常",
    "review_remark": "人工确认检测结果正常",
    "reviewer": "worker01"
}
```

规则：

* 指定的球化记录必须存在。
* 创建新的 ReviewRecord。
* 不修改原始机器检测结果。
* 不删除历史复核记录。

---

### 2.2 查询复核记录

```http
GET /api/reviews/{record_id}
```

用途：

查询指定球化检测记录的复核历史。

注意：

`record_id` 表示：

```text
SpheroidizationRecord.id
```

---

# 3. 检测标准

基础路径：

```text
/api/standards
```

### 3.1 创建新标准

```http
POST /api/standards
```

请求：

```json
{
    "standard_spheroidization_time": 30.0,
    "standard_entry_length": 2.5,
    "weighing_standard": 1500.0,
    "created_by": "worker01",
    "remark": "调整球化时间标准"
}
```

规则：

* 每次创建产生新的 StandardRecord。
* 新标准立即成为当前有效标准。
* 历史标准保留。
* 不修改历史球化检测记录。

---

### 3.2 查询当前标准

```http
GET /api/standards/current
```

用途：

获取当前正在生效的检测标准。

---

### 3.3 查询标准历史

```http
GET /api/standards/history
```

用途：

获取历史检测标准。

---

# 4. 健康检查

```http
GET /api/health
```

正常响应：

```json
{
    "code": 200,
    "message": "success",
    "data": {
        "status": "running"
    }
}
```

---

# 5. 统一响应格式

所有正常业务接口统一采用：

```json
{
    "code": 200,
    "message": "success",
    "data": {}
}
```

业务异常：

```json
{
    "code": 400,
    "message": "业务错误信息",
    "data": null
}
```

---

# 6. API 与业务用例对应关系

```text
POST /api/spheroidization
        ↓
CreateSpheroidizationUseCase

GET /api/spheroidization
        ↓
QuerySpheroidizationUseCase

GET /api/spheroidization/abnormal
        ↓
QuerySpheroidizationUseCase

GET /api/spheroidization/{record_id}
        ↓
QuerySpheroidizationUseCase

POST /api/spheroidization/{record_id}/process
        ↓
ProcessSpheroidizationUseCase


POST /api/reviews
        ↓
CreateReviewUseCase

GET /api/reviews/{record_id}
        ↓
QueryReviewUseCase


POST /api/standards
        ↓
CreateStandardUseCase

GET /api/standards/current
        ↓
QueryStandardUseCase

GET /api/standards/history
        ↓
QueryStandardUseCase
```

---

# 7. API 开发原则

API 层只负责：

```text
HTTP请求
 ↓
参数解析
 ↓
Schema校验
 ↓
调用UseCase
 ↓
返回响应
```

API 不负责：

* 数据库操作
* 核心业务判断
* 修改 Domain 数据
* 编写复杂业务流程
