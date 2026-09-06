# 前端开发说明

## 1. 前端定位

本前端用于球化监测系统的业务页面展示和操作。

当前阶段的目标是：

* 建立前端页面基本结构
* 实现页面路由
* 实现前后端 API 联通
* 为后续业务功能开发提供基础框架

当前前端为样例框架，不进行复杂的 UI 和工程化设计。

---

## 2. 技术栈

当前前端采用：

* Vue 3
* TypeScript
* Vite
* Vue Router
* 浏览器原生 `fetch`

暂不引入：

* Axios
* Element Plus
* Pinia
* 复杂组件库
* 复杂状态管理

如果后续项目规模扩大，再根据实际需要增加。

---

## 3. 前端目录结构

```text
frontend/
├── src/
│   ├── api/
│   │   └── index.ts
│   │
│   ├── router/
│   │   └── index.ts
│   │
│   ├── views/
│   │   ├── Home.vue
│   │   ├── Spheroidization.vue
│   │   ├── SpheroidizationDetail.vue
│   │   └── Standard.vue
│   │
│   ├── App.vue
│   ├── main.ts
│   └── style.css
│
├── package.json
└── vite.config.ts
```

### 目录职责

`views/`

存放业务页面。

`api/`

存放前端对后端 API 的 HTTP 请求。

`router/`

负责页面路由。

`App.vue`

负责前端整体页面入口和公共导航。

---

# 4. 页面设计

当前前端共设计 4 个页面。

```text
首页
│
├── 球化记录
│    └── 球化记录详情
│
└── 检测标准
      ├── 当前标准
      └── 标准记录
```

---

## 4.1 系统首页

### 路由

```text
/
```

### 页面职责

显示系统基本运行状态。

当前阶段主要用于验证前后端是否正常连接。

### 主要功能

* 显示系统名称
* 检查后端运行状态
* 显示后端连接结果

### API

```text
GET /api/health
```

---

## 4.2 球化记录

### 路由

```text
/spheroidization
```

### 页面职责

查询球化检测历史记录。

### 主要功能

* 查询球化记录
* 查询异常记录
* 查看记录详情

### API

```text
GET /api/spheroidization

GET /api/spheroidization/abnormal
```

点击某条记录后进入：

```text
/spheroidization/{id}
```

---

## 4.3 球化记录详情

### 路由

```text
/spheroidization/:id
```

### 页面职责

显示单条球化检测记录的完整信息，并提供人工操作入口。

### 主要功能

* 查看检测数据
* 查看检测结果
* 查看检测标准快照
* 查看人工复核记录
* 新增人工复核
* 标记记录已处理

### API

查询记录：

```text
GET /api/spheroidization/{record_id}
```

查询复核：

```text
GET /api/reviews/{record_id}
```

新增复核：

```text
POST /api/reviews
```

标记处理：

```text
POST /api/spheroidization/{record_id}/process
```

---

## 4.4 检测标准

### 路由

```text
/standard
```

### 页面职责

管理系统当前检测标准，并查看历史标准记录。

### 页面组成

```text
检测标准
│
├── 当前标准
│
├── 标准记录
│
└── 新增标准
```

### 主要功能

* 查看当前有效标准
* 查看历史标准记录
* 新增检测标准

### API

当前标准：

```text
GET /api/standards/current
```

历史标准：

```text
GET /api/standards/history
```

新增标准：

```text
POST /api/standards
```

---

# 5. 页面与 API 对应关系

| 页面     | 功能     | API                                      |
| ------ | ------ | ---------------------------------------- |
| 首页     | 检查系统状态 | `GET /api/health`                        |
| 球化记录   | 查询记录   | `GET /api/spheroidization`               |
| 球化记录   | 查询异常记录 | `GET /api/spheroidization/abnormal`      |
| 球化记录详情 | 查询记录   | `GET /api/spheroidization/{id}`          |
| 球化记录详情 | 查询复核   | `GET /api/reviews/{id}`                  |
| 球化记录详情 | 新增复核   | `POST /api/reviews`                      |
| 球化记录详情 | 标记处理   | `POST /api/spheroidization/{id}/process` |
| 检测标准   | 当前标准   | `GET /api/standards/current`             |
| 检测标准   | 历史标准   | `GET /api/standards/history`             |
| 检测标准   | 新增标准   | `POST /api/standards`                    |

---

# 6. 页面导航

系统采用顶部导航栏。

```text
球化监测系统

首页
球化记录
检测标准
```

页面关系：

```text
首页
 ├── 球化记录
 │     └── 球化记录详情
 │
 └── 检测标准
```

球化记录详情不作为顶部一级菜单，而是从球化记录进入。

---

# 7. API 调用规则

所有后端 API 请求统一放在：

```text
src/api/index.ts
```

页面不要直接大量编写 HTTP 请求代码。

页面应该：

```text
Vue 页面
   ↓
调用 api/index.ts 中的函数
   ↓
HTTP 请求
   ↓
FastAPI
```

例如：

```typescript
import { health } from "../api"

const result = await health()
```

而不是在页面中直接到处编写：

```typescript
fetch("http://127.0.0.1:8000/...")
```

---

# 8. 前端与后端职责

前端主要负责：

* 页面展示
* 用户输入
* 用户操作
* API 请求
* API 返回结果展示

后端负责：

* 业务规则
* 数据校验
* 业务状态变化
* 数据持久化
* 业务异常处理

前端不负责核心业务判断。

例如：

```text
机器检测结果是否异常
```

这个判断属于后端业务数据，不应该由前端重新计算。

---

# 9. 前端开发原则

当前项目遵循简单原则：

### 9.1 优先简单

没有实际需求时，不增加新的框架、组件和抽象层。

### 9.2 页面与 API 分离

页面负责展示和操作，API 文件负责 HTTP 请求。

### 9.3 不在前端复制业务规则

业务规则以后端为准。

### 9.4 不提前过度工程化

当前不设计复杂的：

* 状态管理
* 组件体系
* 权限体系
* UI 组件库
* 前端数据缓存
* 前端业务服务层

当项目实际出现需求时再增加。

---

# 10. 当前前端开发状态

当前已经完成：

* Vue 3 + TypeScript + Vite 项目创建
* 页面目录建立
* Vue Router 配置
* API 请求文件建立
* `/api/health` 前后端联通
* 球化记录查询 API 联通
* 球化记录详情 API 联通
* 人工复核 API 请求
* 标记处理 API 请求
* 顶部导航栏

当前尚未实现：

* 数据库
* Repository 实现
* 后端真实业务逻辑
* 真实球化记录数据
* 真实复核数据
* 真实标准数据
* 正式 UI 设计

因此当前前端主要用于：

> **验证系统框架、页面结构以及前后端 API 联通。**

后续后端业务功能实现后，再将页面逐步替换为真实业务页面。
