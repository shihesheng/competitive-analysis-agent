/* 电竞鼠标竞品分析 Agent 协作系统 — 答辩 PPT 生成器
   Dark "midnight engineering" theme, grounded in the real codebase. */
const pptxgen = require("pptxgenjs");
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5
const W = 13.33, H = 7.5;
pres.author = "电竞鼠标竞品分析 Agent 团队";
pres.title = "AI 驱动的电竞鼠标竞品分析 Agent 协作系统";

// ---- palette (matches the app: slate-950 + cyan/violet) ----
const C = {
  bg: "0B1120", bg2: "0E1626", card: "131D31", card2: "182542",
  line: "263247", lineHi: "33425E",
  white: "F1F5F9", text: "CBD5E1", mut: "8DA0BC", dim: "5C6B83",
  cyan: "38BDF8", cyanD: "0EA5E9", violet: "A78BFA", emerald: "34D399",
  amber: "FBBF24", rose: "FB7185", sky: "7DD3FC",
};
const F = { h: "Microsoft YaHei", b: "Microsoft YaHei", mono: "Consolas" };
const ACC = [C.cyan, C.violet, C.emerald, C.amber, C.rose, C.sky];
const sh = () => ({ type: "outer", color: "000000", blur: 9, offset: 3, angle: 90, opacity: 0.35 });

function base(n, { kicker, title } = {}) {
  const s = pres.addSlide();
  s.background = { color: C.bg };
  // subtle top glow band
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: W, h: 0.06, fill: { color: C.cyanD } });
  if (kicker !== undefined) {
    s.addText(kicker.toUpperCase(), { x: 0.62, y: 0.42, w: 11, h: 0.32, fontFace: F.b,
      fontSize: 11.5, color: C.cyan, bold: true, charSpacing: 3, margin: 0 });
  }
  if (title !== undefined) {
    s.addText(title, { x: 0.6, y: 0.74, w: 12.1, h: 0.78, fontFace: F.h,
      fontSize: 29, color: C.white, bold: true, margin: 0 });
  }
  // footer
  s.addText("电竞鼠标竞品分析 · Agent 协作系统", { x: 0.62, y: 7.06, w: 8, h: 0.3,
    fontFace: F.b, fontSize: 9, color: C.dim, margin: 0 });
  s.addText(`${String(n).padStart(2, "0")} / 33`, { x: 11.9, y: 7.06, w: 0.85, h: 0.3,
    fontFace: F.mono, fontSize: 9, color: C.dim, align: "right", margin: 0 });
  return s;
}
function scoreTag(s, text, y = 6.62) {
  if (!text) return;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.62, y, w: Math.min(0.5 + text.length * 0.135, 8.5), h: 0.34,
    rectRadius: 0.06, fill: { color: C.card2 }, line: { color: C.lineHi, width: 1 } });
  s.addShape(pres.shapes.OVAL, { x: 0.78, y: y + 0.115, w: 0.11, h: 0.11, fill: { color: C.emerald } });
  s.addText("评分维度  " + text, { x: 1.0, y, w: 8.2, h: 0.34, fontFace: F.b, fontSize: 10.5,
    color: C.text, valign: "middle", margin: 0 });
}
function card(s, x, y, w, h, accent) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08,
    fill: { color: C.card }, line: { color: C.line, width: 1 }, shadow: sh() });
  if (accent) s.addShape(pres.shapes.RECTANGLE, { x, y: y + 0.14, w: 0.07, h: h - 0.28, fill: { color: accent } });
}
// grid of cards: items = [{h, b:[...], tag?}]
function cardGrid(s, items, { x = 0.62, y = 1.7, w = 12.1, gapx = 0.3, gapy = 0.3, cols = 2, ch } = {}) {
  const cw = (w - gapx * (cols - 1)) / cols;
  const rows = Math.ceil(items.length / cols);
  const rowH = ch || (5.6 - gapy * (rows - 1)) / rows;
  items.forEach((it, i) => {
    const r = Math.floor(i / cols), c = i % cols;
    const cx = x + c * (cw + gapx), cy = y + r * (rowH + gapy);
    const acc = it.accent || ACC[i % ACC.length];
    card(s, cx, cy, cw, rowH, acc);
    s.addText(it.h, { x: cx + 0.26, y: cy + 0.16, w: cw - 0.45, h: 0.42, fontFace: F.h,
      fontSize: it.hs || 15, color: C.white, bold: true, margin: 0, valign: "top" });
    if (it.b && it.b.length) {
      s.addText(it.b.map((t, k) => ({ text: t, options: { bullet: { code: "2022", indent: 12 }, breakLine: true, color: C.text, paraSpaceAfter: 3 } })),
        { x: cx + 0.26, y: cy + 0.62, w: cw - 0.45, h: rowH - 0.74, fontFace: F.b, fontSize: it.bs || 11.5, color: C.text, valign: "top", margin: 0 });
    }
    if (it.note) s.addText(it.note, { x: cx + 0.26, y: cy + rowH - 0.42, w: cw - 0.45, h: 0.32,
      fontFace: F.b, fontSize: 10, color: C.mut, italic: true, margin: 0 });
  });
}
function bullets(s, arr, { x = 0.62, y = 1.7, w = 12.1, h = 4.6, size = 14, color = C.text } = {}) {
  s.addText(arr.map(t => {
    if (typeof t === "string") return { text: t, options: { bullet: { code: "2022", indent: 16 }, breakLine: true, color, paraSpaceAfter: 6 } };
    return { text: t.t, options: { bullet: t.bullet === false ? false : { code: "2022", indent: 16 }, indentLevel: t.lvl || 0, breakLine: true, color: t.color || color, bold: t.bold, paraSpaceAfter: 6 } };
  }), { x, y, w, h, fontFace: F.b, fontSize: size, valign: "top", margin: 0 });
}
function chip(s, x, y, text, col, w) {
  const ww = w || Math.min(0.34 + text.length * 0.115, 4);
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: ww, h: 0.32, rectRadius: 0.06,
    fill: { color: C.card2 }, line: { color: col, width: 1 } });
  s.addText(text, { x, y, w: ww, h: 0.32, fontFace: F.mono, fontSize: 10, color: col, align: "center", valign: "middle", margin: 0 });
  return ww;
}

// =================== SLIDE 1 — COVER ===================
(() => {
  const s = pres.addSlide();
  s.background = { color: C.bg };
  // decorative node-graph motif on right
  const nodes = [[10.2,1.5],[11.5,2.3],[9.6,3.0],[11.2,3.9],[10.0,4.7],[12.0,1.4],[12.3,3.1]];
  nodes.forEach((p,i)=>{ for(let j=i+1;j<nodes.length;j++){ if((i+j)%2===0){ const a=nodes[i],b=nodes[j];
    const ax=a[0]+0.13,ay=a[1]+0.13,bx2=b[0]+0.13,by=b[1]+0.13;
    s.addShape(pres.shapes.LINE,{x:Math.min(ax,bx2),y:Math.min(ay,by),w:Math.abs(bx2-ax),h:Math.abs(by-ay),flipH:bx2<ax,flipV:by<ay,line:{color:C.line,width:1}});}}});
  nodes.forEach((p,i)=>s.addShape(pres.shapes.OVAL,{x:p[0],y:p[1],w:0.26,h:0.26,fill:{color:i%2?C.violet:C.cyan},line:{color:C.bg,width:1.5}}));
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 0.16, h: H, fill: { color: C.cyanD } });
  s.addText("AI 全栈项目挑战赛 · 工程答辩", { x: 0.8, y: 1.15, w: 9, h: 0.4, fontFace: F.b,
    fontSize: 14, color: C.cyan, bold: true, charSpacing: 2, margin: 0 });
  s.addText("AI 驱动的电竞鼠标\n竞品分析 Agent 协作系统", { x: 0.78, y: 1.7, w: 9.2, h: 1.9, fontFace: F.h,
    fontSize: 40, color: C.white, bold: true, lineSpacingMultiple: 1.05, margin: 0 });
  s.addText("基于 LangGraph + 专业 Schema + MCP 数据采集 + 可追溯证据链的多 Agent 竞品分析平台",
    { x: 0.8, y: 3.7, w: 9.5, h: 0.7, fontFace: F.b, fontSize: 15, color: C.text, margin: 0 });
  // key tech chips
  const techs = ["LangGraph","FastAPI","React + TS","MCP","LLM 抽取","Evidence 可追溯","Quality Gate"];
  let cx = 0.8; techs.forEach(t => { cx += chip(s, cx, 4.6, t, C.sky) + 0.18; });
  // meta line
  s.addText([
    { text: "团队：", options: { color: C.mut } }, { text: "[团队名占位]      ", options: { color: C.white, bold: true } },
    { text: "成员：", options: { color: C.mut } }, { text: "[姓名 / 姓名 / 姓名 / 姓名]      ", options: { color: C.white } },
    { text: "方向：", options: { color: C.mut } }, { text: "电竞外设 · 电竞鼠标竞品分析", options: { color: C.white } },
  ], { x: 0.8, y: 5.5, w: 11.6, h: 0.5, fontFace: F.b, fontSize: 12.5, margin: 0 });
  s.addText("电竞鼠标竞品分析 · Agent 协作系统", { x: 0.8, y: 6.9, w: 9, h: 0.3, fontFace: F.b, fontSize: 9.5, color: C.dim, margin: 0 });
  s.addNotes("开场一句话：我们做的是一套像数字调研小组一样工作的多 Agent 系统——输入两款电竞鼠标，系统自动完成产品识别、数据采集、证据结构化、事实校验、质量门控，最后产出可追溯的竞品报告。\n强调三件事：(1) LangGraph 编排的真 DAG，不是聊天式 Agent；(2) 每条结论都绑定 evidence_id，可溯源、不编造；(3) 选电竞鼠标这个垂直场景是为了用专业 Schema 展示结构化深度，同时主流程可换行业复用。");
})();

