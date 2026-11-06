# ZC 的工作记录

项目：SkyRoute。最后更新：2026-11-06（Asia/Hong_Kong）。

| 项目 | 当前状态 |
| --- | --- |
| 成员 | ZC，成员5 |
| 负责方向 | 三维航线算法与评估 |
| 展示安排 | PPT第7–8页，已提供两页可编辑PPT及讲稿 |
| 技术成果状态 | 模块可交付 |
| 集成状态 | 131项回归、7项审查、11项整链路及25项风险专项通过；报告与10页PPT已整合，YHT-05文档问题已分派 |

## v2 任务（2026-11-06 重组，待开始）

| 项目 | 内容 |
| --- | --- |
| v2 职责 | 技术选型、查询服务与性能评估；v2 整合与发布 |
| 报告章节 | 5、7.1、8 |
| PPT | 第7–8页 |
| 建议分支 | `zc/v2-tech-selection`，从 `develop` 创建，PR 到 `develop` |
| 交付位置 | `docs/modules/zc/v2/`：`section.md`、`slides.md`、`references.md` |

具体任务、依赖与验收见[任务安排](../team-tasks.md)第5–8节。以下 v1 记录保留为证据。

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
- 重新运行YHT42、LQ19、ZC24、ZQO31、LJ15，共131项单元测试；原问题审查7/7、整链路11/11、风险专项25/25通过。证据见[verification.json](../final/evidence/verification.json)及同目录三个完整JSON。
- 整合[报告正文](../final/report.md)、[13页Word](../final/SkyRoute-report.docx)、[10页PPT](../final/SkyRoute-presentation.pptx)、[讲稿](../final/slides.md)、[课程覆盖](../final/course-coverage.md)及[贡献依据](../final/contributions.md)。图、可编辑表格／图表和源码随交付保存。
- 内容处理：区分源五版与查询五版、YHT走廊预检与系统Q1、风险代理与概率、历史性能实验与本轮正确性检查。更新实例按实际JSON记录为等长绕行，未把路径变化写成距离增加。D* Lite、真实权限及跨机恢复按候选／部署设计说明。
- 发现YHT-05文档问题，已写入[分派清单](../integration/issues.md)。按用户边界，未改YHT/LQ/ZQO/LJ的模块文件及个人交接；ZC仅维护自身状态与共享整合材料。
- Word逐页渲染检查，PPT完成逐页检查、原生对象及结构验证。正式比例、身份、签字和课程平台上传由成员按通知处理，未代写认可。

后续成员提交修复时，先读全部交接及新提交，再同步受影响的整合材料与证据。YHT-05由YHT修订后复核；本轮已有技术结论以其明确测试范围使用。
