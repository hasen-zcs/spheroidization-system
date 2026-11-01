# DEPLOY.md · 全新部署 / 升级 / 回滚

适用：球化监测系统正式版（FastAPI + SQLite + Vue，单进程同源部署）。
原则：**一个 uvicorn 进程（--workers 1）扛 API + 前端静态托管**，合并层和 vpmin 各一个 systemd 服务。

> 🔴 硬性约束：API 必须 `--workers 1`（会话在进程内存，多 worker = 随机 401 + 重启掉线）。
> 🔴 备份必须库 + `active_standard.json` 同批（`deploy/backup.sh` 已做到）。

---

## 一、全新部署

### 0. 前置
- Ubuntu 22.04+ / Debian 12+，root 或 sudo
- python3 ≥ 3.10（含 `python3-venv`）、curl
- node/npm（可选；不装就跳过前端构建，但没 dist 就没有页面）

### 1. 放代码
```bash
# 把代码放到 /opt/spheroidization（下文统一用这个路径）
cp -a ~/spheroidization-prod /opt/spheroidization
cd /opt/spheroidization
```

### 2. 装依赖 + 建库 + 管理员 + 生效标准
```bash
bash deploy/install.sh
# 会依次：检测依赖 → 建 venv → 装 requirements → 构建前端 → 建库建表
# → 交互输入管理员密码（getpass）→ 播种一条生效标准（75/90/60/1800）
```
- 密码不想走交互：`ADMIN_PASSWORD=*** bash deploy/install.sh`（**只这一次**，别写进 env 文件）
- 初值不合现场：`SEED_STANDARD_TIME=80 SEED_STANDARD_WEIGHING=2000 bash deploy/install.sh`
- 脚本幂等，重复执行不重复建账号/标准

### 3. 配环境变量
```bash
cp deploy/env.example /opt/spheroidization/env
vi /opt/spheroidization/env   # 至少确认 SPHEROIDIZATION_DB / MERGE_ROOT / MERGE_BACKEND
chmod 640 /opt/spheroidization/env
mkdir -p /var/log/spheroidization
```

### 4. 装 systemd 服务（模板已写好，不自动 enable）
```bash
cp deploy/systemd/spheroidization-api.service  /etc/systemd/system/
cp deploy/systemd/spheroidization-merge.service /etc/systemd/system/
# vpmin 的 unit 必须按现场改 WorkingDirectory / ExecStart / EnvironmentFile 后再装：
vi deploy/systemd/vpmin.service
cp deploy/systemd/vpmin.service /etc/systemd/system/
# 若 unit 里的 /opt/spheroidization 与你的部署路径不一致，同步改
cp deploy/logrotate.d/spheroidization /etc/logrotate.d/spheroidization
systemctl daemon-reload
```

### 5. 启动 + 验证
```bash
systemctl start spheroidization-api          # 先起 API
systemctl start spheroidization-merge        # 再起合并层
# vpmin：确认现场程序就绪后再 systemctl start vpmin
bash deploy/healthcheck.sh                   # 三项全 ✅ 才算部署完成
systemctl enable spheroidization-api spheroidization-merge   # 最后一步：开自启
```
浏览器打开 `http://<机器IP>:8000/` 登录（admin + 第 2 步设的密码），确认监控页「当前生效标准」有值。

### 6. 验证数据链路（可选但强烈建议）
```bash
cd /opt/spheroidization
.venv/bin/python -m merge --dry-run          # 影子跑，不调接口，看 merge_dryrun.jsonl
tail -f /var/log/spheroidization/api.log
```

---

## 二、升级（已有生产库）

1. **先备份**：`bash deploy/backup.sh`
2. 停服务：`systemctl stop spheroidization-merge spheroidization-api`
3. 换代码：把新版放到 /opt/spheroidization（保留 `data/` 和 `env`！`data/` 不进代码包，升级时绝不覆盖）
   ```bash
   # 例：新版在 /tmp/sph-new，只覆盖代码，不动 data/ 和 env
   rsync -a --exclude data --exclude env --exclude .venv /tmp/sph-new/ /opt/spheroidization/
   ```
