# Polymarket 跟单交易机器人 — 设计文档

**日期：** 2026-05-18
**项目：** `polymarket/polymarket-copy-bot/`
**关系：** 与现有 `polymarket-arb-bot/` 并列的独立项目，复用其钱包配置（`.env`）和 CLOB 客户端封装思路。

---

## 1. 目标

自动跟随 Polymarket 上经验证的高水平交易员。每日筛选 top 10，监听他们的新开仓和平仓，按固定金额镜像下单；通过日亏损上限做硬熔断。

**非目标：** 套利（已由 `polymarket-arb-bot` 覆盖）、自主行情判断、社交信号、Twitter/Discord 等链外信号。

---

## 2. 关键设计决策（与用户确认）

| ID | 决策 | 选择 |
|---|---|---|
| 选人维度 | 胜率 + 累计盈利 + 风险调整 ROI 复合分（A+B+D） | 见 §4 |
| 数据来源 | Leaderboard 拿候选池 → Data-API 拉完整历史 → 本地算分（D 方案） | 见 §3 |
| 仓位大小 | A1 固定美元金额 `COPY_AMOUNT_USD` | 默认 $5 |
| 退出方式 | B1 镜像退出（他卖我卖） | 见 §5 |
| 过滤器 | C1 全跟，不过滤 | 靠"固定金额够小"自然限敞口 |
| 排名刷新 | D1 每日 00:00 UTC 一次 | — |
| 老仓位处理 | E1 跌出 top 10 后继续持有，等市场 resolve | 不再跟其新单 |
| 检测延迟 | F1 每 30 秒轮询 | — |
| 硬风控 | G2 日已实现亏损上限 `DAILY_LOSS_LIMIT` | 默认 $50 |
| 默认模式 | DRY_RUN 优先，验证 1-2 周后开实盘 | — |
| 回测 | 内置 | 见 §7 |

**显式取舍（已与用户对齐）：**
- 未启用 G3（最大并发持仓数）、G4（单交易员最大敞口）。日亏损上限作为唯一事后熔断，承担所有失败模式的兜底责任。代价：可能在熔断触发前已亏满当日上限。README 将记录此权衡。
- 评分权重 `0.3 / 0.3 / 0.4` 为经验值，无数据支撑；第一版固定，跑两周后用回测模式反向调参。

---

## 3. 数据流与组件

```
┌─────────────┐                          ┌──────────────┐
│   Ranker    │  每日 00:00 UTC           │              │
│             │ ─────────────────────►   │              │
└─────────────┘  写入 top_10              │              │
       ▲                                  │   SQLite     │
       │ 读 Leaderboard + Data-API        │   状态库     │
       ▼                                  │              │
┌─────────────┐                          │ ┌──────────┐ │
│  Watcher    │  每 30s 轮询              │ │ top_10   │ │
│             │  对每个 top trader        │ │ our_pos  │ │
│             │  diff 活动记录            │ │ trades   │ │
└─────┬───────┘                          │ │ daily_pnl│ │
      │ 发现 OPEN/CLOSE 事件              │ └──────────┘ │
      ▼                                  └──────────────┘
┌─────────────┐                                  ▲
│  RiskGate   │  检查日亏损                       │
│             │  超限则拒绝新开仓                   │
└─────┬───────┘                                  │
      │                                          │
      ▼                                          │
┌─────────────┐                                  │
│  Executor   │  下单 / DRY_RUN 日志              │
│             │  ─────────────────────────────►  │ 记录
└─────────────┘  CLOB API                         │
```

**触发规则（精确版）：**

| 事件 | 动作 |
|---|---|
| Top trader 开新仓 | 镜像买入 `COPY_AMOUNT_USD`，向上取整到 Polymarket 最小下单量 |
| Top trader 平仓 **且仍在当前 top 10** | 镜像卖出我们对应的持仓 |
| Top trader 平仓 **但已跌出 top 10** | 忽略，我们的持仓继续持有到市场 resolve |
| 日已实现亏损 ≥ `DAILY_LOSS_LIMIT` | RiskGate 拒绝所有新开仓；**允许镜像退出**（让仓位能减少敞口） |

---

## 4. 复合评分公式

**第一步：候选池过滤**

候选地址必须满足：
- 过去 `RANK_WINDOW_DAYS`（默认 90）天内至少 resolve 过 **20 个市场**（样本量门槛）
- 累计交易额 **≥ $1,000**（过滤微小账户）
- 最后一笔交易在过去 **14 天**内（活跃度，否则跟了没新单）

候选池来源：Polymarket 官方 Leaderboard 取 top N（默认 N=500），再用 Data-API 拉每人完整历史验证上述门槛。

**第二步：原始指标**

| 指标 | 定义 |
|---|---|
| `win_rate` | 已 resolve 市场中盈利的占比 |
| `total_pnl` | 窗口内累计已实现 PnL（美元） |
| `sharpe_like` | `mean(每市场 ROI) / std(每市场 ROI)`；按"每个 resolved 市场一次"算 ROI，不用日频 |

**第三步：标准化 + 加权**

各项按候选池内 z-score 标准化（减均值除标准差），加权求和：

```
score = w1 × z(win_rate) + w2 × z(total_pnl) + w3 × z(sharpe_like)
```

默认 `RANK_WEIGHTS = 0.3, 0.3, 0.4`。Sharpe 权重偏高的理由：胜率和盈利易被极端样本污染，sharpe 强制要求稳定性。

**第四步：排序取 top 10，写入 `top_10` 表，附 score 快照供事后复盘。**

