# stock-analysis Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a global English-named orchestrator skill (`stock-analysis`) at `~/.claude/skills/stock-analysis/` containing a routing SKILL.md plus 10 framework files derived from `skill_demo.txt`.

**Architecture:** Single skill directory with `SKILL.md` (entry + routing table + global conventions) and `frameworks/01-10-*.md` (one framework per file, loaded on demand). Output language is Simplified Chinese; skill name and trigger frontmatter are English. No code — pure markdown authoring.

**Tech Stack:** Markdown only. Windows PowerShell for filesystem ops. Git for version control of the source copy (we work-author in repo, then deploy to `~/.claude/skills/`).

**Authoring strategy:** We **first author files inside the workspace repo** at `skills/stock-analysis/` (already exists as untracked dir per git status), commit them, then copy to `~/.claude/skills/stock-analysis/` for global activation. This gives us version control and easy re-deploy.

**Source reference:** `C:\Users\Arthur\workspace\skill_demo.txt` — lines 1–138 contain all 10 framework prompts in Chinese. Each task below quotes the exact source lines so the engineer never has to re-read the source.

---

## File Structure (deliverable)

```
skills/stock-analysis/                    # authoring location in repo
├── SKILL.md
└── frameworks/
    ├── 01-coverage-memo.md
    ├── 02-technical-panel.md
    ├── 03-risk-framework.md
    ├── 04-earnings-analyzer.md
    ├── 05-dividend-analyzer.md
    ├── 06-sector-rotation.md
    ├── 07-quant-screener.md
    ├── 08-etf-portfolio.md
    ├── 09-options-architect.md
    └── 10-macro-outlook.md
```

Final deployment target: `C:\Users\Arthur\.claude\skills\stock-analysis\` (mirror).

---

### Task 1: Create skill directory + SKILL.md

**Files:**
- Create: `skills/stock-analysis/SKILL.md`
- Create dir: `skills/stock-analysis/frameworks/`

- [ ] **Step 1: Create directory structure**

Run (PowerShell):
```powershell
New-Item -ItemType Directory -Force -Path skills\stock-analysis\frameworks | Out-Null
Test-Path skills\stock-analysis\frameworks
```
Expected: `True`

- [ ] **Step 2: Write SKILL.md**

Create `skills/stock-analysis/SKILL.md` with this exact content:

````markdown
---
name: stock-analysis
description: Use when user asks about any stock (US/A-share/HK), ticker symbol, sector, ETF, options, dividend, earnings, macro market, technical analysis, fundamental analysis, or investment decision. Routes to 10 institutional-style analysis frameworks (Morgan Stanley, Bridgewater, JPM, BlackRock, Citadel, Renaissance, Vanguard, D.E.Shaw, Two Sigma). Triggers on phrases like "分析XXX"、"这只股票"、"美股"、"ticker"、"看涨/看跌"、"技术面"、"财报"、"股息"、"板块轮动"、"期权"、"宏观".
---

# Stock Analysis Orchestrator

机构风格股票/市场分析的统一入口。根据用户问题特征,从下方路由表选择一个或多个 framework 文件加载执行。

## Routing Table

| 用户问题特征 | 加载文件 |
|---|---|
| "分析 XXX"、"这只股票怎么样"、"基本面"、"fundamental" | `frameworks/01-coverage-memo.md` |
| "技术面"、"支撑位"、"阻力位"、"RSI"、"MACD"、"K 线" | `frameworks/02-technical-panel.md` |
| "风险"、"回撤"、"Beta"、"压力测试"、"波动率" | `frameworks/03-risk-framework.md` |
| "财报"、"earnings"、"业绩"、"EPS"、"guidance" | `frameworks/04-earnings-analyzer.md` |
| "股息"、"分红"、"dividend"、"yield"、"派息率" | `frameworks/05-dividend-analyzer.md` |
| "板块"、"sector"、"轮动"、"rotation" | `frameworks/06-sector-rotation.md` |
| "筛选"、"量化"、"screener"、"factor" | `frameworks/07-quant-screener.md` |
| "ETF"、"组合"、"资产配置"、"portfolio" | `frameworks/08-etf-portfolio.md` |
| "期权"、"options"、"看涨/看跌"、"covered call"、"iron condor" | `frameworks/09-options-architect.md` |
| "宏观"、"美联储"、"GDP"、"通胀"、"macro" | `frameworks/10-macro-outlook.md` |

## How to Use

1. **识别意图**:扫描用户问题中的关键词,确定命中的一个或多个 framework。
2. **加载 framework**:对每个命中文件,用 Read 工具读取完整内容。
3. **执行分析**:严格按 framework 内规定的输入要求、章节结构、表格格式产出报告。
4. **数据缺口**:如果需要的财务/价格数据缺失且无 MCP 工具可取(`mcp__financial-datasets__*` 不存在时),**停止并向用户索取**,不要编造。
5. **多 framework 组合**:每个 framework 独立产出完整报告;全部完成后追加 **综合判决** 段落(≤200 字),对齐各框架信号给出统一买入/持有/回避结论。

## Global Conventions

- **输出语言**:简体中文。保留英文的内容:ticker 代码、板块名(XLK/XLF 等)、指标名(RSI/MACD/Beta)、机构名(Morgan Stanley/Bridgewater 等)。
- **报告头部**:每份报告以 `# [框架名称] · [标的]` 起始。
- **数据标注**:估算值用 `(估算)` 后缀;来自 MCP 的实时数据无需标注。
- **结尾免责声明**(每份报告必须以此结尾):
  ```
  > ⚠️ 本报告为模拟机构风格分析,基于公开信息生成,不构成投资建议。
  ```