// =================== SLIDE 2 — 团队分工 ===================
(() => {
  const s = base(2, { kicker: "Team & Roles · 分工说明", title: "团队分工与协作方式" });
  cardGrid(s, [
    { h: "前端 / 产品体验", accent: C.cyan, b: ["产品输入页、Workflow DAG 可视化", "各 Agent 详情页、最终报告页", "SWOT AI 解读 + 人工修正交互"] },
    { h: "后端 / 编排 / Schema", accent: C.violet, b: ["LangGraph DAG 编排与状态流转", "专业报告 Schema、质量门控", "FastAPI 接口层"] },
    { h: "采集 / MCP / LLM 抽取", accent: C.emerald, b: ["Search / OfficialSpec / Price / ReviewIntel MCP", "官网规格、价格、评价的 LLM 结构化抽取", "本地事实库与双路线评价库"] },
    { h: "Demo / 文档 / 测试", accent: C.amber, b: ["演示脚本、README、合规声明", "faithfulness / traceability 等测试用例", "答辩材料与录屏"] },
  ], { y: 1.75, cols: 2, ch: 2.15, gapy: 0.32 });
  s.addText("分工不是“各切一块页面”，而是围绕同一条数据链路（采集 → 证据 → 分析 → 校验 → 报告）协作。",
    { x: 0.62, y: 6.32, w: 12, h: 0.34, fontFace: F.b, fontSize: 11.5, color: C.mut, italic: true, margin: 0 });
  s.addNotes("讲解：每个成员都围绕同一条数据链路负责一段，而不是简单按页面分。前端负责把 Agent 协作过程“可视化、可追溯、可干预”；后端负责 DAG 编排和结构稳定；采集组负责让数据真实可得且分级可信；Demo 组负责材料与合规。\n个人陈述时各自补充自己最难的一个技术点（如前端讲 DAG 可视化与人工修正闭环，采集组讲反爬降级与 reader 取正文）。");
})();

// =================== SLIDE 3 — 痛点 ===================
(() => {
  const s = base(3, { kicker: "Problem · 课题理解", title: "为什么竞品分析适合多 Agent" });
  // two columns: 人工 vs Agent
  card(s, 0.62, 1.75, 5.85, 4.5, C.rose);
  s.addText("传统人工竞品分析", { x: 0.9, y: 1.95, w: 5.3, h: 0.4, fontFace: F.h, fontSize: 16, color: C.white, bold: true, margin: 0 });
  bullets(s, ["信息源分散：官网、评测站、视频、社区、电商","人工对齐成本高：参数、口碑、价格、体验逐条手动","结论常无来源：“适合 FPS”“手感好”不可追溯","一致性差：不同分析人格式、口径都不同"],
    { x: 0.95, y: 2.45, w: 5.25, h: 3.6, size: 12.5, color: C.text });
  card(s, 6.85, 1.75, 5.85, 4.5, C.emerald);
  s.addText("我们的多 Agent 方案", { x: 7.13, y: 1.95, w: 5.3, h: 0.4, fontFace: F.h, fontSize: 16, color: C.white, bold: true, margin: 0 });
  bullets(s, ["专职 Agent 分工：采集 / 结构化 / 分析 / 校验 / 报告","专业 Schema：统一字段与输出结构","Evidence ID：每条结论必须引用证据","QualityAgent：缺数据就降可信度、不伪造结论"],
    { x: 7.18, y: 2.45, w: 5.25, h: 3.6, size: 12.5, color: C.text });
  scoreTag(s, "多 Agent 协作与输出可信度 35% · 业务价值与产品体验 20%");
  s.addNotes("核心论点：竞品分析天然是“多源采集 + 结构化对齐 + 校验”的流水线，正好适合拆成专职 Agent。人工做的三个痛点（来源散、对齐贵、结论无溯源），我们分别用 MCP 采集、专业 Schema、Evidence 绑定来解。\n这一页奠定全场叙事：我们不是为了用 Agent 而用 Agent，而是这个问题本身就该这么拆。");
})();

// =================== SLIDE 4 — 为什么电竞鼠标 ===================
(() => {
  const s = base(4, { kicker: "Vertical Choice · 垂直场景", title: "从通用竞品分析到专业电竞鼠标 Schema" });
  cardGrid(s, [
    { h: "参数明确、可结构化", accent: C.cyan, b: ["重量 / 尺寸 / 传感器 / DPI / 回报率","连接方式 / 续航 / 点击系统 / 驱动 / 板载内存"] },
    { h: "体验依赖外部证据", accent: C.violet, b: ["握法、手感、适合游戏、长期可靠性","不能写死，必须来自真实评价 / 测评"] },
    { h: "价格会变 + 命名混乱", accent: C.amber, b: ["实时价格须采集，不写死 JSON","GPX2 / 狗屁王 / Viper V4 Pro / DEX / 朱雀 需消歧"] },
    { h: "我们的数据策略", accent: C.emerald, b: ["稳定硬件事实 → 本地 JSON（高可信底座）","价格 / 评价 / 测评 → MCP + LLM 实时采集","结论按“场景推荐”，不强行给唯一赢家"] },
  ], { y: 1.75, cols: 2, ch: 2.1, gapy: 0.34 });
  s.addText("专业 Schema 比通用 Schema 更能展示结构化深度；换行业只需换 Schema，DAG 主流程不变。",
    { x: 0.62, y: 6.3, w: 12, h: 0.34, fontFace: F.b, fontSize: 11.5, color: C.mut, italic: true, margin: 0 });
  s.addNotes("回答“为什么不做通用竞品分析”：通用 Schema 太泛，难以展示专业字段与分级可信；电竞鼠标字段明确、且体验/价格强依赖外部实时证据，正好能展示采集+校验+溯源的完整能力。\n同时强调可拓展：专业不等于不可迁移——ResearchAgent 按 Schema 规划数据需求，换成短视频/SaaS/电商只需替换专业 Schema，Agent 协作主流程复用。");
})();

// =================== SLIDE 5 — 系统架构 ===================
(() => {
  const s = base(5, { kicker: "Architecture · 系统说明", title: "端到端系统架构" });
  const layers = [
    { t: "前端  Frontend", c: C.cyan, items: ["React / TypeScript / Vite","产品输入页 · Workflow DAG 可视化","Agent 详情页 · Evidence / Verification / Quality / Report","自研 CSS/SVG 图表（无第三方图表库）"] },
    { t: "后端  Backend · Agent DAG", c: C.violet, items: ["FastAPI 接口层","LangGraph StateGraph（7 Agent + SWOT 节点）","TypedDict State + Reducer 状态流转","专业报告 Schema（Pydantic 校验）"] },
    { t: "数据 / 工具层  Data · MCP · LLM", c: C.emerald, items: ["本地产品事实库 JSON + 双路线评价库","Search / OfficialSpec / Price / ReviewIntel MCP","DeepSeek LLM 结构化抽取 · Tavily 搜索","Evidence / Claim / Report 结构化产物"] },
  ];
  let y = 1.72;
  layers.forEach((L, i) => {
    card(s, 0.62, y, 12.1, 1.62, L.c);
    s.addShape(pres.shapes.OVAL, { x: 0.86, y: y + 0.24, w: 0.42, h: 0.42, fill: { color: C.card2 }, line: { color: L.c, width: 1.5 } });
    s.addText(["①","②","③"][i], { x: 0.86, y: y + 0.24, w: 0.42, h: 0.42, align: "center", valign: "middle", fontFace: F.h, fontSize: 16, color: L.c, bold: true, margin: 0 });
    s.addText(L.t, { x: 1.45, y: y + 0.16, w: 4.2, h: 0.4, fontFace: F.h, fontSize: 15, color: C.white, bold: true, margin: 0 });
    s.addText(L.items.map(t => ({ text: t, options: { bullet: { code: "2022", indent: 10 }, breakLine: true, color: C.text, paraSpaceAfter: 2 } })),
      { x: 5.6, y: y + 0.16, w: 6.9, h: 1.3, fontFace: F.b, fontSize: 11, valign: "middle", margin: 0 });
    if (i < 2) s.addShape(pres.shapes.LINE, { x: 6.6, y: y + 1.62, w: 0, h: 0.18, line: { color: C.lineHi, width: 2, endArrowType: "triangle" } });
    y += 1.8;
  });
  scoreTag(s, "技术深度与工程完整度 25%");
  s.addNotes("三层：前端把 Agent 过程可视化；后端用 LangGraph 编排并保证结构稳定；数据层用本地事实 + MCP/LLM 实时采集。\n要点：外部服务只用 DeepSeek（OpenAI 兼容）+ Tavily 官方搜索 API + LangSmith trace，前端图表全部自研 CSS/SVG，无第三方图表/动画库，轻量可控。");
})();

// =================== SLIDE 6 — LangGraph DAG ===================
(() => {
  const s = base(6, { kicker: "Orchestration · 核心技术", title: "LangGraph DAG 多 Agent 工作流" });
  const nodes = ["Research","Collector","Evidence","Analysis","Verification","Quality","SWOT","Report"];
  const cn = ["调研规划","采集识别","证据结构化","分析","事实校验","质量门控","AI 解读","报告生成"];
  const n = nodes.length, bx = 0.62, bw = 1.42, gap = (12.1 - bw * n) / (n - 1), y = 2.15, bh = 1.0;
  nodes.forEach((nd, i) => {
    const x = bx + i * (bw + gap);
    const acc = i === 5 ? C.amber : (i === 6 ? C.violet : C.cyan);
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: bw, h: bh, rectRadius: 0.08, fill: { color: C.card }, line: { color: acc, width: 1.4 }, shadow: sh() });
    s.addText(nd, { x, y: y + 0.16, w: bw, h: 0.32, align: "center", fontFace: F.h, fontSize: 11.5, color: C.white, bold: true, margin: 0 });
    s.addText(cn[i], { x, y: y + 0.5, w: bw, h: 0.3, align: "center", fontFace: F.b, fontSize: 9.5, color: C.mut, margin: 0 });
    if (i < n - 1) s.addShape(pres.shapes.LINE, { x: x + bw, y: y + bh / 2, w: gap, h: 0, line: { color: C.lineHi, width: 1.6, endArrowType: "triangle" } });
  });
  // feedback loop arrow Quality -> back
  const qx = bx + 5 * (bw + gap);
  const railY = y + bh + 0.55;
  s.addShape(pres.shapes.LINE, { x: qx + bw/2, y: y + bh, w: 0, h: 0.55, line: { color: C.amber, width: 1.6 } });
  s.addShape(pres.shapes.LINE, { x: bx + 0.7, y: railY, w: qx + bw/2 - (bx + 0.7), h: 0, line: { color: C.amber, width: 1.6, dashType: "dash" } });
  s.addShape(pres.shapes.LINE, { x: bx + 0.7, y: y + bh, w: 0, h: 0.55, line: { color: C.amber, width: 1.6, beginArrowType: "triangle" } });
  s.addText("Quality 反馈闭环：打回 Research / Collector / Evidence / Analysis（MAX_ITERATIONS=3）", { x: bx, y: y + bh + 0.62, w: 9, h: 0.3, fontFace: F.b, fontSize: 11, color: C.amber, margin: 0 });
  cardGrid(s, [
    { h: "真 DAG，非聊天式 Agent", accent: C.cyan, b: ["StateGraph 显式节点 + 条件边","结构化 state 在节点间流转"] },
    { h: "前进 vs 反馈两条路径", accent: C.amber, b: ["通过/部分通过 → SWOT → Report","SWOT 只在前进路径跑一次，不进重试环"] },
    { h: "不伪装成功、不默认阻塞", accent: C.emerald, b: ["重试达上限 → 生成 partial_report","明确披露缺口，而非卡死等人工"] },
  ], { y: 4.55, cols: 3, ch: 1.55, gapy: 0.2 });
  scoreTag(s, "编排框架使用合理 · DAG 可视化可追溯（35%）", 6.6);
  s.addNotes("这是全场最重要的一页。强调：(1) 用 LangGraph StateGraph 真编排，节点之间靠结构化 state 传递，不是自然语言对话；(2) quality_router 是条件边，能把不合格的工作打回上游具体 Agent 重做（research/collector/evidence/analysis），MAX_ITERATIONS=3；(3) SWOT 我们做成了 DAG 上的一等节点，挂在 Quality→Report 的前进路径，只跑一次、且在校验之后，所以数据最干净，重试循环不会重复触发它。\nQ&A 防御：‘是不是伪闭环？’——现场可演示故意制造证据不足触发打回，重做后 metrics 改善。‘为什么 8 个框？’——7 个核心 Agent + SWOT AI 解读节点。");
})();

