# RUNBOOK.md · 现场运维卡

> 约定：代码在 `/opt/spheroidization`，库在 `data/spheroidization.db`，
> env 在 `/opt/spheroidization/env`，日志在 `/var/log/spheroidization/`。
> 三条服务：`spheroidization-api`（8000）、`spheroidization-merge`、`vpmin`。
> 每条命令都可以直接复制执行。

## 状态速览

```bash
systemctl status spheroidization-api spheroidization-merge vpmin --no-pager
ss -lntp | grep -E ':8000'                       # API 端口在监听？
bash /opt/spheroidization/deploy/healthcheck.sh  # 三项体检（API/库可读/库可写）
```

## 启动 / 停止

```bash
systemctl start spheroidization-api              # 顺序：先 API
systemctl start spheroidization-merge            # 再合并层
systemctl start vpmin                            # 最后检测

systemctl stop spheroidization-merge             # 停：反过来，先合并层
systemctl stop vpmin
systemctl stop spheroidization-api
```

## 看日志

```bash
tail -f /var/log/spheroidization/api.log         # API（uvicorn stdout/err）
tail -100 /var/log/spheroidization/merge.log     # 合并层 stdout
tail -f /root/MR/merge_service.log               # 合并层业务日志（MERGE_LOG）
tail -f /var/log/spheroidization/vpmin.log       # 检测
journalctl -u spheroidization-api -n 100 --no-pager   # 崩溃/重启记录
```

## 备份

```bash
bash /opt/spheroidization/deploy/backup.sh       # 库 + active_standard.json，自动校验 + 保留最近 10 份
ls -lt /opt/spheroidization/data/backups/ | head # 看有哪些份
```
定时备份（可选，crontab -e 加一行，每天 03:30）：
```cron
30 3 * * * bash /opt/spheroidization/deploy/backup.sh >> /var/log/spheroidization/backup.cron.log 2>&1
```

## 恢复

```bash
# 1. 停服务（顺序见上）
systemctl stop spheroidization-merge vpmin spheroidization-api
# 2. 找到要恢复的份（脚本会先把当前库再备一份，再覆盖）
bash /opt/spheroidization/deploy/restore.sh /opt/spheroidization/data/backups/backup-XXXXXXXX-XXXXXX
# 3. 重启 + 体检
systemctl start spheroidization-api spheroidization-merge vpmin
bash /opt/spheroidization/deploy/healthcheck.sh
```

## 切流（临时把检测暂停 / 恢复）

```bash
# 暂停检测（合并层保留，已产出的 reactions.jsonl 会继续被消费完）
systemctl stop vpmin
# 恢复
systemctl start vpmin
# 临时停整个入库链路（比如修库、回滚期间）
systemctl stop spheroidization-merge spheroidization-api
systemctl start spheroidization-api spheroidization-merge
```
注意：vpmin 停的时候亮光检测会漏记；长时间停机后用
`.venv/bin/python -m merge --replay-dead-letter` 检查死信。

## 回滚

```bash
# 数据回滚（代码回滚见 DEPLOY.md 第三节，先数据后代码）
systemctl stop spheroidization-merge spheroidization-api
bash /opt/spheroidization/deploy/restore.sh /opt/spheroidization/data/backups/backup-XXXXXXXX-XXXXXX
# 换回旧版代码（保留 data/ 与 env）：
#   rsync -a --exclude data --exclude env --exclude .venv /opt/spheroidization-旧版/ /opt/spheroidization/
cd /opt/spheroidization && bash deploy/install.sh --no-admin
systemctl start spheroidization-api spheroidization-merge
bash /opt/spheroidization/deploy/healthcheck.sh
```

## 改生效标准

网页「标准管理」新建一条（新建即生效，历史标准保留），或查当前值：
```bash
curl -s http://127.0.0.1:8000/api/standards/current | python3 -m json.tool
curl -s http://127.0.0.1:8000/api/standards/switch-logs?page=1 | python3 -m json.tool
```

## 密码 / 账号

```bash
# 首个管理员只能在命令行建（接口建用户需要已有管理员，死锁）
cd /opt/spheroidization
.venv/bin/python scripts/init_admin.py <用户名>     # 交互输入密码，幂等（已存在则跳过）
```
忘了密码：系统里没有「找回密码」。走恢复：`deploy/restore.sh` 恢复到人少时点的备份后重建；
或停服务后直接改库（不建议，先备份！）。

## 磁盘巡检

```bash
df -h /
du -sh /opt/spheroidization/data /var/log/spheroidization /root/MR 2>/dev/null | sort -h
```
jsonl 采集文件（/root/MR 下）只增不减，合并层消费完才能清；日志由 logrotate 每日轮转留 14 天。

## 体检不通过时查什么

| 症状 | 第一反应 |
|---|---|
| API 不可达 + 端口无人监听 | `systemctl status spheroidization-api`，看崩溃原因 `journalctl -u spheroidization-api -n 50` |
| 库文件不存在 | 全新机器漏装 → `bash deploy/install.sh` |
| 库不可写 | `df -h`（满了）→ 腾空间后重启 API |
| 上传全 400 | 多半没生效标准 → `curl -s localhost:8000/api/standards/current`，data=null 就补标准（见 DEPLOY.md 四.2） |