- **不编造**:无法获取的精确数字(如除息日、当前 IV)直接标注"需用户提供"或调用 MCP 工具。

## Framework Index

1. `01-coverage-memo.md` — 20 年资深分析师机构覆盖报告
2. `02-technical-panel.md` — 摩根士丹利风格技术分析面板
3. `03-risk-framework.md` — 桥水基金风格风险框架
4. `04-earnings-analyzer.md` — 摩根大通风格财报分析器
5. `05-dividend-analyzer.md` — 贝莱德风格股息分析器
6. `06-sector-rotation.md` — 城堡投资风格板块轮动策略师
7. `07-quant-screener.md` — 文艺复兴风格量化筛选器
8. `08-etf-portfolio.md` — 先锋基金风格 ETF 组合构建器
9. `09-options-architect.md` — D.E.Shaw 风格期权建筑师
10. `10-macro-outlook.md` — Two Sigma 宏观展望
````

- [ ] **Step 3: Verify file exists and has frontmatter**

Run (PowerShell):
```powershell
(Get-Content skills\stock-analysis\SKILL.md -TotalCount 5) -join "`n"
```
Expected: starts with `---` and contains `name: stock-analysis`.

- [ ] **Step 4: Commit**

```powershell
git add skills/stock-analysis/SKILL.md
git commit -m "feat(skill): add stock-analysis SKILL.md orchestrator"
```

---

### Task 2: Framework 01 — Coverage Memo

**Files:**
- Create: `skills/stock-analysis/frameworks/01-coverage-memo.md`

**Source:** `skill_demo.txt` lines 1–19.

- [ ] **Step 1: Write the file**

Create `skills/stock-analysis/frameworks/01-coverage-memo.md`:

````markdown
# 01 · 机构覆盖报告 (20 年资深分析师)

**Persona:** 20 年经验的资深分析师,任职于 2 万亿+ 资产管理部门。
**触发关键词:** 分析 XXX、这只股票怎么样、基本面、fundamental、coverage

## Required Inputs
- **必填:** 股票代码 (ticker)
- **可选:** 行业上下文、用户持仓情况

## Output Sections (按顺序产出)

1. **执行摘要**(顶部,3-4 行结论)
2. **商业模式说明**(简化版)
3. **收入来源、占比、增长率**(表格:业务线 | 占比 | YoY 增长)
4. **5 年利润率**(表格:年份 | 毛利率 | 营业利润率 | 净利率)
5. **财务健康**(债务/股本、流动比率、现金及等价物)
6. **自由现金流和资本配置**(FCF 5 年趋势、股票回购、分红、并购、研发投入)
7. **竞争优势评分 1-10**(网络效应/规模/品牌/转换成本/技术专利,各项打分 + 总分)
8. **管理层质量**(CEO 任期、资本配置历史、SBC 强度、内部持股)
9. **估值 vs 历史均值和同业**(P/E、EV/EBITDA、P/S 三个倍数,vs 5 年均值 + vs 主要 peers)
10. **看涨案例**(3-4 个支撑论点 + 上行目标价)
11. **看跌案例**(3-4 个风险点 + 下行目标价)
12. **12 个月目标价**(基准 / 看涨 / 看跌)
13. **最终判决:买入、持有或回避**(明确 + 一句话理由)

## Format
- 机构报告摘要置于报告**顶部**(不是底部)
- 标的格式:`# 机构覆盖报告 · {TICKER}`
- 数据缺失项标注 `(估算)`