// =================== SLIDE 7 — Agent 职责边界 ===================
(() => {
  const s = base(7, { kicker: "Separation of Concerns · 核心技术", title: "每个 Agent 只做一件事" });
  cardGrid(s, [
    { h: "ResearchAgent · 调研规划", accent: C.cyan, b: ["按 Schema 规划需要哪些数据","不爬数据、不下结论"] },
    { h: "CollectorAgent · 采集识别", accent: C.cyan, b: ["实体消歧、读本地事实","调度 4 个 MCP 工具"] },
    { h: "EvidenceAgent · 证据结构化", accent: C.violet, b: ["统一 evidence_id / source / credibility","只结构化，不做推荐"] },
    { h: "AnalysisAgent · 分析", accent: C.violet, b: ["只分析有证据支撑的差异","硬件 / 价格 / 体验对比 + SWOT"] },
    { h: "VerificationAgent · 校验", accent: C.emerald, b: ["检查 claim 是否被 evidence 支撑","数值/词面 grounding，拦截幻觉"] },
    { h: "QualityAgent · 质量门控", accent: C.amber, b: ["按缺口/弱支撑/风险算可信度","通过 / 有限通过 / 打回 / 降级"] },
  ], { y: 1.72, cols: 3, ch: 1.62, gapy: 0.28 });
  s.addText("ReportAgent · 报告生成：只汇总“已验证”的结果，输出场景推荐 + 可追溯引用 + 风险披露。",
    { x: 0.62, y: 6.18, w: 12, h: 0.34, fontFace: F.b, fontSize: 12, color: C.text, margin: 0 });
  scoreTag(s, "角色划分清晰 · 职责边界明确无重叠（35%）");
  s.addNotes("逐个点出“边界”：Research 不爬数据；Collector 不下结论；Evidence 不推荐；Analysis 只动有证据的；Verification 只判真假；Quality 只算可信度和路由；Report 只汇总已验证。\n这种单一职责让反馈闭环可定位——Quality 打回时能精确指到是哪个上游 Agent 的问题。");
})();

// =================== SLIDE 8 — 结构化消息传递 ===================
(() => {
  const s = base(8, { kicker: "Structured Messaging · 技术说明", title: "Agent 间是 Schema 状态流转，不是自然语言聊天" });
  // left: state fields list ; right: producer mapping
  card(s, 0.62, 1.72, 6.0, 4.7, C.cyan);
  s.addText("统一 State（TypedDict + Reducer）", { x: 0.88, y: 1.9, w: 5.5, h: 0.4, fontFace: F.h, fontSize: 14, color: C.white, bold: true, margin: 0 });
  const fields = ["selected_products / resolved_products","product_facts / official_spec_records","review_intel_records / price_records","evidence_list  ·  claims","faithfulness_report  ·  quality_result","final_report","reducers: merge_claims / merge_trace_log / merge_dict"];
  s.addText(fields.map(t => ({ text: t, options: { breakLine: true, color: C.text, paraSpaceAfter: 6 } })),
    { x: 0.88, y: 2.42, w: 5.5, h: 3.9, fontFace: F.mono, fontSize: 11.5, valign: "top", margin: 0 });
  card(s, 6.9, 1.72, 5.82, 4.7, C.violet);
  s.addText("谁产出什么（输入/输出固定字段）", { x: 7.16, y: 1.9, w: 5.4, h: 0.4, fontFace: F.h, fontSize: 14, color: C.white, bold: true, margin: 0 });
  const map = [["Collector","official_spec_records / price_records"],["ReviewIntel","review_intel_records"],["Evidence","evidence_list"],["Analysis","claims / SWOT"],["Verification","unsupported_claim_ids"],["Quality","quality_result"],["Report","final_report"]];
  let yy = 2.5;
  map.forEach(([a,b],i)=>{ s.addText(a, { x: 7.16, y: yy, w: 1.9, h: 0.34, fontFace: F.h, fontSize: 11.5, color: ACC[i%ACC.length], bold: true, margin: 0 });
    s.addShape(pres.shapes.LINE,{x:9.0,y:yy+0.17,w:0.24,h:0,line:{color:C.lineHi,width:1.4,endArrowType:"triangle"}});
    s.addText(b, { x: 9.32, y: yy, w: 3.3, h: 0.34, fontFace: F.mono, fontSize: 10.5, color: C.text, margin: 0 }); yy += 0.55; });
  scoreTag(s, "结构化消息传递（function calling / 标准 Schema）35%");
  s.addNotes("强调评分点：Agent 之间不是把自然语言丢来丢去，而是读写同一个 TypedDict State 的固定字段，并用 reducer 控制合并（merge_claims 去重保留首条、merge_trace_log 去重重排步号、merge_dict 合并）。\nLLM 的输出也被强制成结构化 JSON 再并入 state。这就是评委要的‘结构化消息传递，非纯自然语言对话’。");
})();

// =================== SLIDE 9 — 专业 Schema ===================
(() => {
  const s = base(9, { kicker: "Domain Schema · 技术说明", title: "电竞鼠标专业竞品 Schema" });
  cardGrid(s, [
    { h: "产品识别 ProductIdentity", accent: C.cyan, b: ["官方型号 / 别名 / 变体 / 实体消歧","field_confidence 字段级可信度"] },
    { h: "硬件事实 HardwareSpec", accent: C.cyan, b: ["重量 / 传感器 / DPI / 回报率 / 连接","续航 / 点击系统 / 驱动 / 板载内存"] },
    { h: "评价测评 ReviewIntel", accent: C.violet, b: ["握感 / 手型 / 适合游戏","驱动口碑 / 长期可靠 / 社区口碑"] },
    { h: "实时价格 Pricing", accent: C.amber, b: ["官方价 / 电商价 / 低可信来源","official_price_blocked 反爬标记"] },
    { h: "Evidence & Claim", accent: C.emerald, b: ["evidence_id / source_url / credibility","claim_id / dimension / evidence_ids"] },
    { h: "Final Report", accent: C.rose, b: ["场景推荐 / 风险披露","质量评分 / 可追溯引用"] },
  ], { y: 1.72, cols: 3, ch: 1.62, gapy: 0.28 });
  s.addText("已清理旧的通用 schema，统一为 GamingMouseFinalReportSchema（Pydantic，extra=allow 兼容增量字段）。",
    { x: 0.62, y: 6.18, w: 12, h: 0.34, fontFace: F.b, fontSize: 11.5, color: C.mut, italic: true, margin: 0 });
  scoreTag(s, "输出严格符合预定义竞品知识 Schema（35%）");
  s.addNotes("说明我们做了 schema 收敛：删掉旧的泛化 report，统一成 GamingMouseFinalReportSchema，包含功能树、定价模型、用户画像、证据链等模块，ReportAgent 输出过 Pydantic 校验（run_node 用 ReportAgentOutput 校验 final_report）。extra=allow 是为了平滑加新字段（如 scenario_recommendations、analysis_ai_interpretation）。");
})();

// =================== SLIDE 10 — 实体消歧 ===================
(() => {
  const s = base(10, { kicker: "Entity Resolution · 功能说明", title: "解决电竞鼠标命名混乱：实体消歧" });
  bullets(s, [
    { t: "问题：玩家简称 ≠ 官方型号，且变体多", bold: true, color: C.white },
    "GPX2 / 狗屁王2 / DEX / 朱雀 / Viper V4 Pro 容易混淆，还有 DEX、SUPERSTRIKE 等变体",
  ], { x: 0.62, y: 1.7, w: 12, h: 1.1, size: 13.5 });
  // flow
  const steps = [["输入","GPX2 / Viper V4 Pro"],["本地命中?","aliases / community_aliases"],["命中 → 稳定事实","本地 JSON 高可信底座"],["未命中 → SearchMCP","只找官网候选，不写字段"],["OfficialSpecMCP","从官网抽取规格"]];
  const n = steps.length, x0 = 0.62, bw = 2.2, gap = (12.1 - bw*n)/(n-1), y = 3.0, bh = 1.3;
  steps.forEach((st,i)=>{ const x=x0+i*(bw+gap); const acc=ACC[i%ACC.length];
    card(s,x,y,bw,bh,acc);
    s.addText(st[0],{x:x+0.14,y:y+0.16,w:bw-0.28,h:0.4,fontFace:F.h,fontSize:12.5,color:C.white,bold:true,align:"center",margin:0});
    s.addText(st[1],{x:x+0.14,y:y+0.62,w:bw-0.28,h:0.6,fontFace:F.b,fontSize:10,color:C.mut,align:"center",valign:"top",margin:0});
    if(i<n-1) s.addShape(pres.shapes.LINE,{x:x+bw,y:y+bh/2,w:gap,h:0,line:{color:C.lineHi,width:1.6,endArrowType:"triangle"}});
  });
  s.addText("关键边界：SearchMCP 只负责“找候选”，硬件字段一律由 OfficialSpecMCP 从官网抽取——搜索结果不等于实体解析。",
    { x: 0.62, y: 4.7, w: 12, h: 0.4, fontFace: F.b, fontSize: 12, color: C.text, margin: 0 });
  scoreTag(s, "数据采集与知识结构化（35% / 25%）");
  s.addNotes("讲清两层：命中本地库就直接用稳定事实（高可信、即时）；没命中才走搜索找官网候选，再由 OfficialSpec 抽取规格。\n反复强调‘SearchMCP 只找候选、不写硬件字段’——这是我们刻意的职责切分，避免把搜索摘要当成事实，是防幻觉的第一道闸。");
})();

