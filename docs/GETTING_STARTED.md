# 开发者上手指南

## 1. 第一次拿到项目

首先确认 Python 环境：

```bash
python --version
```

然后创建虚拟环境：

```bash
python -m venv .venv
```

激活虚拟环境并安装：

```bash
pip install fastapi uvicorn pytest
```

---

## 2. 启动项目

执行：

```bash
uvicorn app.main:app --reload
```

然后访问：

```text
http://127.0.0.1:8000/docs
```

确认 API 文档能够正常打开。

---

## 3. 运行测试

执行：

```bash
pytest
```

确保现有测试通过。

---

## 4. 开始开发前

必须先阅读：

```text
docs/ARCHITECTURE.md
docs/DEVELOPMENT.md
docs/API.md
```

特别注意：

* 机器检测结果不可篡改
* 人工复核独立保存
* 复核和处理相互独立
* 检测标准采用历史版本
* 历史检测记录保存标准快照

---

## 5. 开发球化记录

相关代码：

```text
app/
├── api/spheroidization.py
├── application/spheroidization/
├── domain/spheroidization/
└── schemas/spheroidization.py
```

对应 UseCase：

```text
CreateSpheroidizationUseCase
QuerySpheroidizationUseCase
ProcessSpheroidizationUseCase
```

---

## 6. 开发人工复核

相关代码：

```text
app/
├── api/review.py
├── application/review/
├── domain/review/
└── schemas/review.py
```

对应 UseCase：

```text
CreateReviewUseCase
QueryReviewUseCase
```

---

## 7. 开发检测标准

相关代码：

```text
app/
├── api/standard.py
├── application/standard/
├── domain/standard/
└── schemas/standard.py
```

对应 UseCase：

```text
CreateStandardUseCase
QueryStandardUseCase
```

---

## 8. 数据持久化

当前项目只提供 Repository Interface。

例如：

```text
app/domain/spheroidization/repository.py
```

后续数据库开发人员需要实现对应的 Repository。

具体实现应该放在 Infrastructure 层。

不要直接修改 Domain 中的 Repository Interface 来适配某个数据库。

---

## 9. 开发完成后

至少执行：

```bash
pytest
```

然后启动：

```bash
uvicorn app.main:app --reload
```

确认：

```text
/api/health
```

正常。

再通过：

```text
/docs
```

检查 API。

---

## 10. 提交代码前

确认：

* 没有把业务逻辑写进 API
* 没有绕过 Application 直接操作 Repository
* 没有修改机器原始检测结果
* 没有破坏历史标准
* 没有删除历史复核记录
* 新增业务代码有对应测试
* API 数据结构符合 API 契约