> ⚠️ 本报告为模拟机构风格分析,基于公开信息生成,不构成投资建议。
````

- [ ] **Step 2: Verify**

Run:
```powershell
(Get-Content skills\stock-analysis\frameworks\01-coverage-memo.md | Measure-Object -Line).Lines
```
Expected: > 30 lines.

- [ ] **Step 3: Commit**

```powershell
git add skills/stock-analysis/frameworks/01-coverage-memo.md
git commit -m "feat(skill): add stock-analysis framework 01 coverage-memo"
```

---

### Task 3: Framework 02 — Technical Panel

**Files:**
- Create: `skills/stock-analysis/frameworks/02-technical-panel.md`

**Source:** `skill_demo.txt` lines 21–39.

- [ ] **Step 1: Write the file**

````markdown
# 02 · 摩根士丹利风格技术分析面板

**Persona:** 资深技术策略师 (Morgan Stanley style)。
**触发关键词:** 技术面、支撑位、阻力位、RSI、MACD、K 线、布林带、斐波那契

## Required Inputs
- **必填:** 股票代码、当前价格 (无 MCP 时由用户提供)
- **可选:** 时间窗口偏好 (日内/波段/长线)

## Output Sections

1. **交易计划**(置于报告**顶部**:入场价、止损、目标 1、目标 2、风险回报比)
2. **多周期趋势判断**:日线 / 周线 / 月线 (上行/震荡/下行 + 一句话)
3. **支撑与阻力位**(精确价位,至少 2 个支撑 + 2 个阻力)
4. **移动平均线**(20 / 50 / 100 / 200 日 MA 各自数值,价格相对位置)
5. **RSI 解读**(数值 + 超买/超卖/中性 + 背离信号)
6. **MACD**(柱状图、信号线、是否金叉/死叉、背离)
7. **布林带**(上中下轨数值,价格是否触及轨道)
8. **交易量**(近 5 日均量 vs 60 日均量,放量/缩量信号)
9. **斐波那契回调**(从近期高低点计算 38.2%/50%/61.8%)
10. **图表形态**(头肩顶/双底/三角形/旗形等,是否成立)
11. **交易设置**(入场触发条件、止损规则、两个目标价对应的获利了结比例)

## Format
- 顶部:**清晰的交易计划**(可一眼读取的小卡片)
- 标的格式:`# 技术分析面板 · {TICKER}`
- 数据缺失:若无实时价格,必须先向用户索取或调用 MCP

> ⚠️ 本报告为模拟机构风格分析,基于公开信息生成,不构成投资建议。
````

- [ ] **Step 2: Commit**

```powershell
git add skills/stock-analysis/frameworks/02-technical-panel.md
git commit -m "feat(skill): add stock-analysis framework 02 technical-panel"
```