// =================== SLIDE 11 — 本地 vs MCP ===================
(() => {
  const s = base(11, { kicker: "Data Strategy · 功能说明", title: "哪些写进 JSON，哪些必须实时采集" });
  card(s, 0.62, 1.75, 5.85, 4.3, C.cyan);
  s.addText("写进本地 JSON（稳定事实底座）", { x: 0.9, y: 1.95, w: 5.3, h: 0.4, fontFace: F.h, fontSize: 15, color: C.white, bold: true, margin: 0 });
  bullets(s, ["官方型号 / 别名 / 官网 URL","传感器 / DPI / 重量 / 连接方式","点击系统 / 续航等相对稳定字段","字段级可信度 field_confidence"], { x: 0.95, y: 2.5, w: 5.25, h: 3.3, size: 13 });
  card(s, 6.85, 1.75, 5.85, 4.3, C.amber);
  s.addText("必须实时采集（不写死）", { x: 7.13, y: 1.95, w: 5.3, h: 0.4, fontFace: F.h, fontSize: 15, color: C.white, bold: true, margin: 0 });
  bullets(s, ["实时价格（官方 / 电商，会变）","用户评价 / 博主测评（会变）","握法 / 手感 / 适合游戏","驱动口碑 / 长期可靠性"], { x: 7.18, y: 2.5, w: 5.25, h: 3.3, size: 13 });
  s.addText("原因：价格与口碑随时间变化、体验类结论必须来自真实外部证据——我们没有把结果写死。",
    { x: 0.62, y: 6.25, w: 12, h: 0.34, fontFace: F.b, fontSize: 11.5, color: C.mut, italic: true, margin: 0 });
  s.addNotes("这一页回应一个常见质疑：‘是不是把答案写死在 JSON 里？’。我们明确区分：只有相对稳定的硬件事实进本地库当高可信底座；价格/评价/体验全部走实时采集，抓不到就标缺失。\n这既是工程合理性，也是可信度设计。");
})();

// =================== SLIDE 12 — MCP 层 ===================
(() => {
  const s = base(12, { kicker: "MCP Tool Layer · 技术说明", title: "MCP 工具层如何工作" });
  cardGrid(s, [
    { h: "SearchMCP", accent: C.cyan, b: ["Tavily 官方搜索 API","未命中本地库时找官网/评测候选"] },
    { h: "OfficialSpecMCP", accent: C.violet, b: ["抓官网页面 → LLM 抽取硬件规格","多来源字段级合并补齐"] },
    { h: "PriceMCP", accent: C.amber, b: ["官方价 / 电商价 / fallback","反爬拦截标记 + 离群价过滤"] },
    { h: "ReviewIntelMCP", accent: C.emerald, b: ["评价 / 测评 / 口碑信号抽取","reader 取正文绕反爬 + 跨源印证"] },
  ], { y: 1.72, cols: 2, ch: 1.7, gapy: 0.3 });
  bullets(s, [
    { t: "统一工作原则", bold: true, color: C.white, bullet: false },
    "能从官网拿到的用高可信；电商/视频/搜索摘要作为低可信 fallback",
    "被反爬时明确标记 blocked，绝不伪造数据",
    "所有采集结果统一转成 evidence，进入同一条校验链路",
  ], { x: 0.62, y: 5.25, w: 12, h: 1.3, size: 12.5 });
  scoreTag(s, "端到端链路完整 · 信息采集合规（25% / 10%）", 6.62);
  s.addNotes("四个 MCP 各司其职。要点：(1) 分级可信，官网>电商>搜索摘要；(2) 反爬不绕过、只标记降级；(3) 所有来源最终都变成统一的 evidence，下游 Verification/Quality 一视同仁。\nReviewIntel 是我们这次重点优化的：接了 reader 代理取正文（绕反爬、读视频字幕）、Reddit 接口、跨源交叉印证，实测 Viper 从 0 → 7 个维度全覆盖。");
})();

// =================== SLIDE 13 — LLM 作用 ===================
(() => {
  const s = base(13, { kicker: "LLM Boundary · 技术说明", title: "LLM 只做结构化抽取与总结，不替代流程" });
  card(s, 0.62, 1.75, 5.85, 4.3, C.emerald);
  s.addText("规则驱动（不用 LLM）", { x: 0.9, y: 1.95, w: 5.3, h: 0.4, fontFace: F.h, fontSize: 15, color: C.white, bold: true, margin: 0 });
  bullets(s, ["本地别名匹配 / JSON 事实读取","DAG 状态流转","Evidence ID 校验、数值 grounding","Quality 规则门控与扣分"], { x: 0.95, y: 2.5, w: 5.25, h: 3.3, size: 13 });
  card(s, 6.85, 1.75, 5.85, 4.3, C.violet);
  s.addText("LLM 驱动（受约束）", { x: 7.13, y: 1.95, w: 5.3, h: 0.4, fontFace: F.h, fontSize: 15, color: C.white, bold: true, margin: 0 });
  bullets(s, ["官网规格 / 价格页字段抽取","用户评价 / 博主测评摘要","SWOT AI 解读","人工反馈语义理解"], { x: 7.18, y: 2.5, w: 5.25, h: 3.3, size: 13 });
  s.addText("设计原则：LLM 只能基于已有 evidence / 网页内容总结，不能凭空补字段；所有输出必须结构化并带来源。",
    { x: 0.62, y: 6.22, w: 12, h: 0.34, fontFace: F.b, fontSize: 11.5, color: C.amber, italic: true, margin: 0 });
  scoreTag(s, "幻觉抑制 · 技术深度（25%）", 6.62);
  s.addNotes("划清 LLM 的能力边界：流程编排、ID 校验、评分这些确定性工作用规则；只有非结构化文本 → 结构化这件事交给 LLM。并且强约束：必须基于给定证据、必须返回 JSON、必须带 source_ids。\n这是我们抑制幻觉的核心理念——LLM 是‘抽取器/总结器’，不是‘事实来源’。");
})();

// =================== SLIDE 14 — Evidence / Claim 可追溯 ===================
(() => {
  const s = base(14, { kicker: "Traceability · 核心技术", title: "每条结论都能追溯到证据" });
  card(s, 0.62, 1.72, 3.9, 4.5, C.cyan);
  s.addText("Evidence", { x: 0.86, y: 1.9, w: 3.4, h: 0.4, fontFace: F.h, fontSize: 15, color: C.white, bold: true, margin: 0 });
  s.addText(["evidence_id","product / dimension","source_type","source_url","credibility","raw_content / summary"].map(t=>({text:t,options:{bullet:{code:"2022",indent:10},breakLine:true,color:C.text,paraSpaceAfter:7}})),
    { x: 0.9, y: 2.45, w: 3.45, h: 3.6, fontFace: F.mono, fontSize: 12, valign: "top", margin: 0 });
  // arrow
  s.addShape(pres.shapes.LINE, { x: 4.6, y: 3.9, w: 0.55, h: 0, line: { color: C.emerald, width: 2, beginArrowType: "triangle", endArrowType: "triangle" } });
  s.addText("引用", { x: 4.55, y: 3.55, w: 0.7, h: 0.3, align: "center", fontFace: F.b, fontSize: 10, color: C.emerald, margin: 0 });
  card(s, 5.25, 1.72, 3.9, 4.5, C.violet);
  s.addText("Claim", { x: 5.49, y: 1.9, w: 3.4, h: 0.4, fontFace: F.h, fontSize: 15, color: C.white, bold: true, margin: 0 });
  s.addText(["claim_id","content","dimension","evidence_ids[]","confidence","generated_by"].map(t=>({text:t,options:{bullet:{code:"2022",indent:10},breakLine:true,color:C.text,paraSpaceAfter:7}})),
    { x: 5.53, y: 2.45, w: 3.45, h: 3.6, fontFace: F.mono, fontSize: 12, valign: "top", margin: 0 });
  card(s, 9.25, 1.72, 3.47, 4.5, C.amber);
  s.addText("规则", { x: 9.49, y: 1.9, w: 3.0, h: 0.4, fontFace: F.h, fontSize: 15, color: C.white, bold: true, margin: 0 });
  bullets(s, ["无 evidence_id 的结论\n不进入正式推荐","低可信来源可展示\n但必须标注","被反爬 / 未采集 / 缺字段\n一律披露"], { x: 9.5, y: 2.5, w: 3.0, h: 3.5, size: 12 });
  scoreTag(s, "信息溯源完整 · 一键跳转 / 溯源查看（35%）");
  s.addNotes("可追溯是我们对‘输出可信度’的核心兑现。Claim 通过 evidence_ids 指向 Evidence，前端 Evidence 表里 source_url 可点击跳转原始来源。\n三条铁律：没证据不进推荐、低可信必标注、缺数据必披露。这页配合 Demo 里点开 Evidence 表演示。");
})();

