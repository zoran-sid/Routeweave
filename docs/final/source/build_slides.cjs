// SkyRoute v2 presentation builder (pptxgenjs 3.12). Chart data is read from the members' result files.
// Usage (repo root): npm install pptxgenjs@3.12.0 (brings jszip; any directory on NODE_PATH), then
//   node docs/final/source/build_slides.cjs [output.pptx]
const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");

const ROOT = path.resolve(__dirname, "../../..");
const OUT = process.argv[2] || path.join(ROOT, "docs/final/SkyRoute-presentation.pptx");
const J = (p) => JSON.parse(fs.readFileSync(path.join(ROOT, p), "utf8"));
const opA = J("docs/modules/yht/v2/experiments/results/op_a_index_comparison.json").results;
const store = J("docs/modules/zqo/v2/experiments/results/transactions-storage.json").storage;
const access = J("docs/modules/zc/v2/experiments/results/access_paths.json").scales;
const inval = J("docs/modules/zc/v2/experiments/results/invalidation.json").transitions;

const FONT = "Microsoft YaHei";
const C = { navy: "13293D", teal: "147D86", tealLt: "D7EEF0", sky: "EEF4F8", amber: "D98B1F", amberLt: "FBEFD9",
  ink: "1B2B38", muted: "5B6B78", line: "C9D6DF", white: "FFFFFF", grey: "8A99A6", greyLt: "E6EBEF" };
const W = 13.333, H = 7.5, M = 0.6;
// Chart series colors, checked with the dataviz skill's validate_palette.js (light surface, adjacent pairs: all pass;
// amber is below 3:1 contrast, so its series carries a direct label). Color follows the entity across slides:
// full-read baseline = blue, second baseline = amber, the design we chose = teal.
const SERIES = { base: "1C6FB8", alt: "D9822B", third: "C94F8A", fourth: "5B4AC2", chosen: "0F9A8C" };
// Selective direct labels: series name -> [point indexes, number format]. Written as native per-point
// data labels after pptxgenjs saves the file (pptxgenjs only labels whole charts).
const US = '[>=1000]#,##0" µs";0.0" µs"', MS = '0.00" ms"', MIB = '0.00" MiB"';
const POINT_LABELS = { "全表扫描": [[2], US], "时间 B-tree": [[2], US], "四维 R*Tree": [[2], US],
  "全量复制": [[2], MIB], "组件共享": [[2], MIB], "JSON 全量": [[2], MS], "SQL 全量": [[2], MS], "R*Tree": [[2], MS] };

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.title = "SkyRoute 时空数据管理系统设计";
pres.author = "SkyRoute 小组";
pres.theme = { headFontFace: FONT, bodyFontFace: FONT };

pres.defineSlideMaster({
  title: "CONTENT", background: { color: C.white },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: M, y: 0.35, w: W - 2 * M, h: 0.9, fontFace: FONT,
      fontSize: 30, bold: true, color: C.navy, valign: "middle", align: "left", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "presenter", type: "body", x: M, y: H - 0.5, w: 6, h: 0.3, fontFace: FONT,
      fontSize: 11, color: C.muted, margin: 0 }, text: "" } },
    { text: { text: "SkyRoute v2 · 香港九龙开放数据实验", options: { x: W - M - 4.6, y: H - 0.5, w: 4, h: 0.3, fontFace: FONT,
      fontSize: 11, color: C.muted, align: "right", margin: 0 } } },
  ],
  slideNumber: { x: W - M - 0.5, y: H - 0.5, w: 0.5, h: 0.3, fontFace: FONT, fontSize: 11, color: C.muted, align: "right" },
});
pres.defineSlideMaster({ title: "DARK", background: { color: C.navy }, objects: [] });

function text(s, t, o) {
  s.addText(t, { fontFace: FONT, color: C.ink, fontSize: 15, margin: 0, isTextBox: true, valign: "top", ...o });
}
function card(s, x, y, w, h, fill, name) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, fill: { color: fill }, line: { color: fill }, rectRadius: 0.08, objectName: name });
}
function content(section, title, presenter, notes) {
  const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: section });
  s.addText(title, { placeholder: "title" });
  s.addText(presenter, { placeholder: "presenter" });
  s.addNotes(notes);
  return s;
}
function table(s, rows, o) {
  const head = rows[0].map((v) => ({ text: v, options: { bold: true, color: C.white, fill: { color: C.navy } } }));
  const body = rows.slice(1).map((r, i) => r.map((v) => (typeof v === "object" ? v : { text: v,
    options: { fill: { color: i % 2 ? C.white : C.sky } } })));
  s.addTable([head, ...body], { fontFace: FONT, fontSize: 13, color: C.ink, border: { type: "solid", pt: 0.75, color: C.line },
    valign: "middle", margin: [4, 6, 4, 6], ...o });
}
function arrow(s, x1, y1, x2, y2, color = C.navy) {
  s.addShape(pres.shapes.LINE, { x: x1, y: y1, w: x2 - x1, h: y2 - y1, line: { color, width: 1.5, endArrowType: "triangle" } });
}
const axis = { catAxisLabelFontFace: FONT, valAxisLabelFontFace: FONT, catAxisLabelFontSize: 12, valAxisLabelFontSize: 11,
  catAxisLabelColor: C.muted, valAxisLabelColor: C.muted, valGridLine: { color: "E3E9EE", size: 0.75 },
  catGridLine: { style: "none" }, legendFontFace: FONT, legendFontSize: 12, legendColor: C.ink,
  titleFontFace: FONT, titleFontSize: 13, titleColor: C.ink, valAxisTitleFontFace: FONT, valAxisTitleFontSize: 11,
  valAxisTitleColor: C.muted, catAxisTitleFontFace: FONT, catAxisTitleFontSize: 11, catAxisTitleColor: C.muted };