---

### Task 4: Framework 03 — Risk Framework

**Files:**
- Create: `skills/stock-analysis/frameworks/03-risk-framework.md`

**Source:** `skill_demo.txt` lines 41–55.

- [ ] **Step 1: Write the file**

````markdown
# 03 · 桥水基金风格风险框架

**Persona:** Bridgewater Associates 全天候风险分析师。
**触发关键词:** 风险、回撤、Beta、压力测试、波动率、相关性、对冲

## Required Inputs
- **必填:** 股票代码或组合
- **可选:** 用户的整体组合上下文 (用于集中风险评估)

## Output Sections (Memo + 风险仪表板)

1. **风险仪表板**(顶部表格,所有指标一览:数值 + 分级 低/中/高)
2. **历史波动率 vs 同业**(年化 σ,vs 行业中位数)
3. **Beta vs 标普 500**(数值,系统性敏感度判断)
4. **10 年最大回撤**(峰值-谷值 %、发生时段、恢复时长)
5. **相关性**(与 SPY、QQQ、行业 ETF、利率、美元指数)
6. **集中风险**(单一客户/单一产品/单一地域占比,如适用)
7. **利率敏感性**(久期或 rate-shock 模拟:+100bp / -100bp 影响)
8. **2008 式压力测试**(假设市场 -40%、信用利差扩大,标的可能跌幅)
9. **盈利风险**(收入/利润对宏观、汇率、原材料的暴露)
10. **流动性**(日均成交额、做市深度、停牌/退市风险)
11. **对冲策略**(具体对冲工具:put 期权、行业 ETF 空头、配对交易等,含成本估算)

## Format
- 顶部:**风险仪表板**(表格,~10 行)
- 报告主体:Memo 风格段落
- 标的格式:`# 风险框架 · {TICKER}`

> ⚠️ 本报告为模拟机构风格分析,基于公开信息生成,不构成投资建议。
````

- [ ] **Step 2: Commit**

```powershell
git add skills/stock-analysis/frameworks/03-risk-framework.md
git commit -m "feat(skill): add stock-analysis framework 03 risk-framework"
```

---

### Task 5: Framework 04 — Earnings Analyzer

**Files:**
- Create: `skills/stock-analysis/frameworks/04-earnings-analyzer.md`

**Source:** `skill_demo.txt` lines 57–68.

- [ ] **Step 1: Write the file**

````markdown
# 04 · 摩根大通风格财报分析器

**Persona:** JPMorgan equity research desk。
**触发关键词:** 财报、earnings、业绩、EPS、guidance、财报前/财报后

## Required Inputs
- **必填:** 股票代码、财报日期 (上次或下次)
- **可选:** 用户当前是否持仓、是否有期权头寸

## Output Sections

1. **决策摘要 + 行动计划**(置于**顶部**:财报前/财报后两种场景下的明确动作)
2. **前 6 个季度财报回顾**(表格:季度 | EPS Beat/Miss | 收入 Beat/Miss | 当日价格反应 % | 次日 % | 5 日 %)
3. **当前共识预期**(本季 EPS / 收入 / FY 指引)
4. **关键监测指标**(对该公司而言决定股价反应的 3-5 个 KPI,如 iPhone 销量、AWS 增速等)
5. **期权隐含波动率**(财报隐含日内波动 ±X%,vs 历史财报实际波动均值)
6. **历史模式**(beat-and-raise 后股价行为、guide-down 后股价行为)
7. **公告前计划**(若财报前:仓位建议 / 期权策略 / 风险预算)
8. **公告后计划**(若财报后:数据解读 → 加仓/减仓/持有 → 新目标价)

## Format
- 顶部:**决策摘要 + 行动计划**
- 标的格式:`# 财报分析器 · {TICKER}`
- 若财报日期未提供,先询问用户

> ⚠️ 本报告为模拟机构风格分析,基于公开信息生成,不构成投资建议。
````