// =================== SLIDE 15 — Verification 防幻觉 ===================
(() => {
  const s = base(15, { kicker: "Faithfulness · 核心技术", title: "VerificationAgent：事实校验与幻觉抑制" });
  cardGrid(s, [
    { h: "数值 grounding（硬失败）", accent: C.rose, b: ["claim 里的关键数字必须能在所引证据中找到","找不到 → not_supported，硬拦截"] },
    { h: "词面 grounding（弱支撑）", accent: C.amber, b: ["覆盖率低 → weak，不硬拦但降可信","避免误杀合理的中文转述"] },
    { h: "价格类特判", accent: C.cyan, b: ["按所引证据可信度判定强弱","反爬/低可信来源 → 弱支撑"] },
    { h: "人工反馈特判（新增）", accent: C.violet, b: ["仅人工证据 → 待验证，不能自证","需非人工证据同向才升为支撑"] },
  ], { y: 1.72, cols: 2, ch: 1.65, gapy: 0.28 });
  bullets(s, [
    { t: "三档结果", bold: true, color: C.white, bullet: false },
    { t: "支撑 → 进入报告   ·   弱支撑 → 进入但降可信   ·   不支撑 → 拦截，不进最终推荐", color: C.text },
  ], { x: 0.62, y: 5.3, w: 12, h: 1.0, size: 13 });
  scoreTag(s, "输出可信度 · 幻觉抑制（引用强制 / 自一致性）35% / 25%", 6.62);
  s.addNotes("两层 grounding：数字对不上是硬失败（直接踢出报告并触发质检），词面覆盖低只是弱支撑（保留但降可信，避免误杀转述）。还有两个特判：价格类按来源可信度判，人工反馈不能‘自己引用自己’当事实。\nQ&A：‘怎么防幻觉？’——LLM 只抽取、结论必绑 evidence_id、数值必须可在证据中验证、Verification 拦截、Quality 降级，四道闸。");
})();

// =================== SLIDE 16 — Quality 门控 ===================
(() => {
  const s = base(16, { kicker: "Quality Gate · 核心技术", title: "QualityAgent：质量门控与反馈闭环" });
  cardGrid(s, [
    { h: "approved", accent: C.emerald, b: ["证据完整，可生成报告"] , hs:14},
    { h: "approved_with_limitations", accent: C.amber, b: ["可生成，但有弱支撑/缺口"], hs:13 },
    { h: "partial_report", accent: C.rose, b: ["重试达上限仍不足 → 有限报告"], hs:14 },
  ], { y: 1.7, cols: 3, ch: 1.25, gapy: 0.2 });
  // scoring formula
  card(s, 0.62, 3.25, 6.0, 3.0, C.cyan);
  s.addText("评分是“报告可信度”，非产品评分", { x: 0.88, y: 3.42, w: 5.5, h: 0.4, fontFace: F.h, fontSize: 14, color: C.white, bold: true, margin: 0 });
  s.addText("score = max(0, 90 − 扣分 − 待补惩罚)", { x: 0.88, y: 3.92, w: 5.5, h: 0.4, fontFace: F.mono, fontSize: 13, color: C.cyan, margin: 0 });
  bullets(s, ["失败检查项 ×10","高风险项 min(20, n×4)","缺失维度 min(12, n×4)","pending 数据 / 弱价格 / 弱测评惩罚"], { x: 0.92, y: 4.4, w: 5.4, h: 1.7, size: 11.5 });
  card(s, 6.85, 3.25, 5.87, 3.0, C.amber);
  s.addText("反馈机制", { x: 7.11, y: 3.42, w: 5.4, h: 0.4, fontFace: F.h, fontSize: 14, color: C.white, bold: true, margin: 0 });
  bullets(s, ["可打回 Collector / Evidence / Analysis / Research","不默认人工阻塞，达上限自动降级","人工反馈作为 evidence 进入校验链路","人工输入不计入维度覆盖，刷不了分"], { x: 7.15, y: 3.92, w: 5.4, h: 2.2, size: 12 });
  s.addNotes("两件事：(1) 分数是数据驱动的报告可信度，不是写死——给出公式：90 减去失败检查、风险、缺维度、pending 惩罚；现场可演示不同输入分数不同。(2) 闭环是真的：能打回具体上游 Agent；达上限不卡死而是 partial_report 并披露。\n防御点：我们专门修了‘人工输入刷分’——人工证据被排除在维度覆盖统计外，且只算弱支撑，所以现场随便输入一句话不会让分数虚高。");
})();

// =================== SLIDE 17 — SWOT + 人工修正 ===================
(() => {
  const s = base(17, { kicker: "Human-in-the-loop · 功能说明", title: "SWOT AI 解读 + 人工修正闭环" });
  // flow
  const steps = ["人工输入现场判断","转为 HF evidence + HCL claim","重跑 Verification → Quality → SWOT → Report","报告 / 场景推荐更新"];
  const n=steps.length, x0=0.62, bw=2.85, gap=(12.1-bw*n)/(n-1), y=1.85, bh=1.15;
  steps.forEach((st,i)=>{const x=x0+i*(bw+gap);card(s,x,y,bw,bh,ACC[i%ACC.length]);
    s.addShape(pres.shapes.OVAL,{x:x+0.16,y:y+0.16,w:0.34,h:0.34,fill:{color:C.card2},line:{color:ACC[i%ACC.length],width:1.5}});
    s.addText(String(i+1),{x:x+0.16,y:y+0.16,w:0.34,h:0.34,align:"center",valign:"middle",fontFace:F.h,fontSize:13,color:ACC[i%ACC.length],bold:true,margin:0});
    s.addText(st,{x:x+0.16,y:y+0.56,w:bw-0.32,h:0.55,fontFace:F.b,fontSize:11,color:C.text,valign:"top",margin:0});
    if(i<n-1)s.addShape(pres.shapes.LINE,{x:x+bw,y:y+bh/2,w:gap,h:0,line:{color:C.lineHi,width:1.6,endArrowType:"triangle"}});});
  cardGrid(s, [
    { h: "人工输入不直接覆盖报告", accent: C.cyan, b: ["先变成 evidence/claim 走校验","与现有结论一致才升为支撑"] },
    { h: "SWOT 进 DAG，证据被校验", accent: C.violet, b: ["AI 自报的 evidence_id 与真实证据取交集","虚构编号被剔除、未绑定标“待绑定”"] },
    { h: "支持现场互动", accent: C.emerald, b: ["专家可补“Viper 更适合 FPS”","展示人机协作 + 决策回放"] },
  ], { y: 3.4, cols: 3, ch: 1.55, gapy: 0.2 });
  scoreTag(s, "产品体验 · 反馈闭环 · Agent 决策回放（20% / 35%）", 6.6);
  s.addNotes("这是产品体验 + 反馈闭环的亮点，也是现场最好互动的环节。逻辑：人工输入不直接改报告，而是转成 HF evidence + HCL claim，重新跑校验→质检→SWOT→报告。\n两个诚实性设计（我们专门加固过）：(1) 人工输入默认低可信、待验证，必须有非人工证据同向才算支撑；(2) SWOT 引用的证据会和真实 evidence 取交集，虚构的 EV 编号被剔除、未绑定证据的 point 标‘待绑定’。所以现场输入不会污染报告、也不会刷分。");
})();

// =================== SLIDE 18 — 前端体验 ===================
(() => {
  const s = base(18, { kicker: "Frontend UX · 产品体验", title: "前端如何展示 Agent 协作过程" });
  cardGrid(s, [
    { h: "① 产品输入页", accent: C.cyan, b: ["输入两款竞品","不提前展示分析结果"] },
    { h: "② Workflow 页", accent: C.violet, b: ["LangGraph DAG 可视化","Agent 卡片可点击 + MCP 状态"] },
    { h: "③ Agent 详情页", accent: C.emerald, b: ["输入 / 输出 / 证据 / 风险","每个 Agent 的任务贡献"] },
    { h: "④ 最终报告页", accent: C.amber, b: ["场景推荐 + Evidence 引用","质量状态 + 人工修正记录"] },
  ], { y: 1.72, cols: 2, ch: 1.75, gapy: 0.3 });
  bullets(s, [
    { t: "设计取向", bold: true, color: C.white, bullet: false },
    "工具型布局（参考 eloshapes）· 深色科技风 · 高信息密度 · 自研图表非营销 landing",
  ], { x: 0.62, y: 5.35, w: 12, h: 1.0, size: 12.5 });
  scoreTag(s, "交互设计流畅 · Agent 决策回放易用（20%）", 6.62);
  s.addNotes("四个核心页对应‘报告查看、溯源跳转、人工介入、决策回放’四个评分动作。产品输入页刻意不预渲染结果，强调‘分析是 Agent 跑出来的’。\n风格上明确不做营销路演风，而是工程工具风：深色、高密度、可点开每个 Agent 看它的输入输出和证据。");
})();

// =================== SLIDE 19 — 后端工程 ===================
(() => {
  const s = base(19, { kicker: "Backend Engineering · 技术说明", title: "FastAPI + LangGraph + Service 分层" });
  card(s, 0.62, 1.72, 6.4, 4.55, C.violet);
  s.addText("目录结构", { x: 0.88, y: 1.9, w: 5.8, h: 0.4, fontFace: F.h, fontSize: 14, color: C.white, bold: true, margin: 0 });
  s.addText([
    "api/routes.py        分析 / 报告 / trace / swot / feedback",
    "orchestration/       workflow.py  (LangGraph DAG) · state.py",
    "agents/              research · collector · evidence · analysis",
    "                     verification · quality · report · analysis_ai",
    "services/            catalog · 4×MCP · scoring · faithfulness",
    "                     context_manager · metrics · review_intel",
    "schemas/             gaming_mouse 专业报告 Schema",
  ].map(t=>({text:t,options:{breakLine:true,color:C.text,paraSpaceAfter:5}})),
    { x: 0.88, y: 2.4, w: 6.0, h: 3.7, fontFace: F.mono, fontSize: 10.5, valign: "top", margin: 0 });
  card(s, 7.25, 1.72, 5.47, 4.55, C.cyan);
  s.addText("设计原则", { x: 7.51, y: 1.9, w: 5.0, h: 0.4, fontFace: F.h, fontSize: 14, color: C.white, bold: true, margin: 0 });
  bullets(s, ["Agent 只负责流程节点","Service 负责可复用工具能力","Schema 保证结构稳定","run_node 统一错误兜底 + trace","trace_log 记录每个 Agent 输入输出摘要"], { x: 7.55, y: 2.45, w: 5.0, h: 3.5, size: 13 });
  scoreTag(s, "代码质量与模块化（10%）");
  s.addNotes("强调分层：Agent=流程节点、Service=可复用能力、Schema=结构契约。所有 Agent 都过 run_node 包一层——单个 Agent 抛异常不会炸整个图，而是记 trace+error_log 并降级继续。\n这点很重要：体现了工程完整度里的‘错误恢复/降级’。");
})();

