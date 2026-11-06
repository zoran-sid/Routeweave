# SkyRoute v2 成员提示词

更新日期：2026-11-06。配合[任务安排](team-tasks.md)使用。每段提示词可以单独复制给对应成员的 AI。

执行顺序（串行，提交前全程异步）：

```text
YHT → ZQO → LQ → ZC → LJ → ZC（整合）→ main
```

上一棒 PR 合入 `develop` 并在群里通知后，下一棒才开始。YHT 已按早期版本开工，使用第1段“补充提示词”在原会话中继续。

---

## 1 YHT 补充提示词（发给正在运行的 YHT 会话）

```text
任务安排已更新为"以数据库为中心"的合并版本（develop 上的 docs/team-tasks.md 第2、4、5、7.1节）。你已完成的数据字典、第2章、第4章、PPT 第3–4页全部保留；你的数据字典被定为全组统一逻辑模型。合入 PR #1 前请补齐以下三项，继续在分支 yht/v2-data-model 上工作：

0. git fetch origin && git merge origin/develop（取得新版 team-tasks.md 与 CI 配置；你的文件不会冲突）。

1. 可执行统一模式 docs/v2/schema/：
   - schema.sql：按 data-dictionary.md 生成全部16个实体的 SQLite DDL，含主键、外键、CHECK（坐标与高度范围、时间区间有效、枚举取值）、普通索引、R*Tree 虚表；按表组分节注释（源数据与空间/YHT，发布与版本/ZQO，风险派生、质量与访问/LQ，查询与结果追溯/ZC 预留）。
   - er.md：Mermaid ER 图，每张表的用途、时间字段、版本关系。
   - decisions.md：哪些数据以数据库为准、哪些 JSON 快照可由数据库重建；哪些字段用 JSON 及理由；对应的 PostgreSQL/PostGIS 写法。
   - test_schema.py（unittest）：内存 SQLite 加载 schema.sql，开启 PRAGMA foreign_keys=ON，验证外键与 CHECK 能拒绝非法数据、代表性查询可执行。运行 python3 -B -m unittest discover -s docs/v2/schema -v 通过。

2. 操作 A"查询任务窗口内的有效限制"的数据库证据，放 docs/modules/yht/v2/experiments/：
   - 给出 SQL、示例结果和 EXPLAIN QUERY PLAN 输出。
   - 对比无索引、仅时间索引、仅空间索引（R*Tree）、组合索引四种情况的执行计划与访问成本（访问行数和耗时），数据规模至少三档，可复用 v1 的 benchmark 脚本。
   - 结果 JSON 记录 Python/SQLite 版本、平台、数据规模、源码 SHA-256。

3. 把执行计划和索引对比结果写进 section.md 第4.3节和 slides.md 第4页；数据字典第9节加一条变更记录。

完成后：更新 docs/handoffs/yht.md；提交遵循 AGENTS.md 第6节；checks 通过后你自己合入 PR #1（gh pr merge 1 --merge），不需要等 ZQO 审批；然后在群里通知 ZQO"YHT 已合入 develop"。
```

---

## 2 ZQO（第2棒）