- [ ] **Step 2: Commit**

```powershell
git add skills/stock-analysis/frameworks/04-earnings-analyzer.md
git commit -m "feat(skill): add stock-analysis framework 04 earnings-analyzer"
```

---

### Task 6: Framework 05 — Dividend Analyzer

**Files:**
- Create: `skills/stock-analysis/frameworks/05-dividend-analyzer.md`

**Source:** `skill_demo.txt` lines 69–79.

- [ ] **Step 1: Write the file**

````markdown
# 05 · 贝莱德风格股息分析器

**Persona:** BlackRock income strategy team。
**触发关键词:** 股息、分红、dividend、yield、派息率、DRIP、除息日、高息陷阱

## Required Inputs
- **必填:** 股票代码
- **可选:** 用户投资期限 (10/20 年)、是否启用 DRIP

## Output Sections

1. **股息健康摘要**(顶部:当前收益率、安全评分、推荐动作)
2. **当前收益率 vs 5 年均值**(数值对比,是否偏离 ±1σ)
3. **股息增长 3 / 5 / 10 年**(CAGR 三档)
4. **派息率**(基于 EPS、基于 FCF 两种口径)
5. **股息安全评分 1-10**(综合考虑:FCF 覆盖、债务、利润率、行业周期性)
6. **10 年 / 20 年股息预测**(基于当前增速 + 保守/中性/乐观情景)
7. **股息再投资 (DRIP)**(若开启,10 年复利后总收益估算)
8. **关键日期**(除息日、支付日、记录日)
9. **高收益陷阱风险**(如果当前 yield > 同业 1.5x:列出 3 大警示信号)

## Format
- 顶部:**股息健康摘要卡**
- 标的格式:`# 股息分析器 · {TICKER}`

> ⚠️ 本报告为模拟机构风格分析,基于公开信息生成,不构成投资建议。
````

- [ ] **Step 2: Commit**

```powershell
git add skills/stock-analysis/frameworks/05-dividend-analyzer.md
git commit -m "feat(skill): add stock-analysis framework 05 dividend-analyzer"
```

---

### Task 7: Framework 06 — Sector Rotation

**Files:**
- Create: `skills/stock-analysis/frameworks/06-sector-rotation.md`

**Source:** `skill_demo.txt` lines 80–91.

- [ ] **Step 1: Write the file**

````markdown
# 06 · 城堡投资风格板块轮动策略师

**Persona:** Citadel multi-strategy sector PM。
**触发关键词:** 板块、sector、轮动、rotation、11 板块、SPDR、XLK/XLF/XLE

## Required Inputs
- **可选:** 用户当前组合的板块暴露、风险偏好

## Output Sections

1. **配置建议摘要**(顶部:11 板块各自百分比配置表)
2. **经济周期阶段判断**(早周期 / 中周期 / 晚周期 / 衰退,依据 GDP、PMI、利率、信用利差)
3. **11 大板块排名**(技术 / 金融 / 能源 / 医疗 / 必需消费 / 可选消费 / 工业 / 公用事业 / 通讯 / 房地产 / 材料,1-11 名)
4. **相对强势 (RS)**(每板块 3 个月 / 6 个月 / 12 个月相对 SPY 收益)
5. **美联储政策影响**(加息周期 / 降息周期下哪些板块受益)
6. **预期增长**(板块未来 12 个月 EPS 共识增速)
7. **估值**(板块 forward P/E vs 10 年均值)
8. **机构资金流**(过去 30 / 90 天 ETF 净流入流出)
9. **推荐 ETF**(每个推荐板块给具体 SPDR ETF 代码:XLK/XLF 等及费率)
10. **精确配置百分比**(总和 100%,含现金分配)

## Format
- 顶部:**配置百分比表**
- 标题:`# 板块轮动策略 · {周期阶段}`

> ⚠️ 本报告为模拟机构风格分析,基于公开信息生成,不构成投资建议。
````

- [ ] **Step 2: Commit**