4. **老库结构升级必须先迁移**（启动自检会拦，但先跑脚本更清楚）：
   ```bash
   cd /opt/spheroidization
   .venv/bin/python scripts/migrate_db.py    # 幂等，结构已新则跳过
   bash deploy/install.sh --no-admin         # 刷新 venv 依赖（库/管理员/标准都已存在，全部跳过）
   ```
5. 启动 + 验证：`systemctl start spheroidization-api spheroidization-merge`，`bash deploy/healthcheck.sh`
6. 冒烟：登录 → 看当前生效标准 → 手工补录一条 → 合并层日志无 5xx

---

## 三、回滚

代码回滚 + 数据恢复，两条线，**先数据后代码**：

1. 停服务：`systemctl stop spheroidization-merge spheroidization-api`
2. **恢复升级前备份**（自动会把升级后的库再备一份，不会丢）：
   ```bash
   ls data/backups/                          # 找到升级前那份 backup-YYYYmmdd-HHMMSS
   bash deploy/restore.sh data/backups/backup-XXXXXXXX-XXXXXX
   ```
3. 代码回滚：把 /opt/spheroidization 换回旧版目录（保留 `data/`、`env`）
   ```bash
   rsync -a --exclude data --exclude env --exclude .venv /opt/spheroidization-旧版/ /opt/spheroidization/
   cd /opt/spheroidization && bash deploy/install.sh --no-admin
   ```
4. 启动 + 验证（同升级第 5 步）。
5. 若回滚后数据还是不对 → 说明坏的是备份之前的操作，继续往前找更早的备份目录重复第 2 步（每份备份独立，互不影响）。

---

## 四、常见故障

### 1. 端口占用（8000）
```bash
ss -lntp | grep :8000                 # 看谁占着
systemctl status spheroidization-api  # 是不是自己没停干净
# 处理：停掉占用进程；要改端口则同步改 unit ExecStart、MERGE_BACKEND、healthcheck 的 SPHEROIDIZATION_PORT
```

### 2. 上传全 400「没有生效标准」
- 原因：库里一条标准都没有（全新库没播种，或误删了）。
- 查：`curl -s http://127.0.0.1:8000/api/standards/current | python3 -m json.tool`（data 为 null 就是没有）
- 治：重新播种 `bash deploy/install.sh --no-admin`（只在标准表为空时补一条），
  或让管理员在网页「标准管理」新建一条（新建即生效）。

### 3. 权限 401 / 登录成功却随机掉线
- 先确认 unit 里是 `--workers 1`：`systemctl cat spheroidization-api | grep ExecStart`
- 多 worker 或 Nginx 前挂多实例都会导致（会话在进程内存）。改回单 worker 后全员重新登录。
- 正常 401 则检查：账号是否被停用（停用后不能登录）、密码是否正确。

### 4. 磁盘满
```bash
df -h /                              # 看哪块满
du -sh /opt/spheroidization/data /var/log/spheroidization /root/MR | sort -h
```
- 备份目录超龄会自动清（BACKUP_KEEP），但**视频/图片、jsonl 采集文件**不会自动清：
  优先清 `/root/MR` 下的历史 jsonl（确认合并层已消费完再删）和旧日志。
- 库文件写满会直接拒绝写入，healthcheck 的「库可写」会红——先腾空间再 `systemctl restart spheroidization-api`。

### 5. 合并层不停 5xx
```bash
tail -100 /var/log/spheroidization/merge.log
systemctl status spheroidization-api    # 先确认 API 活着
curl -s http://127.0.0.1:8000/api/health
```
合并层自带指数退避 + 死信（MERGE_DEAD_AFTER），不会丢数据；修好后：
`.venv/bin/python -m merge --replay-dead-letter` 把死信重新入队。

### 6. 启动自检报错（表/列不齐）
老库直接换新代码会触发。跑 `.venv/bin/python scripts/migrate_db.py` 再启动；
迁移脚本不动数据、幂等可重跑。