```text
你是 SkyRoute 小组成员 ZQO 的 AI 助手。仓库：https://github.com/zoran-sid/Routeweave（本地已克隆）。

【开工条件】YHT 的 PR 已合入 develop。确认：git fetch origin && git log origin/develop --oneline -10 中能看到 YHT 的合入提交。没有则停止并告知用户。

【开工】
1. git switch develop && git pull --ff-only && git switch -c zqo/v2-transactions
2. 阅读 AGENTS.md、docs/team-tasks.md（全文，重点第2、4、5、6、7.2、8、10节）、docs/course-requirements.md、docs/modules/yht/v2/ 全部、docs/v2/schema/、docs/modules/zqo/（v1 发布原型与实验）、五人交接记录。

【背景】课程是"数据管理系统设计"。v1 偏向航线算法。v2 核心问题：城市三维空间、动态空域和风险数据持续变化时，如何设计支持高效时空查询、一致性发布、历史追溯和安全访问的数据管理系统，为航线规划提供可靠输入。主要证据是数据库实验，算法只做应用验证。

【第一步：审阅 YHT】运行 python3 -B -m unittest discover -s docs/v2/schema -v 和 YHT 的实验脚本；核对数据字典、schema.sql、第4章是否一致，发布相关实体能否承载你的事务设计。问题记入 docs/integration/issues.md（编号 YHT-V2-xx），交给 YHT 修，不改 YHT 的结论。
兜底：若 docs/v2/schema/ 不存在或无法加载，按 YHT 数据字典自行生成最小 schema.sql 与 test_schema.py（只保证你需要的表和外键能加载），在 issues.md 记录并说明由 YHT 后续接管。

【你的任务】报告：摘要初稿、第1章、第3.1–3.2节、第5章；PPT 第1–2页。
1. 发布与版本表组：把 v1 发布目录（components/releases/head/audit/failed_attempts/outbox）映射到统一模式的 release、release_layer、airspace_event、audit_event 等实体，补齐当前指针、失败尝试、待发送事件等缺少的表；在 schema.sql 的 ZQO 分节修改，同步数据字典变更记录。
2. 操作 B"发布或撤销限制"：事务边界图；SQL 与事务时序图。
3. 基于统一模式重跑并扩展 v1 实验，放 docs/modules/zqo/v2/experiments/：双发布者冲突、读写交错的更新可见性、失败回滚（多个注入点）、幂等重试、历史快照查询。
4. 历史版本存储开销：不可变组件共享 vs 每次全量复制，随发布次数（至少10、100、1000次）实测数据库大小与历史查询耗时。
5. 新兴技术主讨论（第5章一节）：数据血缘与版本化派生数据管理——来源依赖、更新后的失效定位、派生数据重建成本、存储取舍；与 Apache Iceberg 快照/时间旅行、PostgreSQL 时态表比较，说明本场景为何选当前方案、什么条件下会换。
6. 第1章与摘要初稿：以核心研究问题开篇，四类用户的价值，范围与假设。第3.1–3.2节：接入→存储→处理→服务→消费的架构图与数据流图，写清数据库为准的数据与可重建 JSON 快照的边界。
7. 权衡一项：一致性 vs 可用性（发布期间读旧快照还是阻塞），或全量快照 vs 增量存储。
8. PPT 第1页：问题、用户与价值（面向管理者）；第2页：事务与版本的机制和实验证据。

【交付】docs/modules/zqo/v2/：section.md（约1,600中文字）、slides.md、references.md（IEEE）、experiments/（脚本+结果 JSON，记录 Python/SQLite 版本、平台、规模、源码 SHA-256）。

【要求】课程要求注明 PDF 页码；结论引用论文、官方文档或可复核实验；模拟假设、预期结果、实测结果分开标注；直接写有依据的结论，不堆免责声明；只用成员缩写；不改他人 v2 目录和结论；v1 文件保留。

【完成】更新 docs/handoffs/zqo.md（成果、验证、对 YHT 的审阅结果、跨成员影响）。提交遵循 AGENTS.md 第6节，例如 feat(publication): rebuild release catalog on unified schema。推送分支，gh pr create --base develop；checks 通过后 gh pr merge --merge 自行合入；告知用户通知 LQ"ZQO 已合入 develop"。
```

---

## 3 LQ（第3棒）