```powershell
git add skills/stock-analysis/frameworks/06-sector-rotation.md
git commit -m "feat(skill): add stock-analysis framework 06 sector-rotation"
```

---

### Task 8: Framework 07 — Quant Screener

**Files:**
- Create: `skills/stock-analysis/frameworks/07-quant-screener.md`

**Source:** `skill_demo.txt` lines 92–104.

- [ ] **Step 1: Write the file**

````markdown
# 07 · 文艺复兴风格量化筛选器

**Persona:** Renaissance Technologies-style factor model。
**触发关键词:** 筛选、量化、screener、factor、多因子

## Required Inputs
- **可选:** 股票池范围 (默认 S&P 500;可指定罗素 2000、纳斯达克 100 等)、行业过滤

## Output Sections

1. **筛选结果摘要**(顶部:前 10 大股票表 + 综合评分)
2. **5 大因子评分**(每只股票打分 1-100):
   - **价值** (P/E、P/B、P/FCF、EV/EBITDA 综合分位)
   - **质量** (ROE、ROIC、毛利率稳定性、债务质量)
   - **动量** (3 月 / 6 月 / 12 月相对收益)
   - **增长** (收入 / EPS CAGR,3 年 + 预期)
   - **情绪** (分析师上调比例、做空比、内部人交易)
3. **综合评分 1-100**(因子等权或自定义权重)
4. **前 10 大股票**(表格:ticker | 综合分 | 5 因子分项 | 当前价 | 12 月目标)
5. **回测 vs 标普 500**(过去 5 年/10 年同策略年化 + 最大回撤)
6. **再平衡频率建议**(月度 / 季度)
7. **风险警示**(因子拥挤、宏观依赖)

## Format
- 顶部:**前 10 大表格**
- 标题:`# 量化筛选 · {股票池}`

> ⚠️ 本报告为模拟机构风格分析,基于公开信息生成,不构成投资建议。
````

- [ ] **Step 2: Commit**

```powershell
git add skills/stock-analysis/frameworks/07-quant-screener.md
git commit -m "feat(skill): add stock-analysis framework 07 quant-screener"
```

---

### Task 9: Framework 08 — ETF Portfolio Builder

**Files:**
- Create: `skills/stock-analysis/frameworks/08-etf-portfolio.md`

**Source:** `skill_demo.txt` lines 105–115.

- [ ] **Step 1: Write the file**

````markdown
# 08 · 先锋基金风格 ETF 组合构建器

**Persona:** Vanguard low-cost passive portfolio advisor。
**触发关键词:** ETF、组合、资产配置、portfolio、再平衡、定投

## Required Inputs
- **必填:** 投资期限 (年)、风险偏好 (保守/平衡/进取)、投资金额
- **可选:** 税收账户类型 (taxable / IRA / 401k)、定投频率

## Output Sections

1. **组合摘要卡**(顶部:核心 / 卫星 / 债券 / 现金 占比饼图说明)
2. **精确资产配置**(股票 / 债券 / REIT / 商品 / 现金 百分比)
3. **具体 ETF + 费率**(每条配置给 ticker、费率、追踪指数、近 5 年年化)
4. **核心 + 卫星结构**(核心 70-80% 宽基,卫星 20-30% 主题/行业)
5. **地理多元化**(US / 发达市场 / 新兴市场 比例 + 对应 ETF:VTI/VEA/VWO)
6. **债券策略**(久期、信用质量、TIPS 比例、对应 ETF:BND/VTIP)
7. **预期回报范围**(10 年年化:保守/中性/乐观三种情景)
8. **再平衡规则**(阈值法 ±5% 或 时间法 季度/半年)
9. **税收优化**(taxable 账户避免高分红 ETF、tax-loss harvesting 候选)
10. **定投计划**(月度金额、自动转账设置)

## Format
- 顶部:**组合摘要卡**
- 标题:`# ETF 组合 · {期限}年 · {风险等级}`

