# 按钮接入补丁（PLC DB200.128.0）

日期：2026-11-01
适用：东贝 QHAIServer `10.0.0.19` 的 `/root/Get_Allinfomation`
本目录是**本地准备好的补丁**，尚未覆盖生产文件。

## 一、这次改了什么

| 文件 | 改动 |
|---|---|
| `Get_PLCInfo.v1.1.py` | 在生产采集脚本基础上加：按钮位 `DB200.128.0` 上升沿、连按去抖（默认 2s）、stdout 事件 `{"event":"button_confirm",...}`、按钮文件（全量 + 滚动 10 条） |
| `bridge.v1.1.py` | 在 `emit()` 里**先于 `plc_count += 1`** 拦截按钮事件：不写 `plc.jsonl`、不占配对序号，只打日志 |
| 管理端 `plc_button_time` | 主表加列（ALTER，不重建），创建接口/详情接口透传，详情页显示“按钮时刻” |

为什么必须在 bridge 拦截：`bridge.emit` 对 PLC 子进程 stdout 的**每一行**都 `plc_count += 1`，
按钮行若混进去，`plc.jsonl` 的序号会和进线错位，合并器按序号配对会整体乱掉（10-27 已指出）。

## 二、前置确认（必须做，不然上线也白搭）

1. **确认按钮位真的接线了。**
   读 `DB200.128.0`，有人按按钮时应从 0 变 1 再回 0。
   **2026-11-01 00:12:25 已实测到一次脉冲**（原始字节 1 → 0，持续约 0.2s），
   40 秒后出现该炉的喂丝开始（00:13:05），信号与浇注动作对得上 → **按钮位已接线**。
   仍需注意：脉冲很短（~200ms），采集周期必须 ≤0.1s（现为 0.1s，够用）。
   探测命令（只读）：
   ```bash
   /root/Get_Allinfomation/.venv/bin/python -c "
   import snap7,time
   c=snap7.client.Client(); c.connect('192.168.10.1',0,1)
   for _ in range(100):
       print(c.db_read(200,128,1)[0]&1, end=' ', flush=True); time.sleep(0.2)
   c.disconnect()"
   ```
2. 确认按钮时间补偿：当前 `TRIGGERS` 里按钮 `offset_s=0`。若按钮信号比实际浇注晚 X 秒，
   改 `("按钮确认", 200, 128, 0, X)`。
3. 确认连按策略：当前 2 秒内重复按下只取第一次，其余计数丢弃（`BUTTON_DEBOUNCE_S`）。

## 三、上线步骤（需要停机窗口，约 3 分钟）

```bash
cd /root/Get_Allinfomation

# 1. 备份（三个文件都要）
cp PLC_Moudle/Get_PLCInfo.py PLC_Moudle/Get_PLCInfo.py.bak-$(date +%Y%m%d-%H%M%S)
cp Info_Conect_Module/bridge.py Info_Conect_Module/bridge.py.bak-$(date +%Y%m%d-%H%M%S)
cp PLC_Moudle/v1.py PLC_Moudle/v1.py.ref-$(date +%Y%m%d)

# 2. 覆盖（用本目录上送的两个文件）
#    Get_PLCInfo.v1.1.py   -> PLC_Moudle/Get_PLCInfo.py
#    bridge.v1.1.py        -> Info_Conect_Module/bridge.py

# 3. 重启采集（bridge 会连带重启两个 worker）
screen -S plc_temp -X quit
screen -dmS plc_temp bash -lc 'cd /root/Get_Allinfomation && uv run Info_Conect_Module/bridge.py >> /root/logs/plc_temp.log 2>&1'

# 4. 看日志
tail -f /root/logs/plc_temp.log
```

## 四、验证清单

| # | 检查 | 通过标准 |
|---|---|---|
| 1 | 日志出现 `[button] 2026-11-01 …` | 按一次按钮出现一条 |
| 2 | `/root/Get_Allinfomation/all_button_confirm_time.jsonl` | 行数 +1 |
| 3 | `/root/Get_Allinfomation/plc.jsonl` | **不出现** `button_confirm_time` 字段 |
| 4 | `plc.jsonl` 的 `reaction_count` | 连续、无跳号 |
| 5 | 合并器日志 | 无配对错位、无“漏检”暴涨 |
| 6 | 连续 2 炉 | 记录正常入库，`detection_time` 仍是原口径（按钮只在管理端留档） |

> 注意：本补丁**不改变** `detection_time` 的取值。合并层（第一刀）接入按钮后才会把锚点切到按钮时刻。

## 五、回滚（1 分钟）

```bash
cd /root/Get_Allinfomation
cp PLC_Moudle/Get_PLCInfo.py.bak-<时间戳> PLC_Moudle/Get_PLCInfo.py
cp Info_Conect_Module/bridge.py.bak-<时间戳> Info_Conect_Module/bridge.py
screen -S plc_temp -X quit
screen -dmS plc_temp bash -lc 'cd /root/Get_Allinfomation && uv run Info_Conect_Module/bridge.py >> /root/logs/plc_temp.log 2>&1'
```

## 六、风险

| 风险 | 说明 / 对策 |
|---|---|
| 按钮位没接线 | 上线后读到的永远是 0，不会出错但也没用；先做第二步的现场按按钮验证 |
| 按钮行污染 plc.jsonl | 已在 bridge 拦截并加测试（按钮与进线混流，序号仍 1、2） |
| 连按重复 | 默认 2s 去抖；若现场习惯连按，需确认取第一次还是最后一次 |
| 按钮时间补偿 | 默认 0s；喂丝结束是 −24s，按钮是否需要补偿要现场比对 |
| 旧合并器不认按钮 | 本补丁只负责“采到、别添乱”；按钮真正生效在合并层上线后 |

## 七、已完成/未完成

- [x] 采集脚本补丁 + stdout 事件 + 去抖
- [x] bridge 旁路（不占序号）
- [x] 管理端 `plc_button_time` 落库、接口、详情页
- [x] 单测 8 条（去抖、事件格式、滚动保留、bridge 分流/计数）
- [ ] 现场接线确认（需人按按钮）
- [ ] 现场覆盖与验证（需停机窗口）
- [ ] 合并层把 `detection_time` 锚点切到按钮（第一刀上线后）
