# ZC 的工作记录

项目：SkyRoute。最后更新：2026-11-07（Asia/Hong_Kong）。

| 项目 | 当前状态 |
| --- | --- |
| 成员 | ZC，成员5 |
| 负责方向 | 三维航线算法与评估 |
| 展示安排 | PPT第7–8页，已提供两页可编辑PPT及讲稿 |
| 技术成果状态 | 模块可交付 |
| 集成状态 | 131项回归、7项审查、11项整链路及25项风险专项通过；报告与10页PPT已整合，YHT-05文档问题已分派 |

## v2 任务（第4棒，2026-11-07 完成）

| 项目 | 内容 |
| --- | --- |
| v2 数据库重点 | 面向规划的查询负载与性能；v2 整合与发布（第6棒，另行进行） |
| 报告章节 | 6、8.1、附录 A（第9章与整合在第6棒完成） |
| PPT | 第7–8页 |
| 开工基线 | `ca2bf58`：YHT PR #1、ZQO PR #4、LQ PR #6 已合入 `develop` |
| 分支 | `zc/v2-query-workload` |
| 成果入口 | [ZC v2](../modules/zc/v2/README.md) |

### 审阅上一棒（LQ）

复跑统一模式45项、LQ 18项测试与 `run.py`、ZQO `run.py --counts 10`、`review_zqo.py`，并写 [12项独立探针](../modules/zc/v2/experiments/results/lq-review.json)：

- 11项通过：LQ-V2-01 已修复（已批准模型的参数更新与删除被拒）；封存的派生值与数据集不可改写或回退；作者自审被拒；时段缺口无法封存；固定端点与 authorizer 都拒绝原表与内部 `resolved_feature` 视图；调度员读不到暴露明细。我原先怀疑 authorizer 放行 `resolved_feature`，探针显示外层查询对视图列的读取被拒，该控制成立。
- 1项不通过，记为 **LQ-V2-02**：LQ 的 `op_c.sql` 要求查询窗口等于数据集窗口（发布有效期一年），规划任务是10分钟窗口，同一条航线 LQ 版追溯0行、ZC 正式版2行。正式表与 `docs/v2/schema/op_c.sql` 已采用“任务窗口落在数据集窗口内”，LQ 版由 LQ 确认或对齐。
- ZQO-V2-01 仍未修复：`review_zqo.py` 退出码1，空上游版本与空编译器版本仍可发布。YHT-V2-05/06 的修复在 PR #5，尚未合入 `develop`。

### 已完成

- 统一模式 ZC 分节：`query_run`、`route_result`、`route_segment_source`、`route_graph_cache`，12个触发器校验发布、窗口、角色、新鲜度、数据集与缓存父子关系，结果表只追加；[操作 C 正式版](../v2/schema/op_c.sql)；ER 与决定 ZC-DV2 同步。
- [规划服务适配](../modules/zc/v2/experiments/planner_io.py)：读事务固定发布、经组件解析物理 owner、绑定覆盖任务窗口的封存数据集；四种取数路径；派生图构建、修补与搜索；结果写入。v1 规划器未修改。
- [取数路径实验](../modules/zc/v2/experiments/results/access_paths.json)：200/2,400/10,000 栋各12任务。R*Tree 取数中位数 0.04–0.17 ms，JSON 全量 1.4–33.6 ms，SQL 全量 0.54–14.5 ms；v1 A* 搜索 22–45 ms；派生图构建 49–129 ms、命中 0.31–0.58 ms。输入摘要、算法结果、Dijkstra 代价与航段追溯 36/36 一致。
- [缓存失效实验](../modules/zc/v2/experiments/results/invalidation.json)：2,400 栋、24 张图、两次真实发布。按变更沿用/修补比全部重建快 6.9× 与 16.2×，48 张图与重建结果0处不一致，旧发布历史查询 24/24 命中。
- [第6章、第8.1节与附录 A](../modules/zc/v2/section.md)、[第7–8页](../modules/zc/v2/slides.md)、[引用](../modules/zc/v2/references.md)。

### 验证

`python3 -B -m unittest discover -s docs/v2/schema`：54项通过（含 ZC 9项、ZQO 与 LQ 回归）；五个 v1 模块测试、`audit.py`、`five_module.py`、`review_integration.py`、LQ 与 ZQO v2 实验均通过。环境：Python 3.15.0、SQLite 3.54.1、macOS arm64。

### 跨成员影响

- **LJ（第5棒）**：第8.1节给出规划查询指标与建议告警；备份恢复须同时核验 ZC 四张表的外键与只追加约束；`route_graph_cache` 图本体在内存中，恢复后按发布重建。
- **LQ**：LQ-V2-02 待确认；正式结果表已满足 ZC-V2-C01 字段合同。
- **ZQO**：查询适配按 S-04 解析 owner；缓存沿用以 `airspace_event` 为变更来源，依赖发布事务为每个改动的限制写事件。