// =================== SLIDE 20 — 上下文管理 ===================
(() => {
  const s = base(20, { kicker: "Context Management · 技术说明", title: "上下文管理与长文本处理" });
  // flow
  const steps=["Evidence Pool\n(全部证据)","Context Selector\nselect_evidence_context","裁剪后子集\nmax_items=18 / per_dim=4","LLM\n结构化 JSON 输出"];
  const n=steps.length,x0=0.62,bw=2.85,gap=(12.1-bw*n)/(n-1),y=1.95,bh=1.4;
  steps.forEach((st,i)=>{const x=x0+i*(bw+gap);card(s,x,y,bw,bh,ACC[i%ACC.length]);
    s.addText(st,{x:x+0.14,y:y+0.2,w:bw-0.28,h:1.0,align:"center",valign:"middle",fontFace:F.b,fontSize:11.5,color:C.text,margin:0});
    if(i<n-1)s.addShape(pres.shapes.LINE,{x:x+bw,y:y+bh/2,w:gap,h:0,line:{color:C.lineHi,width:1.6,endArrowType:"triangle"}});});
  cardGrid(s, [
    { h: "问题", accent: C.rose, b: ["爬虫/测评正文很长","LLM 输入不能无限增长"] },
    { h: "策略", accent: C.cyan, b: ["按 Agent 任务选相关 evidence","限 max_items / per_dimension / chars","长转写按关键词密度抽相关段"] },
    { h: "效果", accent: C.emerald, b: ["降 token、减干扰","防超时、提稳定性"] },
  ], { y: 3.75, cols: 3, ch: 1.55, gapy: 0.2 });
  scoreTag(s, "上下文管理 · 技术深度（25%）", 6.6);
  s.addNotes("context_manager.select_evidence_context 按当前 Agent 任务挑相关证据，限制条数/每维度条数/每条字符数。ReviewIntel 里还有长文本的关键词密度抽取，既防 LLM 超时也提升信号密度。\n这对应评分里的‘超长上下文分片/裁剪’策略。");
})();

// =================== SLIDE 21 — 价格 / 反爬 ===================
(() => {
  const s = base(21, { kicker: "PriceMCP · 功能说明", title: "实时价格采集与反爬合规降级" });
  cardGrid(s, [
    { h: "采集优先级", accent: C.cyan, b: ["优先官方价（高可信）","官方被拦 → official_price_blocked","电商/公开价作为低可信 fallback"] },
    { h: "可信度规则", accent: C.amber, b: ["官方价 vs 官方价 → 高可信","电商价 vs 电商价 → 中/低","YouTube/非电商 不作高可信价"] },
    { h: "数据质量", accent: C.violet, b: ["离群价 / 分期 / 配件价过滤","锚定中位价，抗污染"] },
    { h: "结论约束", accent: C.emerald, b: ["一方缺失 → 不输出强性价比结论","价格来源统一进入 evidence"] },
  ], { y: 1.72, cols: 2, ch: 1.72, gapy: 0.28 });
  s.addText("我们不是绕过反爬，而是合规降级 + 风险披露：拿不到就标“被反爬拦截”，并在报告可信度里扣分。",
    { x: 0.62, y: 5.42, w: 12, h: 0.34, fontFace: F.b, fontSize: 12, color: C.amber, italic: true, margin: 0 });
  scoreTag(s, "信息采集合规 · 端到端链路（10% / 25%）", 6.6);
  s.addNotes("价格是最容易出脏数据的地方。我们做了离群过滤（分期 $22/月、配件价会污染中位数）+ 锚定中位价。可信度严格分级，缺一方就不下性价比结论。\n合规叙事：反爬不绕过、只降级标记，这点对应 10% 合规维度，也是诚实性卖点。");
})();

// =================== SLIDE 22 — ReviewIntel 双路线 ===================
(() => {
  const s = base(22, { kicker: "ReviewIntelMCP · 功能说明", title: "评价 / 测评采集：双路线 + 体验信号" });
  card(s, 0.62, 1.72, 6.0, 2.45, C.emerald);
  s.addText("双路线（demo 对比展示）", { x: 0.88, y: 1.88, w: 5.5, h: 0.4, fontFace: F.h, fontSize: 14, color: C.white, bold: true, margin: 0 });
  bullets(s, [{t:"本地评价库：GPX2 命中即时返回、满维度", color:C.text},{t:"实时爬取：Viper V4 Pro 走 search→reader→LLM", color:C.text},{t:"reader 取正文绕反爬/读视频字幕 + 跨源印证", color:C.text}], { x: 0.92, y: 2.4, w: 5.5, h: 1.7, size: 12 });
  card(s, 6.85, 1.72, 5.87, 2.45, C.violet);
  s.addText("六类体验信号", { x: 7.11, y: 1.88, w: 5.4, h: 0.4, fontFace: F.h, fontSize: 14, color: C.white, bold: true, margin: 0 });
  s.addText(["grip_feel","hand_size_fit","game_type_fit"].map(t=>({text:t,options:{bullet:{code:"2022",indent:10},breakLine:true,color:C.sky,paraSpaceAfter:8}})),
    { x: 7.13, y: 2.45, w: 2.55, h: 1.6, fontFace: F.mono, fontSize: 11.5, valign: "top", margin: 0 });
  s.addText(["driver_reputation","long_term_reliability","community_sentiment"].map(t=>({text:t,options:{bullet:{code:"2022",indent:10},breakLine:true,color:C.sky,paraSpaceAfter:8}})),
    { x: 9.95, y: 2.45, w: 2.7, h: 1.6, fontFace: F.mono, fontSize: 11.5, valign: "top", margin: 0 });
  cardGrid(s, [
    { h: "多来源印证", accent: C.emerald, b: ["≥2 个独立来源 → high"] , hs:14},
    { h: "单一来源", accent: C.amber, b: ["medium"], hs:14 },
    { h: "搜索摘要 / 社区片段", accent: C.rose, b: ["low（仅供参考）"], hs:13 },
  ], { y: 4.4, cols: 3, ch: 1.2, gapy: 0.2 });
  scoreTag(s, "数据覆盖度 · 结构化知识抽取（25%）", 6.62);
  s.addNotes("双路线是这次的亮点：GPX2 走人工整理入库的本地评价库（即时、满维度、可控），Viper 走真实爬虫（search→reader 取正文→LLM 抽取）。reader 代理能绕反爬、读视频字幕，配合跨源交叉印证，实测 Viper 7 维度全 high。\n信号分级：≥2 独立来源才升 high。这页 demo 时正好展示‘两条路线、同一种结构化产物’。");
})();

// =================== SLIDE 23 — 最终报告 ===================
(() => {
  const s = base(23, { kicker: "Final Report · 结果说明", title: "不强行给唯一赢家，而是按场景推荐" });
  const scenes=[["追求极限 FPS",C.cyan],["追求轻量化",C.violet],["无线续航",C.emerald],["驱动与可调性",C.amber],["预算敏感（官方/电商）",C.rose],["手感 / 握法",C.sky],["长期可靠性",C.cyan]];
  const cols=4, x0=0.62, gap=0.28, cw=(12.1-gap*(cols-1))/cols, y0=1.8, ch=0.95;
  scenes.forEach((sc,i)=>{const r=Math.floor(i/cols),c=i%cols;const x=x0+c*(cw+gap),y=y0+r*(ch+0.3);
    card(s,x,y,cw,ch,sc[1]);
    s.addText(sc[0],{x:x+0.22,y,w:cw-0.4,h:ch,fontFace:F.h,fontSize:13,color:C.white,bold:true,valign:"middle",margin:0});});
  bullets(s, [
    { t: "为什么不只给“谁赢”：电竞鼠标选择高度依赖场景，FPS/续航/轻量/驱动/预算/手感答案可能各不相同", color:C.text },
    { t: "原则：有证据才推荐 · 缺证据就标“数据不足” · 人工反馈可进入修正链路", color:C.amber },
  ], { x: 0.62, y: 4.4, w: 12, h: 1.6, size: 13 });
  scoreTag(s, "业务价值 · 产品体验（20%）", 6.6);
  s.addNotes("产品形态上的关键判断：单一赢家是反专业的。我们改成按场景推荐（scenario_recommendations），每个场景独立给结论与可信度，缺证据的场景标 data_missing 而不是硬凑。\n这既贴合真实选购决策，也呼应‘有证据才推荐’的可信度原则。");
})();

// =================== SLIDE 24 — Demo 流程 ===================
(() => {
  const s = base(24, { kicker: "Live Demo · 演示路径", title: "现场演示：两条数据路线" });
  card(s, 0.62, 1.72, 5.95, 2.5, C.emerald);
  s.addText("线路 A · 本地命中（即时高可信）", { x: 0.88, y: 1.9, w: 5.5, h: 0.4, fontFace: F.h, fontSize: 14, color: C.white, bold: true, margin: 0 });
  bullets(s, ["输入 GPX2 / Logitech G Pro X Superlight 2","本地硬件事实高可信底座","本地评价库满维度体验证据"], { x: 0.92, y: 2.45, w: 5.5, h: 1.7, size: 12 });
  card(s, 6.78, 1.72, 5.94, 2.5, C.amber);
  s.addText("线路 B · 非本地走 MCP（实时）", { x: 7.04, y: 1.9, w: 5.5, h: 0.4, fontFace: F.h, fontSize: 14, color: C.white, bold: true, margin: 0 });
  bullets(s, ["输入 Razer Viper V4 Pro","Search→官网候选→OfficialSpec 抽规格","Price 采集（遇反爬低可信披露）+ ReviewIntel 实时抽取"], { x: 7.08, y: 2.45, w: 5.5, h: 1.7, size: 12 });
  const acts=["产品输入","Workflow DAG","Collector","Evidence","Verification","Quality","人工反馈","最终报告"];
  const n=acts.length,x0=0.62,bw=1.42,gap=(12.1-bw*n)/(n-1),y=4.7,bh=0.85;
  acts.forEach((a,i)=>{const x=x0+i*(bw+gap);s.addShape(pres.shapes.ROUNDED_RECTANGLE,{x,y,w:bw,h:bh,rectRadius:0.06,fill:{color:C.card},line:{color:C.cyan,width:1.2}});
    s.addShape(pres.shapes.OVAL,{x:x+bw/2-0.15,y:y+0.1,w:0.3,h:0.3,fill:{color:C.card2},line:{color:C.cyan,width:1.2}});
    s.addText(String(i+1),{x:x+bw/2-0.15,y:y+0.1,w:0.3,h:0.3,align:"center",valign:"middle",fontFace:F.h,fontSize:11,color:C.cyan,bold:true,margin:0});
    s.addText(a,{x,y:y+0.45,w:bw,h:0.35,align:"center",fontFace:F.b,fontSize:9.5,color:C.text,margin:0});
    if(i<n-1)s.addShape(pres.shapes.LINE,{x:x+bw,y:y+bh/2,w:gap,h:0,line:{color:C.lineHi,width:1.2,endArrowType:"triangle"}});});
  s.addNotes("演示编排：A 路线先展示本地命中的即时高可信（GPX2），B 路线展示真实 MCP 采集（Viper）。中间依次点开 Collector/Evidence/Verification/Quality，最后在 Analysis 页提交一条人工反馈，回到报告看场景推荐更新。\n提示：B 路线冷启动约 60-90s，建议提前预热让缓存变热，或用 5 分钟录屏兜底防断网。");
})();

