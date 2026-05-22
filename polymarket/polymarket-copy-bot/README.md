# Polymarket 跟单交易机器人

每日筛选 Polymarket 上 top 10 高水平交易员（复合分：胜率 + 累计盈利 + 风险调整 ROI），实时跟随他们的开仓和平仓。

> **设计文档**：`../docs/superpowers/specs/2026-05-18-polymarket-copy-bot-design.md`
> **实施计划**：`../docs/superpowers/plans/2026-05-18-polymarket-copy-bot.md`

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env 填入 POLYMARKET_PRIVATE_KEY 和 POLYMARKET_FUNDER_ADDRESS

# 1. 跑一次排名（写入今日 top_10）
python main.py rank

# 2. DRY-RUN 跟单（不下单，只打日志）
python main.py watch --dry-run

# 3. 实盘（需要环境变量确认）
CONFIRM_LIVE=yes python main.py watch --live

# 4. 回测（过去 60 天）
python main.py backtest --days 60
```

## 工作流程建议

1. **第一周**：每日 cron 跑 `rank`，运行 `watch --dry-run` 累积观察数据
2. **第二周**：用 `backtest` 验证策略，根据结果调整 `RANK_WEIGHTS`
3. **第三周起**：小额开实盘（`COPY_AMOUNT_USD=2`），观察实盘和回测的差距
4. **稳定后**：调高 `COPY_AMOUNT_USD`

## Signal 模式（受地区限制时的用法）

如果 Polymarket 在你的地区**封锁下单**（CLOB API 返回 403），bot 仍可作为"分析+决策辅助"工具运行：`watch --dry-run` 在每个新 OPEN 事件时打印结构化 signal 块（含 Polymarket URL + trader rank/score），你可以**手动**到浏览器下单：

```
============================================================
>>> SIGNAL  2026-05-22 22:57:52 UTC
Trader  0x6a72f618...  (rank #1  win 79%  PnL $640,112)
Market  Cervia: Andrea Guerrieri vs Max Alcala Gurri
URL     https://polymarket.com/event/atp-guerrie-gurri-2026-05-22
Action  BUY  Max Alcala Gurri  @ $0.4400
Size    $1.00  ~  2.27 shares
============================================================
```

URL 直达 Polymarket 市场，点开就能下单。

## 风控说明（重要）

三道硬风控（任一触发都会拒绝**新开仓**，但**平仓始终允许**——保留止损能力）：

1. `DAILY_LOSS_LIMIT` —— 日已实现亏损上限（事后熔断）
2. `MAX_OPEN_POSITIONS` —— **G3** 同时持有的 OPEN 仓位总数上限（事前限频）
3. `MAX_OPEN_PER_TRADER` —— **G4** 单个 source_trader 最多并发持仓数（防止单人主导敞口）

**G3** 来自第一次真实联调：3 个 top trader 在 3 分钟内触发了 34 个 OPEN。如果按 `COPY_AMOUNT_USD=5`、`MAX_OPEN_POSITIONS=20`，达到 20 仓后新单被拒绝直到有仓位 resolve / 被 source 平仓腾出名额。

**G4** 来自第二次真实联调（30 分钟）：rank #3 一人吃掉 18/20 仓位（90%），G3 只控总数不控分布。`MAX_OPEN_PER_TRADER=5` 强制 20 个仓位至少分散到 4 个 source_trader。

把任一变量设为 `0`（或留空）可禁用对应风控。

## 配置参考

见 `.env.example`。关键参数：

| 变量 | 默认 | 说明 |
|------|------|------|
| `COPY_AMOUNT_USD` | 5 | 每笔跟单的固定美元金额 |
| `DAILY_LOSS_LIMIT` | 50 | 日已实现亏损上限（熔断阈值） |
| `MAX_OPEN_POSITIONS` | 20 | G3：同时持有的 OPEN 仓位总数上限（0 禁用） |
| `MAX_OPEN_PER_TRADER` | 5 | G4：单交易员最多并发持仓数（0 禁用） |
| `MIN_TOTAL_PNL_USD` | 0 | 绝对阈值：候选必须满足 total_pnl ≥ 此值 |
| `MIN_WIN_RATE` | 0.5 | 绝对阈值：候选必须满足 win_rate ≥ 此值 |
| `RANK_WEIGHTS` | 0.3,0.3,0.4 | win_rate / total_pnl / sharpe 权重 |
| `RANK_WINDOW_DAYS` | 90 | 评分窗口 |
| `POLL_INTERVAL_SEC` | 30 | 检测新单延迟 |

## 测试

```bash
python -m pytest -v
```

当前覆盖 55 个测试，覆盖所有模块的核心路径（含 PnL 重建器）。

## 已知局限

- 回测**不模拟**：滑点、挂单未成交、网络延迟、Polymarket 临时下架市场。实盘 PnL 大概率低于回测。
- 同一 source_trader 对同一市场连续加仓时，本机器人**只跟第一次**（避免你的固定金额策略和对方加仓策略冲突）。
- **REDEEM 状态推断**：当 source_trader 在某个市场触发 REDEEM 事件时，bot 假设"source 只 REDEEM 赢的那边 + 我们镜像了相同方向 → 我们也赢"，将持仓置为 RESOLVED + PnL = `(1.0 - 开仓价) × 份数`。极少数情况（source 同时持 Yes+No 后 MERGE 而非 REDEEM）不在此覆盖。
- **MERGE 事件未处理**：source 用 MERGE 平仓的极少数场景，bot 不感知。

## Polymarket API 真实情况（联调记录）

| 项目 | 限制 |
|---|---|
| Leaderboard 端点 | `lb-api.polymarket.com/profit?window=all` — **最多返回 50 条**，`limit` 参数被忽略 |
| Activity 端点 | `data-api.polymarket.com/activity?user=X` — **offset 硬上限 3000**，超过返回 HTTP 400 |
| Activity 事件类型 | `TRADE`（含 BUY/SELL）/ `REDEEM` / `MERGE` / `REWARD` — **无 `pnl_realized` 字段** |
| PnL 数据 | `/activity` 不带 PnL；只能用 `pnl_reconstructor.py` 从事件流回放推导 |
| User-Agent | Cloudflare 会限流默认 `python-requests` UA — 客户端已设浏览器 UA |
| 速率限制 | 候选间隔 0.3s、分页间隔 0.3s，跑完 10 个候选 ≈ 3 分钟 |

所有端点 URL 都集中在 `api_client.py::RequestsPolymarketAPI` 一处，schema 变动只需改这一个文件。

## 架构

```
ranker.py             -> 每日生成 top_10 名单（写入 SQLite）
pnl_reconstructor.py  -> 从 /activity 事件流回放推导每市场 PnL
watcher.py            -> 30s 轮询 top_10 的活动，diff 出 OPEN/CLOSE/RESOLVE 事件
risk.py               -> 日亏损熔断 + G3/G4 并发上限（事件 -> Executor 前的最后一道闸）
executor.py           -> DryRun 模式仅写日志；Live 模式调用 CLOB API
backtest.py           -> 用历史数据回放 watcher+executor，验证策略
main.py               -> CLI：rank / watch --dry-run|--live / backtest --days N
                         watch 自动跨日：UTC 凌晨后无 top_10 时触发 rank
tools/compare_days.py -> 跨日 rank A/B 对比工具
```

## 与 polymarket-arb-bot 的关系

并列的独立项目。共用同一个钱包（`.env` 配置可复制），但策略逻辑完全独立。