// ---------------------------------------------------------------- 1 title
pres.addSection({ title: "开场" });
{
  const s = pres.addSlide({ masterName: "DARK", sectionTitle: "开场" });
  const layers = [["城市三维环境", "每月更新", 1.2], ["动态空域限制", "公告即时生效", 2.25], ["地面暴露与风险", "普查与设施重算", 3.3]];
  layers.forEach(([a, b, y], i) => {
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 8.0, y, w: 3.0, h: 0.8, fill: { color: [C.teal, "1F6F8B", "2D5E7A"][i] },
      line: { color: C.navy }, rectRadius: 0.1, objectName: "data-layer-" + (i + 1) });
    text(s, [{ text: a, options: { bold: true, breakLine: true } }, { text: b, options: { fontSize: 12 } }],
      { x: 8.2, y: y + 0.1, w: 2.7, h: 0.65, color: C.white, fontSize: 15 });
    arrow(s, 11.05, y + 0.4, 11.6, 2.65, "8FB3C6");
  });
  s.addShape(pres.shapes.OVAL, { x: 11.6, y: 2.05, w: 1.2, h: 1.2, fill: { color: C.amber }, line: { color: C.amber }, objectName: "one-release" });
  text(s, "一次\n发布", { x: 11.6, y: 2.3, w: 1.2, h: 0.75, color: C.navy, bold: true, align: "center", fontSize: 16 });
  text(s, "SkyRoute", { x: M + 0.1, y: 1.3, w: 7, h: 1.1, color: C.white, fontSize: 54, bold: true, objectName: "slide-title" });
  text(s, "面向城市无人机配送的时空数据管理系统设计", { x: M + 0.1, y: 2.5, w: 7.2, h: 0.6, color: "CFE3EA", fontSize: 22 });
  text(s, "让每一次航线查询都基于一致、可追溯、受控的数据", { x: M + 0.1, y: 3.25, w: 7.2, h: 0.5, color: C.white, fontSize: 16, italic: true });
  text(s, "INT6164 小组路演 · 2026 年 11 月 · 数据：香港九龙旺角\nZQO · YHT · LQ · ZC · LJ", { x: M + 0.1, y: 5.6, w: 7, h: 0.9, color: "AFC4D0", fontSize: 14 });
  s.addNotes("ZQO：我们的项目叫 SkyRoute。无人机配送的航线要同时依赖三类数据：城市三维环境每月更新，限飞区随公告生效，地面暴露随普查和设施数据重算。我们用香港九龙旺角一带的政府开放数据做全部实验。我们研究的不是怎么搜出一条最短路，而是怎样让每次查询读到一致、可追溯、受控的数据。接下来五位成员分别讲问题与架构、数据模型、事务与版本、治理、查询性能和恢复。");
}

// ---------------------------------------------------------------- 2 ZQO problem
pres.addSection({ title: "问题与架构（ZQO）" });
{
  const s = content("问题与架构（ZQO）", "每次航线查询，都应知道自己用了哪一版数据", "主讲：ZQO",
    "ZQO：先看问题。三类数据更新节奏完全不同。如果查询在空域更新的同时分批读取，就可能把新禁飞区和旧风险值拼在一起，结果既不可信，事后也说不清依据是哪一版。我们的核心问题是：数据持续变化时，如何支持高效时空查询、一致性发布、历史追溯和安全访问，为航线规划提供可靠输入。右边是四类用户各自得到的价值：调度员不会采用旧结果，运营人员能看到依据，管理员能追溯变更，系统管理员故障后能证明数据一致。来源：报告第1章；《作业要求.pdf》第1–2页。");
  const rows = [["城市三维环境", "建筑轮廓与高度 · 地政总署", "每月"], ["动态空域限制", "无人机限飞区 · 民航处公告", "事件"], ["地面暴露与风险", "普查人口、学校、医院 · 派生风险", "定期"]];
  rows.forEach(([a, b, c], i) => {
    const y = 1.55 + i * 1.05;
    card(s, M, y, 5.6, 0.85, C.sky, "data-card-" + (i + 1));
    text(s, [{ text: a, options: { bold: true, breakLine: true } }, { text: b, options: { fontSize: 13, color: C.muted } }], { x: M + 0.25, y: y + 0.12, w: 3.9, h: 0.65 });
    text(s, c, { x: M + 4.3, y: y + 0.2, w: 1.1, h: 0.45, color: C.teal, bold: true, fontSize: 20, align: "right" });
  });
  card(s, M, 4.85, 5.6, 1.6, C.amberLt, "risk-callout");
  text(s, [{ text: "风险在数据层", options: { bold: true, color: C.amber, breakLine: true, fontSize: 17 } },
    { text: "分批读取 → 新禁飞区 + 旧风险值 → 结果不可信、事后无法复现", options: { fontSize: 15 } }], { x: M + 0.25, y: 5.0, w: 5.1, h: 1.3 });
  table(s, [["用户", "需要的结果", "数据管理价值"],
    ["物流调度员", "可行航线与所用版本", "不采用已被新限制影响的旧结果"],
    ["运营人员", "限制、风险依据与质量", "识别未知数据与待复核区域"],
    ["空域及安全管理员", "发布、撤销并追溯", "责任、事件顺序与历史完整"],
    ["系统管理人员", "审计、恢复与核验", "故障后证明数据与清单一致"]],
    { x: 6.75, y: 1.55, w: 6.0, colW: [1.7, 1.9, 2.4], rowH: 0.62 });
  card(s, 6.75, 4.85, 6.0, 1.6, C.navy, "question");
  text(s, [{ text: "核心问题", options: { bold: true, color: C.amber, breakLine: true, fontSize: 15 } },
    { text: "数据持续变化时，如何支持高效时空查询、一致性发布、历史追溯和安全访问，为航线规划提供可靠输入？", options: { color: C.white } }],
  { x: 7.0, y: 5.0, w: 5.5, h: 1.35, fontSize: 15 });
}

