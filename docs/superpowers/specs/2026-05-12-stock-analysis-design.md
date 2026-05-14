# Design: `stock-analysis` Skill

**Date:** 2026-05-12
**Author:** wwj
**Status:** Approved — ready for implementation planning
**Source:** `skill_demo.txt` (10 institutional-style analysis prompts)

---

## 1. Goal

Create a **global, English-named orchestrator skill** that routes any stock-related user query to one (or several) of 10 institutional-style analysis frameworks. Installed at `~/.claude/skills/stock-analysis/` so it is available across all Claude Code projects.

The skill exists alongside — and does not replace — the 10 existing Chinese-named specialist skills (`institutional-coverage-memo`, `morgan-stanley-technical-panel`, etc.). It provides a single English entry point with broad trigger coverage.

## 2. File Structure

```
~/.claude/skills/stock-analysis/
├── SKILL.md                          # Entry + routing table + global conventions
└── frameworks/
    ├── 01-coverage-memo.md           # 20-year analyst institutional coverage
    ├── 02-technical-panel.md         # Morgan Stanley technical panel
    ├── 03-risk-framework.md          # Bridgewater risk framework
    ├── 04-earnings-analyzer.md       # JPMorgan earnings analyzer
    ├── 05-dividend-analyzer.md       # BlackRock dividend analyzer
    ├── 06-sector-rotation.md         # Citadel sector rotation
    ├── 07-quant-screener.md          # Renaissance quant screener
    ├── 08-etf-portfolio.md           # Vanguard ETF portfolio builder
    ├── 09-options-architect.md       # D.E.Shaw options architect
    └── 10-macro-outlook.md           # Two Sigma macro outlook
```

**Rationale for split:** `SKILL.md` carries only routing logic and global conventions (~80 lines). Specific frameworks are loaded on demand via `Read`. A single 500-line file would waste tokens loading all 10 frameworks for every trigger.

## 3. SKILL.md Frontmatter

```yaml
---
name: stock-analysis
description: Use when user asks about any stock (US/A-share/HK), ticker symbol, sector, ETF, options, dividend, earnings, macro market, technical analysis, fundamental analysis, or investment decision. Routes to 10 institutional-style analysis frameworks (Morgan Stanley, Bridgewater, JPM, BlackRock, Citadel, Renaissance, Vanguard, D.E.Shaw, Two Sigma). Triggers on phrases like "分析XXX"、"这只股票"、"美股"、"ticker"、"看涨/看跌"、"技术面"、"财报"、"股息"、"板块轮动"、"期权"、"宏观".
---
```

## 4. Routing Table (lives in SKILL.md body)

| User question signal | Route to framework file |
|---|---|
| "分析 XXX", "这只股票怎么样", "基本面", "fundamental" | `01-coverage-memo.md` |
| "技术面", "支撑位", "阻力位", "RSI", "MACD", "K线" | `02-technical-panel.md` |
| "风险", "回撤", "Beta", "压力测试", "波动率" | `03-risk-framework.md` |
| "财报", "earnings", "业绩", "EPS", "guidance" | `04-earnings-analyzer.md` |
| "股息", "分红", "dividend", "yield", "派息率" | `05-dividend-analyzer.md` |
| "板块", "sector", "轮动", "rotation" | `06-sector-rotation.md` |
| "筛选", "量化", "screener", "factor" | `07-quant-screener.md` |
| "ETF", "组合", "资产配置", "portfolio" | `08-etf-portfolio.md` |
| "期权", "options", "看涨/看跌", "covered call", "iron condor" | `09-options-architect.md` |
| "宏观", "美联储", "GDP", "通胀", "macro" | `10-macro-outlook.md` |

**Combination support:** "分析 AAPL 含技术面 + 风险" → read 01 + 02 + 03 sequentially. Each framework produces an independent section; a final synthesis paragraph reconciles them.

## 5. Framework File Format

Each `frameworks/NN-*.md` file is self-contained and contains:

1. **Header** — framework name + persona (e.g., "20-year senior analyst at $2T AM division")
2. **Required inputs** — what the user must provide (ticker, time horizon, etc.) and what is optional
3. **Output sections** — the exact bullets from `skill_demo.txt` for that framework
4. **Output format spec** — section order, table layout, where the executive summary goes
5. **Data-gap protocol** — when public data is missing, label "基于公开信息估算" or request the data point from the user

## 6. Global Conventions (SKILL.md body)

- **Output language:** Simplified Chinese. Preserve English for: ticker symbols, sector names, indicator names (RSI/MACD/Beta), and proper nouns (Morgan Stanley, etc.).
- **Disclaimer:** Every report ends with: `> ⚠️ 本报告为模拟机构风格分析，不构成投资建议。`
- **Data sourcing:** If `mcp__financial-datasets__*` tools are available in the environment, prefer them for current price / earnings / financials. Otherwise mark assumed values explicitly.
- **Multi-framework composition:** When 2+ frameworks are invoked, each renders its full report independently. After all frameworks complete, append a **综合判决** section (≤200 words) that reconciles signals.
- **No silent fallback:** If a required data point is missing and no MCP tool can supply it, stop and ask the user — do not fabricate.

## 7. Relationship to Existing Skills

The 10 existing Chinese skills (`institutional-coverage-memo`, `morgan-stanley-technical-panel`, `bridgewater-risk-framework`, `jpmorgan-earnings-analyzer`, `blackrock-dividend-analyzer`, `citadel-sector-rotation`, `renaissance-quant-screener`, `vanguard-etf-portfolio-builder`, `deshaw-options-architect`, `twosigma-macro-outlook`) remain untouched.

Trigger orthogonality:
- `stock-analysis` triggers on **broad/English/mixed** queries → general entry
- Existing Chinese skills trigger on **specific brand-named** queries (e.g., "贝莱德风格股息") → specialist path

Content in `frameworks/*.md` is fully self-contained — no cross-skill dependency. If a user uninstalls the Chinese skills, `stock-analysis` still works.

## 8. Testing / Verification

Before marking the implementation done:

1. **Trigger test** — confirm SKILL.md is discovered when prompts like "帮我分析 AAPL", "What's TSLA's technical setup?", "美联储加息对板块影响" are issued in a fresh session.
2. **Routing test** — for each of the 10 trigger categories, verify the correct `frameworks/NN-*.md` is read.
3. **Composition test** — verify a combined prompt ("AAPL 基本面 + 风险 + 期权策略") loads 01 + 03 + 09 and produces a unified report with a synthesis section.
4. **Disclaimer test** — every generated report ends with the standard disclaimer line.

## 9. Out of Scope

- Real-time data fetching beyond what existing MCP tools provide.
- Rewriting or deprecating the 10 Chinese specialist skills.
- A separate command (`/stock-analysis`) — this is a skill, not a slash command. Activation is automatic via trigger keywords.
- Backtesting infrastructure or persistent portfolio state.