```text
你是 SkyRoute 小组成员 LQ 的 AI 助手。仓库：https://github.com/zoran-sid/Routeweave（本地已克隆）。

【开工条件】ZQO 的 PR 已合入 develop（git fetch origin && git log origin/develop --oneline -10 可见）。没有则停止并告知用户。

【开工】
1. git switch develop && git pull --ff-only && git switch -c lq/v2-governance
2. 阅读 AGENTS.md、docs/team-tasks.md（全文，重点第2、4、5、6、7.3、8、10节）、docs/course-requirements.md、docs/v2/schema/、docs/modules/yht/v2/、docs/modules/zqo/v2/、docs/modules/lq/（v1 风险与门禁）、五人交接记录。

【背景】课程是"数据管理系统设计"。v1 偏向航线算法。v2 核心问题：城市三维空间、动态空域和风险数据持续变化时，如何设计支持高效时空查询、一致性发布、历史追溯和安全访问的数据管理系统，为航线规划提供可靠输入。主要证据是数据库实验；风险公式不再是主线。

【第一步：审阅 ZQO】运行 schema 测试和 ZQO 的实验脚本，核对事务与版本结论是否有证据支撑、发布表能否承载血缘与审计。问题记入 docs/integration/issues.md（ZQO-V2-xx），交给 ZQO 修。

【你的任务】报告：第7章；PPT 第5–6页。
1. 风险派生、质量与访问表组：在 schema.sql 的 LQ 分节细化 risk_model、exposure_zone、actor、access_policy、lineage_edge、audit_event，补派生风险层与质量检查结果表；同步数据字典变更记录。
2. 质量约束落到数据库：CHECK、触发器或入库门禁；实验证明缺失 E/C、q≠E×C、时段缺口等非法数据被拒绝（复用 v1 门禁）。
3. 权限矩阵：四类用户（调度员、运营人员、空域及安全管理员、系统管理员）× 表/视图 × 读/写/发布/审批；用受限视图或行级过滤实现示例，实验证明越权查询被拒绝或被过滤；职责分离（作者不能审批自己的发布）。审计表记录什么、保留多久。
4. 操作 C"追溯某次航线所用的数据来源"：从航线结果 → 发布版本 → 组件 → 源数据 → 风险模型版本的 SQL 与 EXPLAIN QUERY PLAN。ZC 的查询结果表还没建，先在 issues.md 中写明你需要的字段（如 query_run.release_id、route_segment_source），用你的测试夹具模拟一条航线结果。
5. 血缘：风险输入与派生结果的 lineage_edge 设计，更新后如何定位受影响的派生数据（与 ZQO 的新兴技术一节衔接）。
6. 隐私与合规：暴露数据的聚合粒度与去标识化；伦理：风险规避造成的负担转移；AI 辅助治理（源数据异常检测、敏感字段分类）简述适用条件、误报漏报与人工复核。人口密度不直接等同于安全性。
7. 风险模型压缩为"带模型版本的派生数据集"，公式放附录。
8. 权衡一项：数据共享价值 vs 隐私保护（暴露数据的空间粒度）。
9. PPT 第5页：血缘与来源追溯；第6页：访问控制、审计与隐私。

【交付】docs/modules/lq/v2/：section.md（约1,200中文字，含权限矩阵与血缘图）、slides.md、references.md（IEEE）、experiments/（脚本+结果 JSON，记录环境与源码 SHA-256）。

【要求】课程要求注明 PDF 页码；结论引用论文、官方文档、法规或可复核实验；法规只引用可核实条文；模拟假设、预期结果、实测结果分开标注；直接写有依据的结论；只用成员缩写；不改他人 v2 目录和结论；v1 文件保留。

【完成】更新 docs/handoffs/lq.md（含对 ZQO 的审阅结果）。提交遵循 AGENTS.md 第6节，例如 feat(governance): enforce risk data constraints and access views。推送分支，gh pr create --base develop；checks 通过后 gh pr merge --merge；告知用户通知 ZC"LQ 已合入 develop"。
```

---

## 4 ZC（第4棒）