// ---------------------------------------------------------------- 3 ZQO architecture
{
  const s = content("问题与架构（ZQO）", "一个数据库承载五类数据，五位成员各管一层", "主讲：ZQO",
    "ZQO：这是总体架构。YHT 负责接入和质检，把多源数据规范到统一坐标、时间与质量字段。所有权威数据放在同一个数据库里，所以一次发布可以在一个事务中提交。LQ 在发布后编译风险数据集并封存；我负责发布服务，保证原子切换和固定版本读取；ZC 的规划服务只通过数据库取数；LJ 负责备份、恢复核验和监测。JSON 导出、空间索引和派生图都可以从发布重建，数据库是唯一事实来源。来源：报告第3章图1、图2。");
  const steps = [["接入与质检", "YHT", "来源登记 · 质量门禁"], ["统一数据库", "全组", "34 个实体 · 约束与索引"],
    ["风险派生与治理", "LQ", "数据集封存 · 受限视图"], ["发布服务", "ZQO", "原子发布 · 固定版本"], ["规划服务", "ZC", "Q1 / Q2 · 派生图"]];
  steps.forEach(([a, who, b], i) => {
    const x = M + i * 2.48;
    card(s, x, 1.6, 2.15, 1.6, i === 1 ? C.navy : C.sky, "layer-" + (i + 1));
    const fg = i === 1 ? C.white : C.ink;
    text(s, [{ text: who, options: { fontSize: 12, color: i === 1 ? "AFC4D0" : C.teal, bold: true, breakLine: true } },
      { text: a, options: { bold: true, fontSize: 17, breakLine: true } }, { text: b, options: { fontSize: 13, color: i === 1 ? "CFE3EA" : C.muted } }],
      { x: x + 0.18, y: 1.75, w: 1.85, h: 1.35, color: fg });
    if (i < 4) arrow(s, x + 2.17, 2.4, x + 2.46, 2.4);
  });
  card(s, M, 3.45, 12.1, 0.7, C.greyLt, "lj-band");
  text(s, [{ text: "LJ 保障：", options: { bold: true } }, { text: "在线备份 · 恢复后五项核验 · 监测与保留策略" }], { x: M + 0.25, y: 3.57, w: 11.5, h: 0.45 });
  const claims = [["数据库是唯一事实来源", "JSON、索引、派生图都可由发布重建"], ["查询先固定发布", "经组件映射找到每层的物理所有者"], ["结果记录所用版本", "发布、组件、风险数据集一并写入"]];
  claims.forEach(([a, b], i) => {
    const x = M + i * 4.1;
    card(s, x, 4.55, 3.85, 1.85, C.sky, "claim-" + (i + 1));
    s.addShape(pres.shapes.OVAL, { x: x + 0.25, y: 4.8, w: 0.55, h: 0.55, fill: { color: C.teal }, line: { color: C.teal }, objectName: "claim-dot-" + (i + 1) });
    text(s, String(i + 1), { x: x + 0.25, y: 4.88, w: 0.55, h: 0.4, color: C.white, bold: true, align: "center", fontSize: 16 });
    text(s, [{ text: a, options: { bold: true, fontSize: 17, breakLine: true } }, { text: b, options: { fontSize: 14, color: C.muted } }], { x: x + 0.25, y: 5.5, w: 3.4, h: 0.85 });
  });
}

// ---------------------------------------------------------------- 4 YHT data
pres.addSection({ title: "数据与模型（YHT）" });
{
  const s = content("数据与模型（YHT）", "三类数据、三种节奏，统一到一套由数据库强制的模式", "主讲：YHT",
    "YHT：数据全部来自香港政府开放数据。以旺角为中心 3.3 公里见方的九龙 L 区有地政总署的 10,674 栋建筑轮廓和高度、2021 年人口普查的 269 个区组、298 所学校和 5 家医院机构，以及民航处宪报公布的 8 处无人机限飞区。坐标是 HK1980 方格网，高度是主水平基准以上米数。492 栋开放式或临时构筑物没有高度，我们按全高度障碍处理，不当作安全空间；限飞区公告只列名称，边界由设施轮廓外扩 20 米近似。我们把它们统一到 34 个实体的关系模式，规则由数据库在写入时强制：发布后的数据不能改，来源和模型修订必须登记新标识，取值一致性用 CHECK 和触发器保证。建模中修正了三处问题：瓦片和地形编号每次发布重复，主键必须带发布编号；空域状态随发布固定；限高体禁止的是上限以上的空间。来源：报告第2、4章；数据字典。");
  const cards = [["城市三维环境", "10,674 栋建筑", "492 栋无高度 · mPD 基准 · 多部件轮廓"], ["动态空域", "8 处限飞区", "公告只列名称 · 临时限制为场景数据"], ["地面暴露与风险", "572 个暴露分区", "普查按居住地 · 代理值被误读"]];
  cards.forEach(([a, n, r], i) => {
    const x = M + i * 4.1;
    card(s, x, 1.55, 3.8, 1.55, C.sky, "dataset-" + (i + 1));
    text(s, [{ text: a, options: { bold: true, breakLine: true, fontSize: 17 } }, { text: n, options: { fontSize: 22, bold: true, color: C.teal, breakLine: true } },
      { text: r, options: { fontSize: 13, color: C.muted } }], { x: x + 0.25, y: 1.68, w: 3.35, h: 1.35 });
  });
  text(s, "九龙 L 区实测（3.3 km 见方，2026-11-07 快照；来源：地政总署、政府统计处、教育局、医管局、民航处）", { x: M, y: 3.18, w: 8, h: 0.35, fontSize: 12, color: C.muted });
  const rules = [["34", "个实体，四个表组按成员负责"], ["发布后", "空间行、来源、模型均不可原地修改"], ["CHECK", "高度 = 顶 − 底；q = E × C；区间 lo < hi"], ["只追加", "事件、审计、派生值、查询结果"]];
  rules.forEach(([a, b], i) => {
    const x = M + i * 3.07;
    card(s, x, 3.65, 2.85, 1.5, i === 0 ? C.navy : C.white, "rule-" + (i + 1));
    if (i) s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 3.65, w: 2.85, h: 1.5, fill: { color: C.white }, line: { color: C.line, width: 1 }, rectRadius: 0.08, objectName: "rule-frame-" + (i + 1) });
    text(s, [{ text: a, options: { bold: true, fontSize: i === 0 ? 34 : 20, color: i === 0 ? C.amber : C.navy, breakLine: true } },
      { text: b, options: { fontSize: 14, color: i === 0 ? C.white : C.ink } }], { x: x + 0.2, y: 3.78, w: 2.5, h: 1.3 });
  });
  card(s, M, 5.4, 12.15, 0.75, C.amberLt, "model-fixes");
  text(s, [{ text: "建模时修正三处：", options: { bold: true, color: C.amber } },
    { text: "瓦片与地形主键必须含发布编号 · 空域状态随发布固定、撤销写新发布 · 限高体禁止的是上限以上的空间" }],
  { x: M + 0.25, y: 5.55, w: 11.7, h: 0.5, fontSize: 15 });
}

