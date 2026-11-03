# 球化监测系统 API 接口总览

更新时间：2026-09-27  
服务地址：`http://127.0.0.1:8000`  
交互式文档：`http://127.0.0.1:8000/docs`

## 一、通用约定

### 1. 响应信封

除图片二进制接口成功响应外，所有接口统一返回：

```json
{
  "code": 200,
  "message": "success",
  "data": {}
}
```

业务失败通常仍使用 HTTP 200，前端应以 `body.code` 判断成功或失败：

| body.code | 含义 | data |
| --- | --- | --- |
| 200 | 成功 | 对象、数组或 null |
| 400 | 业务规则不通过、数据库约束失败 | null |
| 404 | 查询对象不存在、应用标准不存在 | null |
| 422 | 请求参数不合法、字段缺失、字段类型错误 | null |

### 2. 请求字段约束

- 请求模型默认禁止未定义字段，发送多余字段会返回 `code 422`。
- 时间字段使用字符串，推荐格式：`YYYY-MM-DD HH:MM:SS`。
- 后端不会替调用方补零或转换时间格式，调用方必须保持格式一致。
- 数据库中的 0/1 状态在响应中转换为 `true` / `false`。
- 数据库中的复核结果 0/1 在响应中转换为 `"正常"` / `"异常"`。

### 3. 图片数据

- 新增球化记录时，`spheroidization_image` 使用纯 Base64 字符串。
- 不要带 `data:image/jpeg;base64,` 前缀。
- 前端当前使用 JPG/JPEG 文件，读取文件后去除 Data URL 前缀再提交。
- 后端将 Base64 解码为 bytes，以 BLOB 存入数据库。
- 列表接口不返回图片。
- 详情接口返回图片 Base64。
- 图片二进制接口直接返回图片内容，适合 `<img>` 使用。

---

## 二、接口索引

| 方法 | 路径 | 功能 |
| --- | --- | --- |
| GET | `/api/health` | 服务健康检查 |
| POST | `/api/standards` | 新增检测标准并自动应用 |
| GET | `/api/standards/current` | 获取当前应用标准，无需标准 ID |
| GET | `/api/standards/history` | 获取全部标准历史 |
| POST | `/api/standards/{standard_id}/apply` | 应用指定的历史标准或当前标准 |
| POST | `/api/spheroidization` | 新增球化检测记录 |
| GET | `/api/spheroidization` | 分页查询球化记录 |
| GET | `/api/spheroidization/abnormal` | 分页查询异常记录 |
| GET | `/api/spheroidization/stats` | 获取球化记录统计 |
| GET | `/api/spheroidization/{record_id}` | 获取球化记录详情 |
| GET | `/api/spheroidization/{record_id}/image` | 获取球化记录图片 |
| POST | `/api/spheroidization/{record_id}/process` | 人工处置球化记录 |
| POST | `/api/reviews` | 新增人工复核 |
| GET | `/api/reviews/{record_id}` | 获取某条球化记录的全部复核 |

---

## 三、健康检查

### `GET /api/health`

功能：检查后端服务是否运行。

成功响应：

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

## 四、检测标准

### 1. `POST /api/standards`

功能：新增一条检测标准。

业务规则：

- 标准表只增不改。
- 新增成功后自动成为当前应用标准。
- 当前应用标准 ID 写入 `data/active_standard.json`。
- 历史标准不会被修改。

请求体：

```json
{
  "standard_spheroidization_time": 70,
  "standard_spheroidization_time_upper": 75,
  "standard_spheroidization_time_lower": 65,
  "weighing_standard": 1500,
  "created_by": "张三",
  "remark": "调整标准"
}
```

请求字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| standard_spheroidization_time | number | 是 | 标准球化时间，必须大于 0 |
| standard_spheroidization_time_upper | number \| null | 否 | 标准球化时间上限，填写时必须大于 0 |
| standard_spheroidization_time_lower | number \| null | 否 | 标准球化时间下限，填写时必须大于 0 |
| weighing_standard | number | 是 | 称重标准 |
| created_by | string | 是 | 创建人 |
| remark | string | 否 | 备注，默认空字符串 |

成功响应 `data`：标准对象。

### 2. `GET /api/standards/current`

