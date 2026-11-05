# ZC 的工作记录

项目：SkyRoute。最后更新：2026-11-05（Asia/Hong_Kong）。

| 项目 | 当前状态 |
| --- | --- |
| 成员 | ZC，成员5 |
| 负责方向 | 三维航线算法与评估 |
| 展示安排 | PPT第7–8页，已提供两页可编辑PPT及讲稿 |
| 技术成果状态 | 模块可交付 |
| 集成状态 | 共同语义已核对，其他模块实际成果待接入检查 |

## 已完成成果

- [模块入口](../modules/zc/README.md)：报告、原型、数据、PPT与复现方式。
- [算法与数据访问设计](../modules/zc/design.md)：三维26邻居网格、完整航段与缓冲检查、Dijkstra/3D A*、代价和一致启发式证明、伪代码、图投影访问、动态重规划与D* Lite适用性。
- [评估](../modules/zc/evaluation.md)：12个实际运行的合成情境、21项正确性测试、风险权重取舍、更新实例及未执行实验计划。
- [集成说明](../modules/zc/integration.md)：Q1/Q2字段、五类版本、缓存与更新规则、YHT/LQ/ZQO/LJ接入位置及判据。
- [两页PPT](../modules/zc/slides/zc-routing-evaluation.pptx)与[展示文字和讲稿](../modules/zc/slides/notes.md)：可直接整合到第7–8页。
- [原型](../modules/zc/prototype/planner.py)、[场景](../modules/zc/prototype/scenario.json)、[原始结果](../modules/zc/results/benchmark.json)和[参考文献](../modules/zc/references.md)。

## 已执行验证

运行仓库根目录命令：

    python3 -m unittest discover -s docs/modules/zc/prototype -v
    python3 docs/modules/zc/prototype/evaluate.py

21项测试通过。12个情境中两种算法状态一致，所有可行结果的目标代价差小于1e-9。建筑无热点场景：同为116.57米，Dijkstra扩展699节点，A*扩展72节点。热点场景A*的λ从0改为8时，距离116.57米增至133.14米，风险代理0.5021降至0.0666。结果是明确模型下的合成程序运行，真实风险、数据库性能与D* Lite性能尚未测量。

PPT共2页，已完成内容、可编辑表格／图表、文件结构与逐页渲染检查。交付未代填成员认可、贡献百分比或课程签字。

## 本轮协作记录

- 已检查提交：`bb164bb83984563816005317a4626739be078bca`，读取课程要求、共同约定、协作规则和五人的交接。
- 已复用：`starter-v0`、五类版本字段、三种Q1状态、Q1/Q2分工及整体评估要求。
- 其他模块状态：检查基线中均无技术稿，因此采用本目录内的最小完整合成替代；没有声称已完成实际跨模块集成。
- 技术决定：ZC-D1网格、ZC-D2时间窗、ZC-D3模拟风险、ZC-D4搜索、ZC-D5图投影、ZC-D6重规划，详见[决策表](../modules/zc/design.md#7-技术决策记录)。
- 共用文档影响：仅同步ZC成果入口及状态；其他成员的分工、记录和共同场景语义保持原口径。

## 可供其他成员使用

YHT可复用几何反例和规划访问需求；LQ可替换风险输入与聚合并核查非负可加条件；ZQO可使用版本绑定和更新前后输入输出；LJ可复用异常状态、预算与重规划验收。具体接口与接入检查见[集成说明](../modules/zc/integration.md)。

后续读取其他模块新提交后，完成实际字段映射及相关情境复测，记录检查的提交与结果。模块当前交付完整，剩余事项属于跨模块接入和扩大实验。