// ---------------------------------------------------------------- 5 YHT op A
{
  const s = content("数据与模型（YHT）", "时空索引让“窗口内有效限制”的查询不随规模变慢", "主讲：YHT",
    "YHT：操作 A 回答这次任务窗口内，走廊会碰到哪些有效限制。我们在九龙 L 区同一批数据上比较了六种取数路径，每个发布都含 8 处真实限飞区，其余是放在真实建筑位置上的场景限制；结果完全一致，差别只在速度。图中表里保存了 20 个历史发布。限制只有 100 条时，各路径都在二三十微秒。到一万条时，全表扫描 13.7 毫秒，按发布过滤 1.05 毫秒，四维时空 R*Tree 仍是 44 微秒。单列时间 B-tree 只能按开始时间单侧裁剪，反而最慢。SQLite 规划器自选会在路径之间切换，p95 达到 754 微秒，所以查询固定由 R*Tree 驱动。部署到 PostGIS 时对应 n 维 GiST 加范围 GiST，尚未实测。来源：op_a_index_comparison.json；内存 SQLite 3.54.1。");
  const pick = (v) => [100, 1000, 10000].map((n) => opA.find((r) => r.n_per_release === n && r.releases === 20 && r.variant === v).median_us);
  s.addChart(pres.charts.LINE, [
    { name: "全表扫描", labels: ["100", "1,000", "10,000"], values: pick("V0_full_scan") },
    { name: "时间 B-tree", labels: ["100", "1,000", "10,000"], values: pick("V2_time_btree") },
    { name: "发布 B-tree", labels: ["100", "1,000", "10,000"], values: pick("V1_release_btree") },
    { name: "三维 R*Tree", labels: ["100", "1,000", "10,000"], values: pick("V3_rtree_3d") },
    { name: "四维 R*Tree", labels: ["100", "1,000", "10,000"], values: pick("V4_rtree_4d") },
  ], { x: M, y: 1.45, w: 7.8, h: 4.9, ...axis, chartColors: [SERIES.base, SERIES.alt, SERIES.third, SERIES.fourth, SERIES.chosen],
    lineSize: 2, lineDataSymbolSize: 8, valAxisLogScaleBase: 10, showLegend: true, legendPos: "b",
    showValAxisTitle: true, valAxisTitle: "每条查询中位耗时（µs，对数轴）", showCatAxisTitle: true, catAxisTitle: "每个发布的限制数（另存 20 个历史发布）" });
  card(s, 8.85, 1.55, 3.9, 2.3, C.navy, "stat-rtree");
  text(s, [{ text: "44.1 µs", options: { fontSize: 40, bold: true, color: C.amber, breakLine: true } },
    { text: "四维 R*Tree，1 万条限制 × 20 个发布", options: { fontSize: 14, color: C.white } }], { x: 9.1, y: 1.75, w: 3.5, h: 1.9 });
  card(s, 8.85, 4.05, 3.9, 2.3, C.sky, "stat-compare");
  text(s, [{ text: "对比", options: { bold: true, breakLine: true } }, { text: "全表扫描 13.7 ms", options: { breakLine: true } },
    { text: "发布 B-tree 1.05 ms", options: { breakLine: true } }, { text: "6 种路径结果完全一致", options: { color: C.teal, bold: true } }],
    { x: 9.1, y: 4.2, w: 3.5, h: 2.0, fontSize: 15 });
}

// ---------------------------------------------------------------- 6 ZQO transactions
pres.addSection({ title: "事务与版本（ZQO）" });
{
  const s = content("事务与版本（ZQO）", "原子发布保持一致，组件共享节省 97.1% 历史存储", "主讲：ZQO",
    "ZQO：这页是两个选择。第一，组件、当前指针、事件和成功审计在同一个写事务里提交，读者看不到半次发布。两个请求竞争同一旧版本时只有一个成功，另一个明确返回冲突；五处注入失败全部回滚；提交后丢失响应重试，返回同一发布，不会重复产生事件。第二，历史版本复用没有变化的图层。负载是旺角核心 186 栋真实建筑及其地形和暴露分区，每版只改一条场景限制。1000 次发布的数据库从 255.7 MiB 降到 7.45 MiB，历史导出内容一致，读取都约 5 毫秒。发布期间旧读事务继续读旧快照，所以调度采用路线前要用新事务复核当前版本。来源：transactions-storage.json；文件 SQLite，WAL/FULL。");
  table(s, [["实测场景", "结果"], ["两个发布者竞争同一旧版本", "1 次成功 + 1 次版本冲突"], ["五处注入失败", "全部回滚，只留失败记录"],
    ["写入未提交时的旧读事务", "看到旧版；新事务看到完整新版"], ["提交后丢响应并重试", "同一发布，事件不重复"], ["撤销后重开历史版本", "旧版内容与来源不变"]],
    { x: M, y: 1.55, w: 6.3, colW: [3.1, 3.2], rowH: 0.52 });
  const flow = ["写事务：校验预期版本", "组件 + 事件 + 指针 + 审计", "一次 COMMIT"];
  flow.forEach((f, i) => {
    const x = M + i * 2.15;
    card(s, x, 5.0, 1.9, 0.95, i === 2 ? C.teal : C.sky, "txn-" + (i + 1));
    text(s, f, { x: x + 0.1, y: 5.05, w: 1.7, h: 0.85, align: "center", valign: "middle", bold: true, fontSize: 12, color: i === 2 ? C.white : C.ink });
    if (i < 2) arrow(s, x + 1.92, 5.47, x + 2.13, 5.47);
  });
  text(s, "任一步失败 → 全部回滚，另写失败记录", { x: M, y: 6.05, w: 6.3, h: 0.35, fontSize: 13, color: C.amber, bold: true });
  const sz = (mode) => [10, 100, 1000].map((n) => +(store.find((r) => r.mode === mode && r.releases === n).db_bytes / 2 ** 20).toFixed(2));
  s.addChart(pres.charts.BAR, [{ name: "全量复制", labels: ["10 次", "100 次", "1,000 次"], values: sz("full") },
    { name: "组件共享", labels: ["10 次", "100 次", "1,000 次"], values: sz("shared") }],
  { x: 7.2, y: 1.45, w: 5.55, h: 4.3, barDir: "col", barGrouping: "clustered", ...axis, chartColors: [SERIES.base, SERIES.chosen],
    barGapWidthPct: 70, barOverlapPct: -8, showLegend: true, legendPos: "b", showValAxisTitle: true, valAxisTitle: "数据库大小（MiB）", showCatAxisTitle: true, catAxisTitle: "发布次数" });
  text(s, "代价：发布写入串行；共享粒度为整层，改一处仍重写该层", { x: 7.2, y: 5.85, w: 5.55, h: 0.5, fontSize: 13, color: C.muted });
}