功能：获取当前应用的标准。

重要：

- 该接口不需要标准 ID。
- 外部系统仍使用原来的接口获取标准，不需要改成带 `{id}` 的路径。
- 当前标准由 `data/active_standard.json` 中的 `standard_record_id` 决定。
- 文件缺失或 ID 无效时，兼容回退到最大 ID 的标准。

成功响应：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 3,
    "standard_spheroidization_time": 70,
    "standard_spheroidization_time_upper": 75,
    "standard_spheroidization_time_lower": 65,
    "weighing_standard": 1500,
    "created_at": "2026-09-27 10:00:00",
    "created_by": "张三",
    "remark": "调整标准"
  }
}
```

没有任何标准时：

```json
{
  "code": 200,
  "message": "success",
  "data": null
}
```

### 3. `GET /api/standards/history`

功能：获取全部标准历史。

成功响应 `data`：标准对象数组，按标准 ID 升序。

```json
{
  "code": 200,
  "message": "success",
  "data": []
}
```

标准对象：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | number | 标准 ID |
| standard_spheroidization_time | number | 标准球化时间 |
| standard_spheroidization_time_upper | number \| null | 上限 |
| standard_spheroidization_time_lower | number \| null | 下限 |
| weighing_standard | number | 称重标准 |
| created_at | string \| null | 创建时间 |
| created_by | string | 创建人 |
| remark | string \| null | 备注 |

### 4. `POST /api/standards/{standard_id}/apply`

功能：把指定标准设置为当前应用标准。

- 可以是当前标准。
- 可以是任意历史标准。
- 应用后只影响之后创建的球化记录。
- 历史球化记录的标准快照不会被修改。
- 应用状态会持久化到 `data/active_standard.json`。
- 服务重启后仍然保持。
- 找不到指定标准时返回 `code 404`。

路径参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| standard_id | number | 要应用的标准 ID |

无请求体。

成功响应：

```json
{
  "code": 200,
  "message": "标准应用成功",
  "data": {
    "id": 1,
    "standard_spheroidization_time": 65,
    "standard_spheroidization_time_upper": 70,
    "standard_spheroidization_time_lower": 60,
    "weighing_standard": 1500,
    "created_at": "2026-09-20 09:00:00",
    "created_by": "张三",
    "remark": "历史标准"
  }
}
```

---

## 五、球化检测记录

### 1. `POST /api/spheroidization`

功能：新增一条球化检测记录。

业务规则：

- 必须存在当前应用标准。
- 新增时保存当前标准 ID 和标准球化时间快照。
- 当前标准不存在时返回 `code 400`。
- 请求中的未知字段会被拒绝。
- `spheroidization_image` 可以为空。

请求体：

```json
{
  "detection_time": "2026-09-27 08:00:00",
  "spheroidization_start_time": "2026-09-27 08:00:05",
  "spheroidization_end_time": "2026-09-27 08:01:10",
  "actual_spheroidization_time": 65,
  "spheroidization_abnormal": false,
  "spheroidization_temperature": 1520,
  "spheroidization_temperature_time": "2026-09-27 08:00:10",
  "spheroidization_wire_entry_start_time": "2026-09-27 08:00:20",
  "spheroidization_wire_entry_end_time": "2026-09-27 08:01:30",
  "spheroidization_wire_entry_total_duration": 70,
  "spheroidization_weight": 1600,
  "spheroidization_image": "/9j/4AAQ..."
}
```

请求字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| detection_time | string | 是 | 检测时间 |
| spheroidization_start_time | string | 是 | 球化开始时间 |
| spheroidization_end_time | string | 是 | 球化结束时间 |
| actual_spheroidization_time | number | 是 | 实际球化时间 |
| spheroidization_abnormal | boolean \| null | 否 | 机器判定是否异常，null 表示机器没给判定 |
| spheroidization_temperature | number | 是 | 铁水温度 |
| spheroidization_temperature_time | string | 是 | 测温时间 |
| spheroidization_wire_entry_start_time | string | 是 | 进线开始时间 |
| spheroidization_wire_entry_end_time | string | 是 | 进线结束时间 |
| spheroidization_wire_entry_total_duration | number | 是 | 实际进线时间 |
| spheroidization_weight | number | 是 | 铁水重量 |
| spheroidization_image | string \| null | 否 | JPG/JPEG 图片 Base64，不带 Data URL 前缀 |

成功响应 `data`：球化记录对象，不包含图片。

### 2. `GET /api/spheroidization`

功能：分页查询球化记录。

查询参数：

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| page | number | 1 | 页码，最小 1 |
| page_size | number | 20 | 每页数量，范围 1 到 200 |
| abnormal | boolean | 无 | true 只查异常；false 查正常和未判定 |
| processed | boolean | 无 | true 已处理；false 未处理 |

成功响应 `data`：分页对象。

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "items": [],
    "total": 0,
    "page": 1,
    "page_size": 20,
    "has_more": false
  }
}
```

