# AI 驱动的电竞鼠标竞品分析 Agent 协作系统

一套像「数字调研小组」一样工作的多 Agent 竞品分析平台：输入两款电竞鼠标，系统通过 **LangGraph DAG** 自动完成产品识别、数据采集、证据结构化、事实校验、质量门控与专业报告生成，**每条结论都绑定可追溯的证据（evidence_id），抓不到的数据如实标记缺失、绝不编造**。

> 技术关键词：LangGraph · FastAPI · React/TypeScript · MCP 工具层 · LLM 结构化抽取 · Evidence 可追溯 · Quality 反馈闭环 · LangSmith 可观测

垂直场景选择「电竞鼠标」，是因为它字段明确（重量/传感器/DPI/回报率/连接/续航/点击系统/驱动……）且体验与价格强依赖实时外部证据，最能展示专业化、结构化、可追溯的竞品分析能力。**换行业时只需替换该行业的专业 Schema 与数据需求配置，Agent DAG 主流程不变。**

---

## 系统架构（多 Agent DAG）

```text
ResearchAgent      调研规划：按 Schema 规划需要哪些数据
  → CollectorAgent   采集识别：实体消歧 + 读本地事实 + 调度 4 个 MCP
  → EvidenceAgent    证据结构化：统一 evidence_id / source / credibility
  → AnalysisAgent    分析：只分析有证据支撑的硬件/价格/体验差异
  → VerificationAgent 事实校验：数值 + 词面 grounding，拦截幻觉
  → QualityAgent     质量门控：算报告可信度，通过 / 有限通过 / 打回 / 降级
       │  approved / approved_with_limitations / partial_report
       ▼
  → AnalysisAI(SWOT) AI 解读：在前进路径上生成 SWOT（证据已校验，只跑一次）
  → ReportAgent      报告生成：汇总已验证结果，输出场景推荐 + 可追溯引用
```

- **反馈闭环（真，非伪）**：QualityAgent 可把不合格的工作**结构化打回** Research / Collector / Evidence / Analysis 重做，`MAX_ITERATIONS=3`。
- **不伪装成功、不默认阻塞**：自动修复达上限后生成 `partial_report` 并披露缺口，而不是卡死等人工。
- **结构化消息传递**：Agent 之间读写统一 `TypedDict` State 的固定字段（`merge_claims` / `merge_trace_log` / `merge_dict` reducer），不是自然语言对话；LLM 输出也强制为结构化 JSON。

---

## 核心特性

| 能力 | 说明 |
|------|------|
| **专业竞品 Schema** | `GamingMouseFinalReportSchema`（Pydantic）统一产品识别 / 硬件事实 / 评价测评 / 定价 / 证据链 / 场景推荐 |
| **Evidence 可追溯** | 每条 claim 必须引用 `evidence_ids`；无证据不进推荐，低可信来源必标注，缺数据必披露 |
| **幻觉抑制** | 数值 grounding（硬失败）+ 词面 grounding（弱支撑）+ 价格/人工反馈特判 |
| **质量门控** | `score = max(0, 90 − 扣分 − 待补惩罚)`，数据驱动而非写死 |
| **场景化推荐** | 不强行给唯一赢家：按「极限 FPS / 轻量化 / 续航 / 驱动 / 预算 / 手感 / 长期可靠性」分别给结论 |
| **人机协作闭环** | 现场人工反馈转为低可信、待验证的 evidence 进入校验链路，不直接覆盖报告、不能自证、不刷质量分 |
| **可观测性** | 每个 Agent 的 `trace_log`（step / status / 摘要 / duration）+ LangSmith 全链路 trace |

---

## MCP 工具层（已接入 4 个）

| MCP | 作用 | 关键设计 |
|-----|------|---------|
| **SearchMCP** | 未命中本地库时查找官网/评测候选 | Tavily 官方搜索 API；**只找候选，不写硬件字段** |
| **OfficialSpecMCP** | 从官网页面抽取硬件规格 | LLM 结构化抽取 + 多来源字段级合并补齐 |
| **PriceMCP** | 官方价 / 电商价 / fallback 价 | 反爬拦截标记 `official_price_blocked` + 离群价过滤 + 锚定中位价 |
| **ReviewIntelMCP** | 用户评价 / 博主测评 / 口碑信号 | reader 代理取正文（绕反爬、读视频字幕）+ Reddit 接口 + 跨源交叉印证 + 落盘缓存 |

