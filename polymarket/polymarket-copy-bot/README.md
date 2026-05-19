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

## 风控说明（重要）

本机器人**只有一个硬风控**：`DAILY_LOSS_LIMIT`（日已实现亏损上限）。

**未启用的风控**（设计上的取舍）：
- **最大并发持仓数**：理论上 10 个 top trader 同时疯狂开仓可能堆出几十个仓位
- **单交易员最大敞口**：某个 top trader 一天连开 30 单，你按固定 $5 跟会有 $150 暴露

这些故意省略，以保持配置最简。`DAILY_LOSS_LIMIT` 作为事后熔断兜底——一旦今日已实现亏损达到上限，**新开仓被拒绝，但平仓继续允许**（让你能止损）。

代价：可能在熔断触发前已亏满当日上限。如果实盘运行中发现频繁触发熔断，请考虑在 `risk.py` 中加入：
- `MAX_OPEN_POSITIONS` 检查
- 单 source_trader 累计敞口检查

## 配置参考

见 `.env.example`。关键参数：

| 变量 | 默认 | 说明 |
|------|------|------|
| `COPY_AMOUNT_USD` | 5 | 每笔跟单的固定美元金额 |
| `DAILY_LOSS_LIMIT` | 50 | 日已实现亏损上限（熔断阈值） |
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
watcher.py            -> 30s 轮询 top_10 的活动，diff 出 OPEN/CLOSE 事件
risk.py               -> 日亏损熔断（事件 -> Executor 前的最后一道闸）
executor.py           -> DryRun 模式仅写日志；Live 模式调用 CLOB API
backtest.py           -> 用历史数据回放 watcher+executor，验证策略
main.py               -> CLI：rank / watch --dry-run|--live / backtest --days N
```

## 与 polymarket-arb-bot 的关系

并列的独立项目。共用同一个钱包（`.env` 配置可复制），但策略逻辑完全独立。