记录按 ID 倒序返回，最新的在前。

### 3. `GET /api/spheroidization/abnormal`

功能：分页查询机器判定为异常的记录。

查询参数：

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| page | number | 1 | 页码 |
| page_size | number | 20 | 每页数量，范围 1 到 200 |

返回结构与 `GET /api/spheroidization` 相同。

### 4. `GET /api/spheroidization/stats`

功能：获取球化记录统计。

成功响应：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 100,
    "abnormal": 8,
    "processed": 90,
    "unprocessed": 10
  }
}
```

统计字段：

| 字段 | 说明 |
| --- | --- |
| total | 全部记录数 |
| abnormal | 机器判定异常记录数 |
| processed | 已处理记录数 |
| unprocessed | 未处理记录数 |

### 5. `GET /api/spheroidization/{record_id}`

功能：获取单条球化记录详情。

路径参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| record_id | number | 球化记录 ID |

成功响应 `data`：球化记录对象，比列表多一个 `spheroidization_image` 字段。

当记录不存在时：

```json
{
  "code": 404,
  "message": "记录不存在",
  "data": null
}
```

### 6. `GET /api/spheroidization/{record_id}/image`

功能：获取球化记录图片。

成功响应特点：

- 响应体不是 JSON，而是图片二进制。
- `Content-Type` 根据文件头识别。
- JPG 返回 `image/jpeg`。
- PNG 返回 `image/png`。
- 响应头包含 `Cache-Control: public, max-age=86400`。

记录不存在或没有图片时，响应体是统一 JSON 信封，`code` 为 `404`。

### 7. `POST /api/spheroidization/{record_id}/process`

功能：人工处置球化记录。

业务规则：

- 处置不可逆。
- 一条记录只能处置一次。
- 重复处置返回 `code 400`。
- 记录不存在返回 `code 400`。
- 处置不会修改机器检测数据。

请求体：

```json
{
  "processed_by": "李四"
}
```

成功响应 `data`：处置后的球化记录对象。

### 8. 球化记录响应对象

列表和详情的基础形状：

```json
{
  "id": 12,
  "detection_time": "2026-09-27 08:00:00",
  "spheroidization_start_time": "2026-09-27 08:00:05",
  "spheroidization_end_time": "2026-09-27 08:01:10",
  "actual_spheroidization_time": 65,
  "spheroidization_abnormal": false,
  "standard_spheroidization_time": 70,
  "spheroidization_temperature": 1520,
  "spheroidization_temperature_time": "2026-09-27 08:00:10",
  "spheroidization_wire_entry_start_time": "2026-09-27 08:00:20",
  "spheroidization_wire_entry_end_time": "2026-09-27 08:01:30",
  "spheroidization_wire_entry_total_duration": 70,
  "spheroidization_weight": 1600,
  "processed": false,
  "processed_at": null,
  "processed_by": null,
  "review_result": null
}
```

详情接口额外返回：

```json
{
  "spheroidization_image": "/9j/4AAQ..."
}
```

字段说明：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | number | 球化记录 ID |
| detection_time | string | 检测时间 |
| spheroidization_start_time | string | 球化开始时间 |
| spheroidization_end_time | string | 球化结束时间 |
| actual_spheroidization_time | number | 实际球化时间 |
| spheroidization_abnormal | boolean | 机器判定结果；原本为 null 时也返回 false |
| standard_spheroidization_time | number | 创建记录时的标准球化时间快照 |
| spheroidization_temperature | number | 铁水温度 |
| spheroidization_temperature_time | string | 测温时间 |
| spheroidization_wire_entry_start_time | string | 进线开始时间 |
| spheroidization_wire_entry_end_time | string | 进线结束时间 |
| spheroidization_wire_entry_total_duration | number | 实际进线时间 |
| spheroidization_weight | number | 铁水重量 |
| processed | boolean | 是否已处理 |
| processed_at | string \| null | 处理时间 |
| processed_by | string \| null | 处理人 |
| review_result | string \| null | 最新复核结果：“正常”、“异常”或 null |
| spheroidization_image | string \| null | 仅详情接口存在，图片 Base64 |

说明：

- 列表和详情接口的 `review_result` 是最新一条人工复核结果。
- 新增记录和处置接口的 `review_result` 未额外聚合，通常为 null。
- `spheroidization_abnormal` 数据库原值允许 null，但接口层统一转换为 false，无法区分“明确正常”和“机器未判定”。

---

## 六、人工复核

### 1. `POST /api/reviews`

功能：对一条球化记录提交人工复核。

业务规则：

- 复核记录只增不改不删。
- 同一条球化记录可以复核多次。
- 复核结果只能是 `"正常"` 或 `"异常"`。
- 对应球化记录不存在时返回 `code 400`。
- 复核不会改变球化记录的处理状态。
- 复核不会修改机器判定结果。

请求体：

```json
{
  "spheroidization_record_id": 12,
  "review_result": "异常",
  "reviewer": "王五",
  "review_remark": "人工确认异常"
}
```

请求字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| spheroidization_record_id | number | 是 | 球化记录 ID |
| review_result | string | 是 | 只能是“正常”或“异常” |
| reviewer | string | 是 | 复核人 |
| review_remark | string \| null | 否 | 复核说明 |

成功响应 `data`：复核对象。

### 2. `GET /api/reviews/{record_id}`

功能：获取某条球化记录的全部复核历史。

路径参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| record_id | number | 球化记录 ID，不是复核记录 ID |

成功响应 `data`：复核对象数组，按复核 ID 升序。

没有复核记录时返回 `[]`。

复核对象：

```json
{
  "id": 5,
  "spheroidization_record_id": 12,
  "review_result": "异常",
  "reviewer": "王五",
  "review_remark": "人工确认异常",
  "reviewed_at": "2026-09-27 09:00:00"
}
```

---

## 七、标准应用状态文件

方案一没有修改数据库表结构。

当前应用标准保存在：

```text
data/active_standard.json
```

示例：

```json
{
  "standard_record_id": 2,
  "applied_at": "2026-09-27 16:14:28",
  "applied_by": null
}
```

读取规则：

1. `GET /api/standards/current` 优先读取该文件。
2. 根据文件中的 `standard_record_id` 查询标准。
3. 文件不存在、格式损坏或标准 ID 不存在时，兼容回退到最大标准 ID。
4. 新建标准后自动更新该文件。
5. 应用历史标准后更新该文件。
6. 备份或迁移时必须同时备份数据库和该 JSON 文件。

---

## 八、删除数据后的 ID 序列规则

三张表均增加了 `AFTER DELETE` 触发器：

- `standard_sync_sequence`
- `spheroidization_sync_sequence`
- `review_sync_sequence`

行为：

- 删除中间数据：序列保持当前最大 ID，下一条继续使用最大 ID + 1。
- 删除最后一条数据：序列回退，下一条复用被删除的最后一个 ID。
- 删除全部数据：序列为 0，下一条从 ID 1 开始。

该逻辑只根据 `MAX(id)`，不会按表记录数重置，因此不会和已有中间 ID 重叠。

---

## 九、主要错误示例

### 参数错误

```json
{
  "code": 422,
  "message": "请求参数不合法 — spheroidization_weight: Field required",
  "data": null
}
```

### 业务失败

```json
{
  "code": 400,
  "message": "不存在生效检测标准，无法创建球化检测记录",
  "data": null
}
```

### 记录不存在

```json
{
  "code": 404,
  "message": "记录不存在",
  "data": null
}
```

### 数据库约束失败

```json
{
  "code": 400,
  "message": "提交的数据不符合数据库约束",
  "data": null
}
```