## v2 第6棒：整合（2026-11-07）

- **开工检查**：YHT PR #1/#5、ZQO PR #4、LQ PR #6、ZC PR #7 已在 `develop`。LJ 的 PR #8 以 `main` 为目标，我未核对目标分支即合并，`main` 一度包含未完成的 v2；经用户确认以 `--force-with-lease` 恢复到 `5d4034b` 并恢复分支保护，LJ 成果经 PR #9 合入 `develop`，CI 增加发往 `main` 的来源检查（INT-V2-01）。
- **全量复核**：新增 [`v2_verify.py`](../integration/v2_verify.py)，20/20 组命令符合预期，231 项测试通过；LJ 恢复实验在 macOS 复现。修复本人 ZC-V2-02（UTF-8 读取、连接关闭），并对 ZQO `catalog.initialize()` 做一行 UTF-8 兼容修订。LQ-V2-02、ZQO-V2-01 复跑仍未关闭，已记录。
- **报告**：LaTeX 源 [`report.tex`](../final/source/report/report.tex)，21 页 PDF，正文 9,833 个汉字；7 张图（TikZ / pgfplots，数据由成员结果 JSON 生成）、17 张表、26 条 IEEE 引用；Markdown 镜像自动生成，编号与 PDF 一致。逐页渲染检查版面，无溢出盒。
- **PPT**：[`build_slides.cjs`](../final/source/build_slides.cjs) 构建 12 页，原生图表与表格、每页讲稿；OOXML 校验通过，逐页渲染检查版面，图表数值从文件读回核对。PowerPoint 导出 PDF 因沙盒文件权限未完成，原生图表的最终外观请在 PowerPoint 中目视确认。
- **文档**：重写课程覆盖对照、要求对照、贡献依据与最终交付说明；v1 交付文件从 `docs/final/` 移除，历史记录中的链接改指向 `v1.0-algorithm-baseline` 标签。
- **下一步**：全员通读 `v2.0-rc.1`，确认贡献比例、封面信息与提交要求后，由 ZC 开 `develop` → `main` 的发布 PR 并打 `v2.0-submission`。

以下 v1 记录保留为证据。

## 已完成成果

- [模块入口](../modules/zc/README.md)：报告、原型、数据、PPT与复现方式。
- [算法与数据访问设计](../modules/zc/design.md)：三维26邻居网格、完整航段与缓冲检查、Dijkstra/3D A*、代价和一致启发式证明、伪代码、图投影访问、动态重规划与D* Lite适用性。
- [评估](../modules/zc/evaluation.md)：12个实际运行的合成情境、21项正确性测试、风险权重取舍、更新实例及未执行实验计划。
- [集成说明](../modules/zc/integration.md)：Q1/Q2字段、五类版本、缓存与更新规则、YHT/LQ/ZQO/LJ接入位置及判据。
- [两页PPT](../modules/zc/slides/zc-routing-evaluation.pptx)与[展示文字和讲稿](../modules/zc/slides/notes.md)：可直接整合到第7–8页。
- [原型](../modules/zc/prototype/planner.py)、[场景](../modules/zc/prototype/scenario.json)、[原始结果](../modules/zc/results/benchmark.json)和[参考文献](../modules/zc/references.md)。

## 首次交付验证（保留原实验基线）

运行仓库根目录命令：

    python3 -m unittest discover -s docs/modules/zc/prototype -v
    python3 docs/modules/zc/prototype/evaluate.py

21项测试通过。12个情境中两种算法状态一致，所有可行结果的目标代价差小于1e-9。建筑无热点场景：同为116.57米，Dijkstra扩展699节点，A*扩展72节点。热点场景A*的λ从0改为8时，距离116.57米增至133.14米，风险代理0.5021降至0.0666。结果是明确模型下的合成程序运行，真实风险、数据库性能与D* Lite性能尚未测量。

PPT共2页，已完成内容、可编辑表格／图表、文件结构与逐页渲染检查。交付未代填成员认可、贡献百分比或课程签字。

## 首次交付协作记录