// ---------------------------------------------------------------- 7 LQ lineage
pres.addSection({ title: "治理与安全（LQ）" });
{
  const s = content("治理与安全（LQ）", "每条航线都能追溯到来源与风险模型版本", "主讲：LQ",
    "LQ：风险层在我们的设计里是带模型版本的派生数据集。一条航线的每个航段，都能沿着这条链查到：查询用的逻辑发布、组件映射、物理所有者下的暴露分区、已封存的风险数据集、派生值、来源和模型版本。共享组件的所有者可能是旧发布，所以不能直接按新发布编号去筛原表。数据库在封存时独立核对时间覆盖和最大值，应用写一个“质检通过”也盖不住缺口；已批准的模型不能原地修改。来源或模型变化时，反向血缘能定位需要重算的数据集。ZC 已把正式查询结果表接入，36 条实验航线的每个航段都能追溯。来源：governance.json；op_c.sql。");
  const chain = [["航线查询", C.sky], ["逻辑发布", C.tealLt], ["组件映射", C.tealLt], ["物理所有者分区", C.sky], ["已封存数据集", C.amberLt], ["来源 + 模型版本", C.amberLt]];
  chain.forEach(([a, fill], i) => {
    const x = M + i * 2.05;
    card(s, x, 1.75, 1.8, 1.0, fill, "trace-" + (i + 1));
    text(s, a, { x: x + 0.1, y: 1.85, w: 1.6, h: 0.8, align: "center", valign: "middle", bold: true, fontSize: 14 });
    if (i < 5) arrow(s, x + 1.82, 2.25, x + 2.03, 2.25);
  });
  const facts = [["36 / 36", "实验航线的航段全部可追溯"], ["拒绝封存", "时段缺口、q ≠ E × C"], ["新标识修订", "已批准模型不可原地修改"], ["递归定位", "来源变化 → 需重算的数据集"]];
  facts.forEach(([a, b], i) => {
    const x = M + i * 3.07;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 3.05, w: 2.85, h: 1.3, fill: { color: C.white }, line: { color: C.line, width: 1 }, rectRadius: 0.08, objectName: "fact-" + (i + 1) });
    text(s, [{ text: a, options: { bold: true, fontSize: 22, color: C.teal, breakLine: true } }, { text: b, options: { fontSize: 14 } }], { x: x + 0.2, y: 3.18, w: 2.5, h: 1.1 });
  });
  table(s, [["航段", "查询发布", "暴露层物理所有者", "来源", "模型版本"], ["1", "R1", "R0（组件共享）", "教育局学校位置", "lq-risk-v1 · 1.0.0"], ["2", "R1", "R0（组件共享）", "2021 人口普查区组", "lq-risk-v1 · 1.0.0"]],
    { x: M, y: 4.6, w: 12.1, colW: [1.2, 2.0, 3.3, 2.4, 3.2], rowH: 0.42 });
  text(s, "示例：旺角的两段航线，分别经过一所学校和一个普查区组。E 来自普查与设施位置；C 与阈值为演示参数，q = E × C 不是事故概率", { x: M, y: 5.95, w: 12.1, h: 0.4, fontSize: 12, color: C.muted });
}

// ---------------------------------------------------------------- 8 LQ access
{
  const s = content("治理与安全（LQ）", "谁能看、谁能改、谁能批准：规则落在数据库里", "主讲：LQ",
    "LQ：风险数据既要共享，也要限制用途。调度员和运营人员只能通过受限视图看本机构的 200 米格网摘要，直接查原表、内部视图或写 SQL 都被拒绝；安全管理员按策略看分区明细。发布审批绑定内容摘要，作者不能审批自己，审批后也不能换数据。右边是实测结果。200 米和每格至少两个分区是演示参数，不构成匿名保证。AI 只辅助发现异常值和敏感字段，最终变更仍要人工复核。SQLite 没有 GRANT 和行级安全，部署到 PostgreSQL 时用非表所有者角色和 RLS。来源：governance.json；ZC 独立探针 lq-review.json。");
  table(s, [["用户", "读取", "发布 / 审批"], ["调度员", "本机构摘要视图", "禁止"], ["运营人员", "摘要视图与任务解释", "禁止"],
    ["安全管理员", "明细视图、模型、来源", "独立审批后发布；不可自审"], ["系统管理员", "运行元数据与审计", "默认不授予"]],
    { x: M, y: 1.55, w: 6.1, colW: [1.5, 2.2, 2.4], rowH: 0.62 });
  table(s, [["情境", "实测结果"], ["缺 E/C、q 不一致", "拒绝入库"], ["时间缺口、伪写“质检通过”", "拒绝封存"], ["越权查原表或写 SQL", "拒绝"],
    ["不同机构、停用账号", "无可见行"], ["作者审批自己的发布", "拒绝"], ["原地修改已批准模型", "拒绝，新标识修订"]],
    { x: 7.0, y: 1.55, w: 5.75, colW: [3.25, 2.5], rowH: 0.62 });
  card(s, M, 4.95, 6.1, 1.4, C.amberLt, "privacy");
  text(s, [{ text: "共享 vs 隐私：", options: { bold: true, color: C.amber } }, { text: "内部用精确分区规划，对外只给 200 m 格网、每格 ≥ 2 个分区的聚合摘要" }], { x: M + 0.2, y: 5.1, w: 5.75, h: 1.15, fontSize: 15 });
}