**采集原则**：能从官网拿到的用高可信；电商/视频/搜索摘要为低可信 fallback；被反爬只标记降级、不绕过；所有来源统一转为 evidence 进入同一条校验链路。

---

## 数据策略：稳定事实 vs 实时采集

- **写进本地 JSON**（[data/products/gaming_mice.json](data/products/gaming_mice.json)，24 款）：官方型号 / 别名 / 官网 URL / 传感器 / DPI / 重量 / 连接等相对稳定的硬件事实，作为高可信底座。
- **必须实时采集**：实时价格、用户评价、博主测评、握法/手感/适合游戏、驱动口碑、长期可靠性——会随时间变化，必须来自真实外部证据。
- **双路线评价库（demo 对比）**：命中 [data/products/gaming_mice_reviews.json](data/products/gaming_mice_reviews.json) 的产品（如 GPX2）即时读取已结构化的评价信号；未命中的产品（如 Viper V4 Pro）走实时爬取路线。两条路线产出同一种结构化证据，下游一视同仁。

---

## 技术栈

- **后端**：Python · FastAPI · LangGraph（StateGraph）· Pydantic
- **前端**：React · TypeScript · Vite（图表/动画全部自研 CSS/SVG，无第三方图表库）
- **模型/检索**：DeepSeek（OpenAI 兼容）· Tavily Search API · Jina Reader（取正文）
- **可观测**：LangSmith trace

---

## 目录结构

```text
backend/
  api/routes.py               # 分析任务 / 报告 / trace / swot / feedback 接口
  orchestration/
    workflow.py               # LangGraph DAG（7 Agent + SWOT 节点 + 反馈闭环）
    state.py                  # CompetitiveAnalysisState + reducers
  app/agents/                 # research / collector / evidence / analysis
                              # verification / quality / report / analysis_ai(SWOT)
  app/services/               # 4×MCP · faithfulness · context_manager · metrics
                              # product_catalog · scoring · review_intel · swot_ai
  app/schemas/gaming_mouse.py # 电竞鼠标专业报告 Schema
data/products/
  gaming_mice.json            # 稳定硬件事实库（24 款）
  gaming_mice_reviews.json    # 本地评价库（双路线 database 路线）
frontend/src/                 # React 前端（Workflow 可视化 / Agent 详情 / 报告页）
docs/                         # 架构、Agent 协议、API、合规声明
```

---

## 快速开始

### 1. 配置后端环境变量 `backend/.env`

```text
# 检索
SEARCH_PROVIDER=tavily
TAVILY_API_KEY=...

# LLM（官网规格 / 价格 / 评价抽取，DeepSeek 兼容 OpenAI 协议）
ARK_BASE_URL=https://api.deepseek.com
OFFICIAL_SPEC_API_KEY=...   OFFICIAL_SPEC_MODEL=deepseek-v4-pro
PRICE_API_KEY=...           PRICE_MODEL=deepseek-v4-pro
REVIEW_INTEL_API_KEY=...    REVIEW_INTEL_MODEL=deepseek-v4-pro

# 数据来源：database（本地）| crawler（实时）| mock
RESEARCH_PROVIDER=database
```

> `.env` 已被 `.gitignore` 忽略，密钥不入仓。

### 2. 启动后端（默认 `http://127.0.0.1:8000`）

```bash
cd backend
./venv/Scripts/python.exe main.py
```

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev
```

---

## 验证

```bash
# 前端类型检查
cd frontend && npx tsc --noEmit

# 后端关键链路测试
cd backend
./venv/Scripts/python.exe test_product_compare_flow.py
./venv/Scripts/python.exe test_traceability.py
./venv/Scripts/python.exe test_context_and_faithfulness.py
```

---

## 合规

只采集公开网页信息、遇反爬不绕过只降级标记、不抓取隐私数据、密钥不入仓、外部数据保留 `source_url` 与可信度标记。完整说明见 [docs/合规声明.md](docs/合规声明.md)。

---

## 可拓展性

主流程（Agent DAG + 证据/校验/质检/报告）与行业无关。换到短视频软件、SaaS 工具、电商平台等场景时，只需：① 替换该行业的专业 Schema；② 替换数据需求配置。ResearchAgent 会按新 Schema 自动规划数据需求，CollectorAgent 复用 MCP 工具层，Evidence / Verification / Quality / Report 流程不变。