- 已检查提交：`bb164bb83984563816005317a4626739be078bca`，读取课程要求、共同约定、协作规则和五人的交接。
- 已复用：`starter-v0`、五类版本字段、三种Q1状态、Q1/Q2分工及整体评估要求。
- 其他模块状态：检查基线中均无技术稿，因此采用本目录内的最小完整合成替代；没有声称已完成实际跨模块集成。
- 技术决定：ZC-D1网格、ZC-D2时间窗、ZC-D3模拟风险、ZC-D4搜索、ZC-D5图投影、ZC-D6重规划，详见[决策表](../modules/zc/design.md#7-技术决策记录)。
- 共用文档影响：仅同步ZC成果入口及状态；其他成员的分工、记录和共同场景语义保持原口径。

## 可供其他成员使用

YHT可复用几何反例和规划访问需求；LQ可替换风险输入与聚合并核查非负可加条件；ZQO可使用版本绑定和更新前后输入输出；LJ可复用异常状态、预算与重规划验收。具体接口与接入检查见[集成说明](../modules/zc/integration.md)。

## 2026-11-05：最终集成复核与输入校验修复

- 已读取共享主线 `cc20db8a6c3d2c92f030c8322cdf067ece249f91`、五人交接及实际模块代码。已检查 YHT 的导出、LQ 的风险编译、ZQO 的发布/Q2 和 LJ 的验收接口。
- 修复 `assess_segment` 对实际 `a/b` 端点的校验：错误维度、非数值、布尔值、NaN/Infinity 返回 `unknown / invalid_segment_endpoint`；超出搜索域返回 `unknown / segment_outside_search_domain`。结果保留版本和时间窗。
- 修复非字符串时间触发未处理异常的问题，由预检返回 `unknown`。新增 3 项回归测试，ZC 当前共 24 项通过。
- 分别运行五模块测试：YHT 31、LQ 19、ZC 24、ZQO 20、LJ 8，共 102 项通过；完整日志与源码摘要见 [回归结果](../integration/results/regression.json)。
- 新增审查实际复现 7 个其他成员问题，见 [分派与验收清单](../integration/issues.md) 及 [原始结果](../integration/results/audit.json)。按用户要求由所属成员修复，其代码与个人交接未修改。
- 本轮修复涉及输入校验，首次交付的 12 情境性能数据与 PPT 保留原始基线，没有把旧计时标记为本轮重测。最终集成状态为“问题已分派、整链路待验证”。

后续读取修复提交，复跑审查并参与 I-01 的字段映射及整链路复测；记录具体提交和实际结果后更新状态。

## 2026-11-06：最终材料整合与独立复核

- 已读取远程主线`2850d89cea68221bbe6a8cf1161bd1d3ab220c2c`、五名成员全部交接、课程要求及模块设计和证据。关键修复包括YHT `1862ab4`，LQ独立确认`2850d89`；历史提交标识保持原记录，当前验证另存源码摘要。
- 重新运行YHT42、LQ19、ZC24、ZQO31、LJ15，共131项单元测试；原问题审查7/7、整链路11/11、风险专项25/25通过。证据见[verification.json](https://github.com/zoran-sid/Routeweave/blob/v1.0-algorithm-baseline/docs/final/evidence/verification.json)及同目录三个完整JSON。
- 整合[报告正文](../final/report.md)、[13页Word](https://github.com/zoran-sid/Routeweave/blob/v1.0-algorithm-baseline/docs/final/SkyRoute-report.docx)、[10页PPT](../final/SkyRoute-presentation.pptx)、[讲稿](../final/slides.md)、[课程覆盖](../final/course-coverage.md)及[贡献依据](../final/contributions.md)。图、可编辑表格／图表和源码随交付保存。
- 内容处理：区分源五版与查询五版、YHT走廊预检与系统Q1、风险代理与概率、历史性能实验与本轮正确性检查。更新实例按实际JSON记录为等长绕行，未把路径变化写成距离增加。D* Lite、真实权限及跨机恢复按候选／部署设计说明。
- 发现YHT-05文档问题，已写入[分派清单](../integration/issues.md)。按用户边界，未改YHT/LQ/ZQO/LJ的模块文件及个人交接；ZC仅维护自身状态与共享整合材料。
- Word逐页渲染检查，PPT完成逐页检查、原生对象及结构验证。正式比例、身份、签字和课程平台上传由成员按通知处理，未代写认可。

后续成员提交修复时，先读全部交接及新提交，再同步受影响的整合材料与证据。YHT-05由YHT修订后复核；本轮已有技术结论以其明确测试范围使用。

## 2026-11-07：按用户指示修复全部未关闭问题并发布

- **LQ-V2-02**（LQ 名下）：LQ 追溯 SQL 改为数据集窗口包含任务窗口，`run.py` 与证据随之更新，探针 12/12。
- **ZQO-V2-01**（ZQO 名下）：发布服务拒绝空的上游版本值与编译器版本，新增回归，LQ 探针退出码 0。
- **ZC-V2-02**（本人，LJ 发现）：在关闭 UTF-8 模式的 ASCII 语言环境下全量复核 20/20 通过；同类问题在 v1 的 ZC `scenarios.py`、`evaluate.py`，ZQO、LQ 脚本与 `docs/integration/audit.py`、`five_module.py` 中一并修复。
- 修改分别记入 LQ、ZQO、LJ 的交接与问题清单，注明由 ZC 按用户指示完成、待各自复核。报告 §8.4 与相关说明同步更新后，由 ZC 将 `develop` 发布到 `main`（`v2.0-submission`）。