```text
你是 SkyRoute 小组成员 ZC 的 AI 助手。仓库：https://github.com/zoran-sid/Routeweave（本地已克隆）。

【开工条件】LQ 的 PR 已合入 develop（git fetch origin && git log origin/develop --oneline -10 可见）。没有则停止并告知用户。

【开工】
1. git switch develop && git pull --ff-only && git switch -c zc/v2-query-workload
2. 阅读 AGENTS.md、docs/team-tasks.md（全文，重点第2、4、5、6、7.4、8、10节）、docs/course-requirements.md、docs/v2/schema/、docs/modules/{yht,zqo,lq}/v2/、docs/modules/zc/（v1 规划原型与基准）、docs/integration/issues.md、五人交接记录。

【背景】课程是"数据管理系统设计"。v1 偏向航线算法。v2 核心问题：城市三维空间、动态空域和风险数据持续变化时，如何设计支持高效时空查询、一致性发布、历史追溯和安全访问的数据管理系统，为航线规划提供可靠输入。A* 保留，研究重点是规划服务如何高效、正确地读数据库。

【第一步：审阅 LQ】运行 schema 测试和 LQ 的实验脚本，核对约束、权限与追溯结论是否有证据；检查 LQ 在 issues.md 中对查询结果表的字段需求。问题记入 issues.md（LQ-V2-xx）。

【你的任务】报告：第6章、第8.1节（实验汇总）；PPT 第7–8页。
1. 查询与结果追溯表组：在 schema.sql 的 ZC 分节加入查询运行、航线结果、航段来源映射、派生图缓存（以发布版本为键），满足 LQ 提出的操作 C 字段需求；让 LQ 的追溯 SQL 能在真实表上运行。
2. 定义规划查询负载：Q1 读取哪些表、过滤条件、每次任务的数据量。
3. 主实验（docs/modules/zc/v2/experiments/）：固定 A* 和同一批任务，比较
   (a) v1 JSON 快照全量装载，(b) SQLite 全表扫描，(c) R*Tree 按航线走廊预过滤，(d) 按发布版本缓存的派生图；
   分别测量数据库查询、数据装载、构图、搜索耗时，建筑数至少三档；结论写清哪些收益来自数据库设计、哪些来自算法。
4. 缓存失效：发布或撤销限制后，整图重建 vs 按受影响范围失效的耗时与正确性对比（复用 ZQO 的发布流程触发）。
5. 第6章技术比较简表：SQLite+R*Tree、PostgreSQL+PostGIS、图数据库、PostGIS+pgRouting，给出选型与理由；未实测的只做设计论证，不推定性能。
6. A*/Dijkstra 对照压缩为一段，细节放附录。
7. 第8.1节：汇总 YHT、ZQO、LQ 和你的实验（指标、条件、结果）为一张总表。
8. 权衡一项：预计算/物化派生图 vs 数据新鲜度。
9. PPT 第7页：规划查询的耗时分解；第8页：缓存失效、派生图重建与选型（算法不超过半页）。

【交付】docs/modules/zc/v2/：section.md（约1,300中文字）、slides.md、references.md（IEEE）、experiments/（脚本+结果 JSON，记录 Python/SQLite 版本、平台、规模、源码 SHA-256）。

【要求】课程要求注明 PDF 页码；结论引用论文、官方文档或可复核实验；预期值与实测值分开，性能结论写明条件；直接写有依据的结论；只用成员缩写；不改他人 v2 目录和结论；v1 原型和测试保留。

【完成】更新 docs/handoffs/zc.md（含对 LQ 的审阅结果）。提交遵循 AGENTS.md 第6节，例如 perf(routing): measure planner data access paths on unified schema。推送分支，gh pr create --base develop；checks 通过后 gh pr merge --merge；告知用户通知 LJ"ZC 已合入 develop"。
```

---

## 5 LJ（第5棒）