// ---------------------------------------------------------------- 9 ZC access paths
pres.addSection({ title: "查询负载（ZC）" });
{
  const s = content("查询负载（ZC）", "A* 不变，只换取数方式：取数从 55 ms 降到 0.2 ms", "主讲：ZC",
    "ZC：这一页回答规划服务慢在哪里。我们把 A* 固定不动，同一批任务只换取数方式。12 个任务都在旺角核心，三个规模只改变数据库里装的城市范围：S 区 186 栋、M 区 2,267 栋、L 区 10,674 栋。整份读取发布的 JSON，或者用 SQL 读全城对象，耗时都随城市范围线性增长，L 区时分别是 55 毫秒和 21 毫秒；用时空索引只取搜索域附近的对象，稳定在 0.2 毫秒以内。三种方式交给规划器的输入逐字节相同，所以这部分收益完全来自数据库设计。剩下的九到十一毫秒是算法检查航段是否碰到障碍，由旺角的局部密度决定；同一张图上 A* 扩展的节点约是 Dijkstra 的八分之一，最优代价一致。来源：access_paths.json；文件 SQLite 3.54.1，WAL。");
  const labels = access.map((r) => r.area + " 区 · " + r.n_buildings.toLocaleString("en-US") + " 栋");
  const v = (k) => access.map((r) => r.summary[k].data_ms);
  // Lines, not bars: on a log axis bar length does not encode the value.
  s.addChart(pres.charts.LINE, [{ name: "JSON 全量", labels, values: v("json_snapshot") }, { name: "SQL 全量", labels, values: v("sql_full") },
    { name: "R*Tree", labels, values: v("sql_rtree") }],
  { x: M, y: 1.45, w: 7.6, h: 4.95, ...axis, chartColors: [SERIES.base, SERIES.alt, SERIES.chosen], lineSize: 2, lineDataSymbolSize: 8,
    valAxisLogScaleBase: 10, showLegend: true, legendPos: "b", showValAxisTitle: true, valAxisTitle: "每次查询取数中位耗时（ms，对数轴）",
    showCatAxisTitle: true, catAxisTitle: "九龙嵌套区域（同一批 12 个任务）" });
  const pts = [["≈280×", "L 区 10,674 栋时 R*Tree 比 JSON 快"], ["36 / 36", "规划器输入逐字节相同 → 收益来自数据库"], ["9–11 ms", "剩余是算法的航段检查；A* 扩展约为 Dijkstra 的 1/8"]];
  pts.forEach(([a, b], i) => {
    const y = 1.55 + i * 1.62;
    card(s, 8.6, y, 4.15, 1.42, i === 0 ? C.navy : C.sky, "point-" + (i + 1));
    text(s, [{ text: a, options: { bold: true, fontSize: 26, color: i === 0 ? C.amber : C.teal, breakLine: true } },
      { text: b, options: { fontSize: 13, color: i === 0 ? C.white : C.ink } }], { x: 8.85, y: y + 0.12, w: 3.75, h: 1.2 });
  });
}