// =================== SLIDE 25 — 结果与指标 ===================
(() => {
  const s = base(25, { kicker: "Results · 结果说明", title: "项目完成情况与效果" });
  const done=["LangGraph 多 Agent DAG","专业电竞鼠标 Schema","本地事实库 + 双路线评价库","Search / OfficialSpec / Price / ReviewIntel MCP","Evidence / Claim / Report 结构化","Verification 防幻觉 + Quality 门控","前端 Workflow 可视化","SWOT 进 DAG + 人工修正闭环"];
  card(s,0.62,1.72,7.0,4.55,C.emerald);
  s.addText("已完成（功能完成度）",{x:0.88,y:1.9,w:6.5,h:0.4,fontFace:F.h,fontSize:14,color:C.white,bold:true,margin:0});
  s.addText(done.map(t=>({text:t,options:{bullet:{code:"2713",indent:14},breakLine:true,color:C.text,paraSpaceAfter:6}})),
    {x:0.92,y:2.42,w:6.5,h:3.7,fontFace:F.b,fontSize:12.5,valign:"top",margin:0,color:C.emerald});
  // stat tiles
  const stats=[["分钟级","对比人工数小时"],["100%","结论绑定 evidence_id"],["7","场景化推荐维度"],["0 伪造","缺数据→降级披露"]];
  stats.forEach((st,i)=>{const x=7.85,y=1.72+i*1.16;card(s,x,y,4.87,1.0,ACC[i%ACC.length]);
    s.addText(st[0],{x:x+0.22,y:y+0.12,w:1.7,h:0.76,fontFace:F.h,fontSize:24,color:ACC[i%ACC.length],bold:true,valign:"middle",margin:0});
    s.addText(st[1],{x:x+2.0,y:y,w:2.75,h:1.0,fontFace:F.b,fontSize:12,color:C.text,valign:"middle",margin:0});});
  scoreTag(s,"工程完整度 · 业务价值（25% / 20%）");
  s.addNotes("左边是功能完成度清单（全部已落地）。右边四个可量化卖点：分钟级 vs 人工数小时、100% 结论可溯源、7 个场景维度、0 伪造（抓不到就降级披露）。\n注意措辞：分钟级是流程自动化的量级对比；可信度类指标（citation_rate/coverage_rate/faithfulness_rate）由 metrics_service 实时算出，可在报告页展示。");
})();

// =================== SLIDE 26 — 可观测性 ===================
(() => {
  const s = base(26, { kicker: "Observability · 技术说明", title: "Agent 可观测性与 Token 成本" });
  card(s,0.62,1.72,5.95,4.55,C.cyan);
  s.addText("已有",{x:0.88,y:1.9,w:5.5,h:0.4,fontFace:F.h,fontSize:14,color:C.white,bold:true,margin:0});
  bullets(s,["每个 Agent 的 trace_log（step / status / 摘要 / 耗时）","run_node 统一记录 duration_ms 与 error_log","Evidence / Claim / Quality / Report 全可查看","LangSmith 全链路 trace（已开 TRACING_V2）"],{x:0.92,y:2.45,w:5.5,h:3.5,size:12.5});
  card(s,6.8,1.72,5.92,4.55,C.violet);
  s.addText("规划补充（Observability 页）",{x:7.06,y:1.9,w:5.4,h:0.4,fontFace:F.h,fontSize:14,color:C.white,bold:true,margin:0});
  bullets(s,["每个 Agent 耗时 + MCP 调用次数","prompt / completion / total tokens","estimated cost 估算","LangSmith trace 跳转按钮"],{x:7.1,y:2.45,w:5.4,h:3.5,size:12.5});
  s.addText("说明：LangSmith 用于深度 trace；项目内页面用于稳定答辩展示（不依赖现场网络）。",
    {x:0.62,y:6.22,w:12,h:0.34,fontFace:F.b,fontSize:11.5,color:C.mut,italic:true,margin:0});
  scoreTag(s,"可观测性达标 · Token 消耗可查（25%）",6.62);
  s.addNotes("诚实表述：trace_log/耗时/错误已经有；LangSmith 已开，能看到每个 LLM 调用的 prompt/输出/token/耗时——现场演示直接打开 LangSmith 面板即可回答‘token 怎么观测’。\n项目内 Token 看板是规划项（已留接口位）。不要把规划说成已完成，但要展示 LangSmith 实证。");
})();

// =================== SLIDE 27 — 合规 ===================
(() => {
  const s = base(27, { kicker: "Compliance · 合规声明", title: "信息采集合规与数据安全" });
  cardGrid(s, [
    { h: "采集合规", accent: C.emerald, b: ["只采集公开网页信息","遇反爬不绕过 → 标 blocked / 低可信","走 Tavily 官方搜索 API"] },
    { h: "数据安全", accent: C.cyan, b: ["不抓取隐私数据","人工输入仅作当前任务 evidence","API Key 不入仓（.env / .gitignore）"] },
    { h: "来源留痕", accent: C.violet, b: ["外部数据保留 source_url","附可信度标记，可回溯"] },
    { h: "风险披露", accent: C.amber, b: ["视频字幕/API 可能受限","电商价格区域差异","搜索摘要不作强证据"] },
  ], { y: 1.72, cols: 2, ch: 1.72, gapy: 0.28 });
  s.addText("原则：抓不到就如实标“未抓取 / 被反爬”，绝不编造；合规优先于覆盖率。",
    { x: 0.62, y: 5.42, w: 12, h: 0.34, fontFace: F.b, fontSize: 12, color: C.emerald, italic: true, margin: 0 });
  scoreTag(s, "合规、材料与答辩（10%）", 6.6);
  s.addNotes("合规四点：只采公开信息、反爬不绕过只降级、不碰隐私、Key 不入仓。来源全程留 source_url + 可信度，可回溯。\n主动披露已知限制（视频 API 受限、电商价区域差异、搜索摘要不算强证据），把‘抓得少’讲成‘诚实分级’而非缺陷。");
})();

// =================== SLIDE 28 — 技术难点 ===================
(() => {
  const s = base(28, { kicker: "Hard Problems · 技术说明", title: "我们遇到的真实问题与解决" });
  const rows=[
    ["结果像写死、Agent 秒出","区分本地快评与 Agent 最终分析；接 MCP/LLM 后真实耗时"],
    ["证据数量 / 质量分固定","移除 mock，改由真实 evidence / pending / weak 驱动"],
    ["搜索候选 ≠ 实体解析","SearchMCP 只找候选，OfficialSpec 负责抽规格"],
    ["非本地产品无法分析","允许任意输入，未命中走 Search / 官网 MCP"],
    ["LLM 可能编造体验结论","evidence_id 强制 + Verification 拦截 + Quality 降级"],
    ["前端信息过载","Agent 卡片折叠、点击详情、DAG 可视化"],
  ];
  let y=1.78;
  rows.forEach((r,i)=>{const acc=ACC[i%ACC.length];
    s.addShape(pres.shapes.ROUNDED_RECTANGLE,{x:0.62,y,w:12.1,h:0.72,rectRadius:0.06,fill:{color:i%2?C.card:C.bg2},line:{color:C.line,width:1}});
    s.addShape(pres.shapes.RECTANGLE,{x:0.62,y:y+0.1,w:0.06,h:0.52,fill:{color:acc}});
    s.addText("问题 "+(i+1),{x:0.85,y,w:1.1,h:0.72,fontFace:F.h,fontSize:11,color:acc,bold:true,valign:"middle",margin:0});
    s.addText(r[0],{x:2.0,y,w:4.4,h:0.72,fontFace:F.b,fontSize:11.5,color:C.white,valign:"middle",margin:0});
    s.addShape(pres.shapes.LINE,{x:6.5,y:y+0.36,w:0.22,h:0,line:{color:acc,width:1.4,endArrowType:"triangle"}});
    s.addText(r[1],{x:6.85,y,w:5.7,h:0.72,fontFace:F.b,fontSize:11,color:C.text,valign:"middle",margin:0});
    y+=0.8;});
  scoreTag(s,"工程完整度 · 错误恢复 · 幻觉抑制（25%）",6.65);
  s.addNotes("这页很加分——展示我们踩过的真实坑和工程化解决，体现‘不是 demo 玩具’。每一条都是真发生过的：早期像写死、mock 证据、搜索当事实、非本地不能分析、LLM 编造、前端过载。\n对应评分里的工程完整度、错误恢复、幻觉抑制。");
})();