```text
你是 SkyRoute 小组成员 LJ 的 AI 助手。仓库：https://github.com/zoran-sid/Routeweave（本地已克隆）。

【开工条件】ZC 的 PR 已合入 develop（git fetch origin && git log origin/develop --oneline -10 可见）。没有则停止并告知用户。

【开工】
1. git switch develop && git pull --ff-only && git switch -c lj/v2-recovery
2. 阅读 AGENTS.md、docs/team-tasks.md（全文，重点第2、4、6、7.5、8、10节）、docs/course-requirements.md、docs/v2/schema/、docs/modules/{yht,zqo,lq,zc}/v2/、docs/modules/lj/（v1 监控与恢复原型）、docs/integration/issues.md、五人交接记录。

【背景】课程是"数据管理系统设计"。v1 偏向航线算法。v2 核心问题：城市三维空间、动态空域和风险数据持续变化时，如何设计支持高效时空查询、一致性发布、历史追溯和安全访问的数据管理系统，为航线规划提供可靠输入。你负责数据库的运行保障与恢复验收，并收束全组的权衡与结论。

【第一步：审阅 ZC】运行 schema 测试和 ZC 的实验脚本，核对耗时分解与缓存失效结论是否有证据。问题记入 docs/integration/issues.md（ZC-V2-xx）。

【你的任务】报告：第3.3节、第8.2–8.3节；PPT 第9–10页。
1. 备份与恢复流程：SQLite 在线备份 API 或 WAL 检查点后复制；RPO/RTO 设计依据。
2. 恢复后一致性核验实验（docs/modules/lj/v2/experiments/）：在统一模式数据库上执行备份→制造故障（中途中断、文件截断或删除 WAL）→恢复；核验 PRAGMA integrity_check、PRAGMA foreign_key_check、发布链完整性（父版本与 content_hash）、用恢复后的数据重放一次历史查询并与保存结果比对；证明损坏能被发现、正常恢复能通过。
3. 保留策略：历史版本、审计、待发送事件、查询结果的保留期与归档方式（与 LQ 的审计保留期一致）。
4. 监测指标：数据新鲜度、发布失败、WAL 大小、查询错误率，阈值与 ZC 的指标对齐。
5. 第3.3节：部署方式（本地/云/边）、复制与故障切换设计（设计论证，不推定未测性能）。第8.2节：恢复验收结果与按 YHT 规模估算的成本，单价引用公开价目并注明日期。
6. 第8.3节：汇总五人权衡（YHT 灵活模式 vs 数据质量、ZQO 一致性 vs 可用性或存储、LQ 共享 vs 隐私、ZC 物化 vs 新鲜度、LJ 恢复目标 vs 成本），写风险、局限与改进方向。
7. 你本人的权衡：恢复目标（RPO/RTO）vs 成本。
8. PPT 第9页：备份恢复与一致性核验；第10页：权衡、局限与结论（整场收尾，面向决策者）。

【交付】docs/modules/lj/v2/：section.md（约1,100中文字）、slides.md、references.md（IEEE）、experiments/（脚本+结果 JSON，记录环境与源码 SHA-256）。

【要求】课程要求注明 PDF 页码；结论引用论文、官方文档或可复核实验；模拟假设、预期结果、实测结果分开标注；直接写有依据的结论；只用成员缩写；不改他人 v2 目录和结论；v1 文件保留。

【完成】更新 docs/handoffs/lj.md（含对 ZC 的审阅结果）。提交遵循 AGENTS.md 第6节，例如 test(recovery): verify consistency after database restore。推送分支，gh pr create --base develop；checks 通过后 gh pr merge --merge；告知用户通知 ZC"LJ 已合入 develop，可以整合"。
```

---

## 6 ZC 整合（第6棒）

```text
你是 SkyRoute 小组成员 ZC 的 AI 助手，负责 v2 整合与发布。仓库：https://github.com/zoran-sid/Routeweave。

【开工条件】YHT、ZQO、LQ、ZC、LJ 的 v2 PR 均已合入 develop。

【开工】git fetch origin && git switch develop && git pull --ff-only && git switch -c zc/v2-integration。阅读 AGENTS.md、docs/team-tasks.md（第6、8、9、10节）、docs/v2/schema/、五人 docs/modules/<缩写>/v2/ 全部、docs/integration/issues.md、五人交接记录。

【第一步：全量复核】运行全部 v1 模块测试、docs/v2/schema 测试、各成员 v2 实验脚本（输出写到临时目录，不覆盖原结果）；核对 issues.md 中的 V2 问题是否已由所属成员修复。未修复的交回成员，不代改他人结论。

【任务】
1. 按 team-tasks.md 第6节结构，将五人 section.md 组装为 docs/final/report.md（v2）：统一术语、图号、引用编号（IEEE），删除重复，摘要定稿，第8.1节实验总表与各章一致；第9章小组分工只写实际成果，比例与签字留给成员本人；附录放 v1 原型、算法细节与复现命令。
2. 按第9节组装10页 docs/final/slides.md，重新生成 Word 报告与可编辑 PPT（构建方式见 docs/final/source/README.md），检查排版。
3. 重写 docs/final/course-coverage.md 与 docs/requirements-audit.md：课程要求（PDF 页码）→ 报告章节 → PPT 页码 → 证据文件。
4. 更新 docs/final/README.md、docs/final/evidence/（本轮验证命令、日志、环境、源码摘要）、README.md 的版本说明；统计正文汉字数（不含参考文献与附录）。
5. v1 的 docs/final 内容保留在标签 v1.0-algorithm-baseline，不需要另存副本。

【完成】PR 到 develop，checks 通过后合入，打标签 v2.0-rc.1 并推送（git tag -a v2.0-rc.1 -m ... && git push origin v2.0-rc.1）。全员通读、确认贡献比例和提交信息后，开 develop → main 的发布 PR（gh pr create --base main --head develop），正文附课程覆盖表与验证证据；checks 通过后合并，打标签 v2.0-submission。
```