// ---------------------------------------------------------------- 10 ZC cache
{
  const s = content("查询负载（ZC）", "缓存派生图把查询降到 0.1 ms，新发布后只更新受影响的部分", "主讲：ZC",
    "ZC：既然航段检查是主要成本，可以把整张可飞航段图预先算好。构建一次要七十到八十毫秒，之后每次查询只要零点一毫秒左右，同一区域和时间窗被查询八次就划算。难点在于数据会更新。发布不可变，所以旧版本的缓存对旧版本永远正确，历史查询直接命中。新发布到来时，数据库已经记录了这次改动了哪些禁飞区、哪些风险值；只有与改动重叠的图需要修补，其余直接沿用。实验在旺角 M 区 2,267 栋真实建筑上做，两次变化是放在旺角街道上的场景禁飞区。新增禁飞区时 24 张图只需更新 4 张，用时从 3.0 秒降到 0.24 秒；撤销旧禁飞区时更新 8 张，用时从 3.1 秒降到 0.82 秒。每张都和全部重建的结果核对一致；新增禁飞区让 2 条航线变得不可飞，撤销后 8 条航线重新可飞。选型上，原型用 SQLite 加空间索引，部署换成 PostgreSQL 与 PostGIS。来源：invalidation.json、access_paths.json；报告第6章。");
  const a = access[access.length - 1].summary;
  const stats = [[a.graph_cache.hit_total_ms.toFixed(2) + " ms", "缓存命中（L 区）"], ["第 8 次", "同一键查询起收回构建成本"], ["0 处", "48 张图与全部重建不一致"]];
  stats.forEach(([x1, b], i) => {
    const x = M + i * 2.1;
    card(s, x, 1.55, 1.9, 1.5, i === 0 ? C.navy : C.sky, "cache-stat-" + (i + 1));
    text(s, [{ text: x1, options: { bold: true, fontSize: 22, color: i === 0 ? C.amber : C.teal, breakLine: true } },
      { text: b, options: { fontSize: 12, color: i === 0 ? C.white : C.ink } }], { x: x + 0.15, y: 1.68, w: 1.65, h: 1.3 });
  });
  const tr = inval.map((t, i) => [i === 0 ? "新增禁飞区" : "撤销禁飞区", `${t.carried} / ${t.patched} / ${t.rebuilt}`,
    (t.full_rebuild_ms / 1000).toFixed(2) + " s", (t.targeted_ms / 1000).toFixed(2) + " s", (t.full_rebuild_ms / t.targeted_ms).toFixed(1) + "×"]);
  table(s, [["发布变化", "沿用/修补/重建", "全部重建", "按变更处理", "加速"], ...tr], { x: 7.0, y: 1.55, w: 5.75, colW: [1.35, 1.45, 1.0, 1.15, 0.8], rowH: 0.5, fontSize: 12 });
  text(s, "M 区 2,267 栋 · 24 张缓存图 · 变化为场景禁飞区；变更来自发布事务写入的 airspace_event 与风险数据集差异", { x: 7.0, y: 3.15, w: 5.75, h: 0.55, fontSize: 12, color: C.muted });
  card(s, M, 3.85, 12.15, 1.25, C.sky, "selection");
  text(s, [{ text: "选型", options: { bold: true, fontSize: 17, color: C.navy, breakLine: true } },
    { text: "原型：SQLite + R*Tree（已实测）  →  部署：PostgreSQL + PostGIS（多用户写入、行级权限、三维谓词）", options: { breakLine: true } },
    { text: "派生图留在规划服务内存，依赖与有效性记录在数据库；图数据库 / pgRouting 需为每个发布 × 窗口物化约 1 万条边，暂不采用", options: { color: C.muted, fontSize: 14 } }],
  { x: M + 0.25, y: 3.95, w: 11.6, h: 1.1, fontSize: 15 });
  card(s, M, 5.35, 12.15, 0.75, C.amberLt, "tradeoff");
  text(s, [{ text: "物化 vs 新鲜度：", options: { bold: true, color: C.amber } },
    { text: "缓存以发布为键，查询不会读到其他版本的图；同一键少于 8 次或限制频繁覆盖大面积时，按需搜索更合适" }],
  { x: M + 0.25, y: 5.47, w: 11.7, h: 0.5, fontSize: 14 });
}

// ---------------------------------------------------------------- 11 LJ recovery
pres.addSection({ title: "保障与结论（LJ）" });
{
  const s = content("保障与结论（LJ）", "恢复不是复制文件，而是五项核验全部通过", "主讲：LJ",
    "LJ：备份用 SQLite 在线备份 API，数据库、WAL、审计和发布哈希作为一个整体保护；内存里的派生图不备份，恢复后按发布重建。恢复到隔离路径后，依次检查完整性、外键、发布父链和哈希，再重放一条历史查询比对摘要，全部通过才切换读流量，任何一项失败就阻断，不能显示为可用。实验对旺角核心的两个真实发布做备份恢复，五项全部通过，截断的备份在打开时就被发现是损坏的。RPO 15 分钟、RTO 30 分钟是单机原型的设计目标，不是实测承诺。成本按公开单价估算，2 GB 热数据加备份每月约 0.09 美元。来源：recovery.json；报告第3.3、8.2节。");
  const checks = ["完整性检查", "外键检查", "发布父链与哈希", "历史查询重放", "派生图按发布重建"];
  checks.forEach((c, i) => {
    const x = M + i * 2.48;
    s.addShape(pres.shapes.OVAL, { x: x + 0.7, y: 1.6, w: 0.75, h: 0.75, fill: { color: C.teal }, line: { color: C.teal }, objectName: "check-dot-" + (i + 1) });
    text(s, String(i + 1), { x: x + 0.7, y: 1.72, w: 0.75, h: 0.5, color: C.white, bold: true, align: "center", fontSize: 18 });
    text(s, c, { x, y: 2.5, w: 2.15, h: 0.6, align: "center", bold: true, fontSize: 15 });
    if (i < 4) arrow(s, x + 1.5, 1.98, x + 3.15, 1.98);
  });
  card(s, M, 3.45, 5.9, 2.9, C.navy, "result");
  text(s, [{ text: "实测结果", options: { bold: true, color: C.amber, fontSize: 17, breakLine: true } },
    { text: "正常恢复：五项全部通过", options: { breakLine: true } }, { text: "截断备份：打开即检测为损坏", options: { breakLine: true } },
    { text: "任一项失败 → 阻断推荐，返回 unknown", options: { color: "CFE3EA" } }], { x: M + 0.35, y: 3.65, w: 5.3, h: 2.5, color: C.white, fontSize: 19, valign: "middle", paraSpaceAfter: 6 });
  const kv = [["RPO ≤ 15 分钟", "WAL 与备份频率决定"], ["RTO ≤ 30 分钟", "恢复、核验、派生图重建决定"], ["≈ 0.09 美元 / 月", "2 GB 热数据 + 1 份备份（S3 公开单价估算）"]];
  kv.forEach(([a, b], i) => {
    const y = 3.45 + i * 1.0;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 6.85, y, w: 5.9, h: 0.85, fill: { color: C.white }, line: { color: C.line, width: 1 }, rectRadius: 0.08, objectName: "target-" + (i + 1) });
    text(s, [{ text: a + "  ", options: { bold: true, color: C.navy } }, { text: b, options: { color: C.muted, fontSize: 13 } }], { x: 7.05, y: y + 0.2, w: 5.6, h: 0.5, fontSize: 16 });
  });
  text(s, "RPO / RTO 为单机原型设计目标，部署前需按目标规模演练", { x: 6.85, y: 6.42, w: 5.9, h: 0.3, fontSize: 11, color: C.muted });
}