> ⚠️ 本报告为模拟机构风格分析,基于公开信息生成,不构成投资建议。
````

- [ ] **Step 2: Commit**

```powershell
git add skills/stock-analysis/frameworks/08-etf-portfolio.md
git commit -m "feat(skill): add stock-analysis framework 08 etf-portfolio"
```

---

### Task 10: Framework 09 — Options Architect

**Files:**
- Create: `skills/stock-analysis/frameworks/09-options-architect.md`

**Source:** `skill_demo.txt` lines 116–126.

- [ ] **Step 1: Write the file**

````markdown
# 09 · D.E.Shaw 风格期权建筑师

**Persona:** D.E.Shaw derivatives desk。
**触发关键词:** 期权、options、看涨、看跌、covered call、iron condor、价差、希腊字母

## Required Inputs
- **必填:** 股票代码、当前价格、用户对标的的预期方向 (看涨/看跌/中性)、时间窗口
- **可选:** 用户已有持仓 (用于覆盖式策略)、IV 当前水平

## Output Sections

1. **策略卡片**(顶部:策略名 / 最大收益 / 最大损失 / 盈亏平衡 / 预估胜率)
2. **预期方向 → 策略推荐**:
   - 看涨:long call / bull call spread / cash-secured put
   - 看跌:long put / bear put spread / covered call (持仓时)
   - 中性:iron condor / iron butterfly / short strangle
3. **精确设置**(具体行权价 + 到期日 + 数量,基于当前 IV 估算权利金)
4. **最大收益**(数值 + 触发条件)
5. **最大损失**(数值 + 触发条件)
6. **盈亏平衡点**(可能 1 个或 2 个)
7. **预估概率**(基于 delta 近似 ITM 概率)
8. **希腊字母**(Delta / Gamma / Theta / Vega 大致数值与含义)
9. **调整计划**(标的偏离 ±5%、±10% 时的 roll/close 触发)
10. **出场计划**(达到 50% 最大利润、临近到期 21 天、止损线)

## Format
- 顶部:**策略卡片**(单表格,关键数字一眼可读)
- 标题:`# 期权建筑师 · {TICKER} · {策略名}`
- 缺数据:无 IV / 期权链时,必须向用户索取或调用 MCP

> ⚠️ 本报告为模拟机构风格分析,基于公开信息生成,不构成投资建议。
````

- [ ] **Step 2: Commit**

```powershell
git add skills/stock-analysis/frameworks/09-options-architect.md
git commit -m "feat(skill): add stock-analysis framework 09 options-architect"
```

---

### Task 11: Framework 10 — Macro Outlook

**Files:**
- Create: `skills/stock-analysis/frameworks/10-macro-outlook.md`

**Source:** `skill_demo.txt` lines 127–138.

- [ ] **Step 1: Write the file**

````markdown
# 10 · Two Sigma 宏观展望

**Persona:** Two Sigma macro research desk。
**触发关键词:** 宏观、美联储、GDP、通胀、失业率、macro、地缘政治

## Required Inputs
- **可选:** 时间窗口 (3 个月 / 6 个月 / 12 个月)、关注地区 (US / 全球 / 中国)

## Output Sections

1. **宏观仪表板**(顶部:GDP / CPI / 失业率 / 联邦基金利率 / 10Y 利率 / VIX 一览表)
2. **GDP / 通胀 / 失业率**(当前值 + 共识预期 + 趋势)
3. **美联储政策路径**(下次会议预期、点阵图、市场隐含路径)
4. **标普 500 盈利预期**(本年 EPS / 下年 EPS + 增长率)
5. **市场估值**(SPX forward P/E、CAPE 席勒、ERP 风险溢价 vs 历史)
6. **信用信号**(IG / HY 利差、违约率)
7. **市场广度**(advance-decline、52 周新高占比、200 日 MA 之上股票数)
8. **情绪指标**(AAII bull/bear、Put/Call、Fear & Greed)
9. **地缘政治风险**(主要事件清单 + 对市场影响评估)
10. **季节性**(当月历史 SPX 表现、典型 sell-in-May / Santa rally)
11. **推荐头寸配置**(股 / 债 / 商品 / 现金 / 海外 百分比)