---

## 5. 仓位生命周期

| 状态 | 进入条件 | 退出条件 |
|---|---|---|
| `OPEN` | source_trader 开新仓 + 风控通过 + 下单成功 | 见下 |
| `MIRRORED_CLOSE` | source_trader 平仓且仍在 top 10 → 我们镜像卖出 | 卖单成交，记录 realized_pnl |
| `ORPHANED_HOLD` | source_trader 跌出 top 10 但我们仓位还在 | 市场 resolve 后自动结算 |
| `RESOLVED` | 市场 resolve | 按结果结算，记录 realized_pnl |

`our_positions` 表通过 `(source_trader, market_id, side)` 唯一索引避免同一来源重复跟单。同一交易员对同一市场连续加仓在第一版**只跟第一次**——简化逻辑，避免 source_trader 的加仓策略和我们的固定金额策略冲突。

---

## 6. 项目结构

```
polymarket/polymarket-copy-bot/
├── main.py              # CLI：rank / watch / backtest
├── ranker.py            # §4 评分逻辑
├── watcher.py           # 30s 轮询 + activity diff
├── executor.py          # 下单封装（dry_run 时只 log）
├── risk.py              # 日亏损熔断
├── backtest.py          # 历史回放
├── storage.py           # SQLite 封装
├── api_client.py        # Polymarket Data-API + CLOB 封装
├── config.py            # 从 .env 读取
├── requirements.txt
├── .env.example
├── README.md
└── data/
    └── bot.sqlite       # gitignored
```

**CLI：**

| 命令 | 用途 |
|---|---|
| `python main.py rank` | 只跑一次排名，打印 top 10 + 分数（调试评分） |
| `python main.py watch --dry-run` | 完整流程，executor 只 log（默认推荐，验证 1-2 周） |
| `python main.py watch --live` | 实盘下单 |
| `python main.py backtest --days 60` | 用过去 60 天历史数据回放 |

**`.env` 关键配置：**

```
POLYMARKET_PRIVATE_KEY=...
POLYMARKET_FUNDER_ADDRESS=...
COPY_AMOUNT_USD=5
DAILY_LOSS_LIMIT=50
RANK_WINDOW_DAYS=90
RANK_WEIGHTS=0.3,0.3,0.4
RANK_CANDIDATE_POOL_SIZE=500
POLL_INTERVAL_SEC=30
MIN_RESOLVED_MARKETS=20
MIN_LIFETIME_VOLUME_USD=1000
MIN_LAST_TRADE_DAYS=14
```

CLI flag (`--dry-run` / `--live`) 优先级高于 env 中的 `MODE`。

---

## 7. SQLite Schema

| 表 | 字段（关键） |
|---|---|
| `top_10` | `date PK, trader_addr PK, score, win_rate, total_pnl, sharpe_like, rank` |
| `our_positions` | `id PK, source_trader, market_id, side, size_usd, opened_at, closed_at NULL, realized_pnl NULL, status` |
| `trades` | `id PK, position_id FK, action (OPEN/CLOSE), price, size, tx_hash NULL, ts, dry_run BOOL` |
| `daily_pnl` | `date PK, realized_pnl, halted_at NULL` |

唯一索引：`our_positions(source_trader, market_id, side)` — 防止同源重复跟单。

---

## 8. 回测模式

**核心原则：和实盘走完全相同的代码路径**，避免"回测赚钱实盘亏钱"陷阱。

实现方式：
1. **事件源换源**：实盘的 `watcher.poll()` 换成 `backtest.replay()` —— 按时间顺序播放历史 activity 记录。
2. **executor 换源**：实盘的 CLOB 下单换成"按历史成交价模拟成交"（假设无滑点；第一版不模拟挂单失败）。
3. **时钟换源**：所有 `now()` 调用走一个统一的 `clock` 抽象，实盘返回真实时间，回测返回当前回放时间戳。
4. **结果输出**：累计 PnL 曲线、每日 PnL、命中率、各交易员贡献、最大回撤。

回测**不模拟**：滑点、挂单未成交、网络延迟、Polymarket 临时下架市场。这些是已知的"实盘比回测差"来源，README 会标注。

---

## 9. 失败模式与缓解

| 风险 | 缓解 |
|---|---|
| Polymarket API 限流 | 30s 轮询 + 指数退避；候选池排名走日级离线任务，不影响实时路径 |
| 选人公式过拟合 | 评分窗口 90 天 + 样本量门槛；权重未来用回测调参而非主观调 |
| Source trader 一天疯狂开仓拖垮账户 | G2 日亏损上限熔断（事后兜底）；README 标注未启用 G3/G4 的权衡 |
| 同源重复跟单 | `our_positions` 唯一索引 `(source_trader, market_id, side)` |
| 跌出 top 10 的人持仓如何处置 | E1：继续持有到 resolve，不再跟新单（仓位状态置 `ORPHANED_HOLD`） |
| Dry-run / Live 模式混淆 | `trades.dry_run` 字段持久化；启动时打印当前模式并需要键盘确认（仅 live 模式） |
| 回测 vs 实盘差异 | 共享代码路径；README 列出回测不模拟的项 |

---

## 10. 范围外（明确不做）

- 加杠杆 / 借贷
- Twitter / Discord / 链下信号
- 自主行情判断（机器人不"思考"市场，只跟人）
- 多链支持（只 Polygon）
- Web UI（CLI + 日志足够）
- 通知系统（Slack / Telegram 等，第一版用 stdout）