// =================== SLIDE 29 — 评分对应 ===================
(() => {
  const s = base(29, { kicker: "Rubric Mapping · 总结", title: "评分标准逐项对应" });
  const blocks=[
    ["多 Agent 协作 35%",C.cyan,["7 Agent + SWOT 节点 · LangGraph DAG","结构化 state · Quality 反馈闭环","Evidence 全程可追溯"]],
    ["技术深度 25%",C.violet,["MCP + LLM 结构化抽取","上下文裁剪 · Verification 防幻觉","降级机制 · LangSmith 可观测"]],
    ["业务价值 20%",C.emerald,["竞品分析自动化 · 专业 Schema","场景推荐 · 人工修正闭环"]],
    ["代码与文档 10%",C.amber,["前后端模块化 · Service 分层","README / 架构 / 协议 / Schema 文档"]],
    ["合规 10%",C.rose,["公开数据 · 反爬降级","隐私保护 · 来源留痕"]],
  ];
  // big block + 4 small
  card(s,0.62,1.72,5.0,4.55,blocks[0][1]);
  s.addText(blocks[0][0],{x:0.9,y:1.95,w:4.5,h:0.5,fontFace:F.h,fontSize:18,color:C.white,bold:true,margin:0});
  bullets(s,blocks[0][2],{x:0.95,y:2.65,w:4.4,h:3.4,size:13.5});
  for(let i=1;i<5;i++){const r=Math.floor((i-1)/2),c=(i-1)%2;const x=5.85+c*3.5,y=1.72+r*2.32;
    card(s,x,y,3.32,2.12,blocks[i][1]);
    s.addText(blocks[i][0],{x:x+0.22,y:y+0.16,w:3.0,h:0.4,fontFace:F.h,fontSize:13,color:C.white,bold:true,margin:0});
    bullets(s,blocks[i][2],{x:x+0.26,y:y+0.62,w:2.95,h:1.4,size:10.5});}
  s.addNotes("收尾的‘自证’页：把每个权重档位对应到我们的具体实现。35% 是我们最强项（真 DAG + 闭环 + 可追溯），25% 有 MCP/LLM/裁剪/防幻觉/可观测，20% 有自动化+专业 Schema+场景推荐+人工修正，10%+10% 文档与合规齐备。\n讲的时候按权重顺序，从大到小。");
})();

// =================== SLIDE 30 — 未来拓展 ===================
(() => {
  const s = base(30, { kicker: "Extensibility · 未来展望", title: "从电竞鼠标到通用竞品分析平台" });
  // central: 换 Schema 复用 DAG
  card(s,0.62,1.78,5.6,4.0,C.cyan);
  s.addText("换行业，只换两样",{x:0.9,y:1.98,w:5.1,h:0.4,fontFace:F.h,fontSize:15,color:C.white,bold:true,margin:0});
  bullets(s,[{t:"① 替换该行业专业 Schema",color:C.text},{t:"② 替换数据需求配置",color:C.text},{t:"ResearchAgent 自动按新 Schema 规划需求",color:C.mut},{t:"CollectorAgent 复用 MCP 工具层",color:C.mut},{t:"Evidence/Verification/Quality/Report 不变",color:C.mut}],{x:0.95,y:2.55,w:5.1,h:3.1,size:12.5});
  card(s,6.45,1.78,6.27,4.0,C.violet);
  s.addText("可拓展方向",{x:6.71,y:1.98,w:5.8,h:0.4,fontFace:F.h,fontSize:15,color:C.white,bold:true,margin:0});
  const dirs=[["短视频软件",C.cyan],["SaaS 产品",C.violet],["电商平台",C.emerald],["手机 / 数码",C.amber]];
  dirs.forEach((d,i)=>{const r=Math.floor(i/2),c=i%2;const x=6.71+c*2.95,y=2.6+r*1.45;
    card(s,x,y,2.75,1.2,d[1]);s.addText(d[0],{x:x+0.2,y,w:2.4,h:1.2,fontFace:F.h,fontSize:14,color:C.white,bold:true,valign:"middle",margin:0});});
  s.addText("比通用 Schema 更专业，比完全定制更可拓展。",{x:0.62,y:6.05,w:12,h:0.34,fontFace:F.b,fontSize:12,color:C.emerald,italic:true,margin:0});
  s.addNotes("把‘选垂直’的质疑转成‘可拓展’的优势：主流程（Agent DAG + 证据/校验/质检/报告）行业无关，换行业只替换专业 Schema 和数据需求配置，ResearchAgent 自动按新 Schema 规划。\n这就是‘专业 + 可迁移’的平衡。");
})();

// =================== SLIDE 31 — 提交材料 ===================
(() => {
  const s = base(31, { kicker: "Deliverables · 补充材料", title: "提交材料与 Demo 备份" });
  card(s,0.62,1.72,5.95,4.55,C.cyan);
  s.addText("提交清单",{x:0.88,y:1.9,w:5.5,h:0.4,fontFace:F.h,fontSize:14,color:C.white,bold:true,margin:0});
  s.addText(["Git 仓库（结构清晰、分支规范）","README","架构图","Agent 角色与协议文档","Schema 文档","合规声明","5 分钟以内 Demo 录屏"].map(t=>({text:t,options:{bullet:{code:"2713",indent:14},breakLine:true,color:C.text,paraSpaceAfter:7}})),
    {x:0.92,y:2.45,w:5.5,h:3.6,fontFace:F.b,fontSize:13,valign:"top",color:C.emerald,margin:0});
  card(s,6.8,1.72,5.92,4.55,C.violet);
  s.addText("Demo 录屏结构（防断网）",{x:7.06,y:1.9,w:5.4,h:0.4,fontFace:F.h,fontSize:14,color:C.white,bold:true,margin:0});
  s.addText(["产品输入","Agent DAG 运行","MCP 数据采集","Evidence 追溯","Verification / Quality","人工反馈修正","最终报告"].map((t,i)=>({text:`${i+1}. ${t}`,options:{breakLine:true,color:C.text,paraSpaceAfter:7}})),
    {x:7.1,y:2.45,w:5.4,h:3.6,fontFace:F.b,fontSize:13,valign:"top",margin:0});
  scoreTag(s,"提交材料完整、规范（10%）");
  s.addNotes("提醒团队答辩前 checklist：仓库、README、架构图、协议/Schema 文档、合规声明、5 分钟录屏都要齐。录屏按这 7 步走一遍，作为现场断网的兜底。");
})();

// =================== SLIDE 32 — Q&A ===================
(() => {
  const s = base(32, { kicker: "", title: "" });
  s.addText("Q & A", { x: 0.62, y: 0.66, w: 6, h: 0.9, fontFace: F.h, fontSize: 34, color: C.white, bold: true, margin: 0 });
  const qa=[
    ["为什么不做通用竞品分析？","专业 Schema 更能展示结构化深度与分级可信；主流程可换行业复用。"],
    ["怎么防止 LLM 幻觉？","LLM 只抽取/总结；结论必绑 evidence_id；数值 grounding + Verification 拦截 + Quality 降级。"],
    ["为什么有些数据低可信？","官网价/视频可能被反爬或来源不稳；不伪造成高可信，而是风险披露 + 扣分。"],
    ["QualityAgent 真会打回吗？","缺 evidence / unsupported / Schema 不全会打回上游；达上限生成 partial_report。"],
    ["人工输入会不会刷分？","人工证据低可信、待验证，不计入维度覆盖，需非人工证据同向才升支撑。"],
    ["怎么拓展到其他行业？","新增专业 Schema + 数据需求配置，DAG 与 Agent 协作复用。"],
  ];
  let y=1.7;
  qa.forEach((q,i)=>{const acc=ACC[i%ACC.length];
    s.addShape(pres.shapes.ROUNDED_RECTANGLE,{x:0.62,y,w:12.1,h:0.82,rectRadius:0.06,fill:{color:C.card},line:{color:C.line,width:1}});
    s.addShape(pres.shapes.RECTANGLE,{x:0.62,y:y+0.12,w:0.06,h:0.58,fill:{color:acc}});
    s.addText([{text:"Q  ",options:{color:acc,bold:true}},{text:q[0],options:{color:C.white,bold:true}}],{x:0.85,y:y+0.08,w:11.6,h:0.34,fontFace:F.b,fontSize:12.5,margin:0});
    s.addText([{text:"A  ",options:{color:C.emerald,bold:true}},{text:q[1],options:{color:C.text}}],{x:0.85,y:y+0.42,w:11.6,h:0.34,fontFace:F.b,fontSize:11,margin:0});
    y+=0.92;});
  s.addNotes("问答主战场。每个回答都要落到代码事实：防幻觉=evidence_id+grounding+Verification+Quality 四道闸；打回=quality_router 条件边；刷分=人工证据排除在覆盖统计外。\n如果被追问 token/可观测，打开 LangSmith；被追问反爬合规，引用合规页；被追问伪闭环，现场制造证据不足触发打回。");
})();

// =================== SLIDE 33 — Thank You ===================
(() => {
  const s = pres.addSlide();
  s.background = { color: C.bg };
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 0.16, h: H, fill: { color: C.cyanD } });
  // node motif
  const nodes=[[10.6,1.3],[11.9,2.1],[10.2,2.9],[11.6,3.6],[10.7,4.6],[12.4,2.6]];
  nodes.forEach((p,i)=>{for(let j=i+1;j<nodes.length;j++){if((i+j)%2){const a=nodes[i],b=nodes[j];const ax=a[0]+0.12,ay=a[1]+0.12,bx2=b[0]+0.12,by=b[1]+0.12;s.addShape(pres.shapes.LINE,{x:Math.min(ax,bx2),y:Math.min(ay,by),w:Math.abs(bx2-ax),h:Math.abs(by-ay),flipH:bx2<ax,flipV:by<ay,line:{color:C.line,width:1}});}}});
  nodes.forEach((p,i)=>s.addShape(pres.shapes.OVAL,{x:p[0],y:p[1],w:0.24,h:0.24,fill:{color:i%2?C.violet:C.cyan}}));
  s.addText("Thank You", { x: 0.8, y: 2.3, w: 9, h: 1.2, fontFace: F.h, fontSize: 52, color: C.white, bold: true, margin: 0 });
  s.addText("感谢评委老师 · 欢迎体验 Demo", { x: 0.82, y: 3.6, w: 9, h: 0.5, fontFace: F.b, fontSize: 18, color: C.cyan, margin: 0 });
  s.addText([
    { text: "项目仓库：", options: { color: C.mut } }, { text: "[GitHub 链接占位]", options: { color: C.text, breakLine: true } },
    { text: "Demo 视频：", options: { color: C.mut } }, { text: "[链接占位]", options: { color: C.text, breakLine: true } },
    { text: "团队成员：", options: { color: C.mut } }, { text: "[姓名 / 姓名 / 姓名 / 姓名]", options: { color: C.text } },
  ], { x: 0.82, y: 4.5, w: 9, h: 1.4, fontFace: F.b, fontSize: 14, paraSpaceAfter: 6, margin: 0 });
  s.addNotes("收尾：一句话强调差异点——‘一套可追溯、不编造、能换行业的多 Agent 竞品分析系统’，并邀请评委现场体验 Demo 或扫码看录屏。");
})();

pres.writeFile({ fileName: "电竞鼠标竞品分析_答辩.pptx" }).then(f => console.log("WROTE", f));