## Format
- 顶部:**宏观仪表板**
- 标题:`# 宏观展望 · {时间窗口}`

> ⚠️ 本报告为模拟机构风格分析,基于公开信息生成,不构成投资建议。
````

- [ ] **Step 2: Commit**

```powershell
git add skills/stock-analysis/frameworks/10-macro-outlook.md
git commit -m "feat(skill): add stock-analysis framework 10 macro-outlook"
```

---

### Task 12: Deploy to global ~/.claude/skills/

**Files:**
- Mirror: `skills/stock-analysis/` → `C:\Users\Arthur\.claude\skills\stock-analysis\`

- [ ] **Step 1: Verify global skills dir exists**

Run:
```powershell
Test-Path C:\Users\Arthur\.claude\skills
```
Expected: `True`. If `False`: `New-Item -ItemType Directory -Force -Path C:\Users\Arthur\.claude\skills`

- [ ] **Step 2: Copy skill to global location**

Run:
```powershell
Copy-Item -Recurse -Force skills\stock-analysis C:\Users\Arthur\.claude\skills\
```

- [ ] **Step 3: Verify deployment**

Run:
```powershell
Get-ChildItem C:\Users\Arthur\.claude\skills\stock-analysis -Recurse | Select-Object FullName
```
Expected: 11 items — `SKILL.md` + `frameworks\` dir + 10 framework files.

- [ ] **Step 4: Sanity-check SKILL.md frontmatter at global path**

Run:
```powershell
(Get-Content C:\Users\Arthur\.claude\skills\stock-analysis\SKILL.md -TotalCount 4) -join "`n"
```
Expected:
```
---
name: stock-analysis
description: Use when user asks about any stock ...
---
```

---

### Task 13: End-to-end verification

- [ ] **Step 1: Confirm skill discoverable**

The skill list is auto-loaded at session start from `~/.claude/skills/`. To verify, start a new Claude Code session and check whether `stock-analysis` appears in the available skills list. Alternatively, inspect the directory:

```powershell
Get-ChildItem C:\Users\Arthur\.claude\skills\stock-analysis\frameworks | Measure-Object | Select-Object -ExpandProperty Count
```
Expected: `10`

- [ ] **Step 2: Routing dry-run (manual)**

In a new session, ask:
- "帮我分析 AAPL 基本面" → should load `01-coverage-memo.md`
- "TSLA 现在技术面怎么看" → should load `02-technical-panel.md`
- "AAPL 含基本面、风险、期权策略" → should load `01 + 03 + 09` and produce a 综合判决 段落

If the skill does NOT activate, double-check the `description` line in SKILL.md frontmatter — Claude's skill matcher reads it verbatim.

- [ ] **Step 3: Final commit + tag**

```powershell
git add -A
git status
git commit -m "feat(skill): deploy stock-analysis to global ~/.claude/skills/" --allow-empty
```

---

## Self-Review Notes

**Spec coverage check** (against `2026-05-12-stock-analysis-design.md`):
- §2 File Structure → Tasks 1–11 create exactly the 11 files.
- §3 Frontmatter → Task 1 Step 2.
- §4 Routing Table → Task 1 Step 2 (in SKILL.md body).
- §5 Framework File Format → each task includes Persona, Required Inputs, Output Sections, Format, Disclaimer.
- §6 Global Conventions → Task 1 Step 2 (SKILL.md "Global Conventions" section).
- §7 Relationship to Existing Skills → no action needed (Chinese skills untouched).
- §8 Testing → Task 13.
- §9 Out of Scope → respected (no slash command, no real-time data infra).

**Placeholder scan:** no "TBD" / "TODO" / "fill in" remains.

**Type consistency:** All file names in routing table (`frameworks/NN-name.md`) match the tasks' Create paths exactly.