// ---------------------------------------------------------------- 12 LJ conclusion
{
  const s = pres.addSlide({ masterName: "DARK", sectionTitle: "保障与结论（LJ）" });
  s.addNotes("LJ：最后总结五项权衡。YHT 选择暂存灵活、发布严格；ZQO 选择不可变发布加读快照，采用前复核；LQ 选择内部精确、对外聚合；ZC 选择派生图按发布记账并按变更更新；我选择单机备份加五项恢复核验。局限也很明确：数据是九龙的开放数据，但临时限制是场景数据、普查人口不含日间人流；性能来自单机 SQLite，PostgreSQL 和图数据库只做了设计论证，风险代理不是事故概率。下一步是在 PostgreSQL 上复现发布和查询实验、按目标规模演练恢复，并用真实许可数据评审隐私粒度。我们的结论是：先把数据管好，航线规划才有可靠输入。来源：报告第8章。");
  text(s, "先把数据管好，航线规划才有可靠输入", { x: M, y: 0.45, w: W - 2 * M, h: 0.8, color: C.white, fontSize: 30, bold: true, objectName: "slide-title" });
  const rows = [["灵活模式 vs 数据质量", "暂存灵活、发布严格", "YHT"], ["一致性 vs 可用性", "不可变发布 + 读快照 + 采用前复核", "ZQO"],
    ["共享价值 vs 隐私", "内部精确、对外聚合", "LQ"], ["物化 vs 新鲜度", "派生图按发布记账、按变更更新", "ZC"], ["恢复目标 vs 成本", "单机备份 + 五项恢复核验", "LJ"]];
  rows.forEach(([a, b, who], i) => {
    const y = 1.5 + i * 0.78;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: M, y, w: 7.6, h: 0.66, fill: { color: "1D3A52" }, line: { color: "1D3A52" }, rectRadius: 0.08, objectName: "tradeoff-" + (i + 1) });
    text(s, [{ text: a + "   ", options: { bold: true, color: C.amber } }, { text: b, options: { color: C.white } }], { x: M + 0.25, y: y + 0.14, w: 6.4, h: 0.42, fontSize: 15 });
    text(s, who, { x: M + 6.75, y: y + 0.14, w: 0.7, h: 0.42, color: "AFC4D0", fontSize: 13, align: "right" });
  });
  text(s, [{ text: "局限", options: { bold: true, color: C.amber, fontSize: 17, breakLine: true } },
    { text: "临时限制为场景数据、普查不含日间人流；单机 SQLite，PostgreSQL、图数据库为设计论证；风险代理不是事故概率", options: { breakLine: true } },
    { text: " ", options: { breakLine: true, fontSize: 14 } },
    { text: "下一步", options: { bold: true, color: C.amber, fontSize: 17, breakLine: true } },
    { text: "PostgreSQL 上复现发布与查询实验 · 目标规模恢复演练 · 真实数据隐私评审" }],
  { x: 8.6, y: 1.5, w: 4.15, h: 3.9, color: C.white, fontSize: 14 });
  text(s, "SkyRoute v2 · 代码与证据：github.com/zoran-sid/Routeweave", { x: M, y: 6.6, w: 9, h: 0.35, color: "AFC4D0", fontSize: 12 });
  text(s, "谢谢", { x: W - M - 2, y: 6.45, w: 2, h: 0.6, color: C.white, fontSize: 24, bold: true, align: "right" });
}

const xmlAttr = (v) => v.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
const SHOW = (val) => `<c:showLegendKey val="0"/><c:showVal val="${val}"/><c:showCatName val="0"/><c:showSerName val="0"/>` +
  '<c:showPercent val="0"/><c:showBubbleSize val="0"/>';
function pointLabel(idx, fmt, pos) {
  return `<c:dLbl><c:idx val="${idx}"/><c:numFmt formatCode="${xmlAttr(fmt)}" sourceLinked="0"/>` +
    "<c:spPr><a:noFill/><a:ln><a:noFill/></a:ln></c:spPr><c:txPr><a:bodyPr/><a:lstStyle/><a:p><a:pPr>" +
    `<a:defRPr sz="1100" b="1"><a:solidFill><a:srgbClr val="${C.ink}"/></a:solidFill><a:latin typeface="${FONT}"/>` +
    `<a:ea typeface="${FONT}"/></a:defRPr></a:pPr><a:endParaRPr lang="zh-CN"/></a:p></c:txPr><c:dLblPos val="${pos}"/>${SHOW(1)}</c:dLbl>`;
}
// Replace each labelled series' data-label block with per-point labels; text wears the ink color, not the series color.
async function labelPoints(file) {
  const JSZip = require("jszip");
  const zip = await JSZip.loadAsync(fs.readFileSync(file));
  const used = new Set();
  for (const name of Object.keys(zip.files).filter((n) => /^ppt\/charts\/chart\d+\.xml$/.test(n))) {
    const xml = await zip.file(name).async("string");
    const pos = xml.includes("<c:lineChart>") ? "r" : "outEnd";
    const out = xml.replace(/<c:ser>[\s\S]*?<\/c:ser>/g, (ser) => {
      const series = (ser.match(/<c:tx>[\s\S]*?<c:v>([^<]*)<\/c:v>/) || [])[1];
      const spec = POINT_LABELS[series];
      if (!spec) return ser;
      used.add(series);
      const block = `<c:dLbls>${spec[0].map((i) => pointLabel(i, spec[1], pos)).join("")}${SHOW(0)}</c:dLbls>`;
      return /<c:dLbls>[\s\S]*?<\/c:dLbls>/.test(ser) ? ser.replace(/<c:dLbls>[\s\S]*?<\/c:dLbls>/, block) : ser.replace("<c:cat>", block + "<c:cat>");
    });
    zip.file(name, out);
  }
  const missing = Object.keys(POINT_LABELS).filter((k) => !used.has(k));
  if (missing.length) throw new Error("labelled series not found: " + missing.join(", "));
  fs.writeFileSync(file, await zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE" }));
}

pres.writeFile({ fileName: OUT }).then(async (f) => {
  await labelPoints(f);
  try { require("child_process").execFileSync("zip", ["-dq", f, "*/"]); } catch (e) { /* no folder entries */ }
  console.log("wrote " + f);
});
