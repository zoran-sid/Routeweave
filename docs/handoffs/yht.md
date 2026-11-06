# YHT 的工作记录

项目：SkyRoute。最后更新：2026-11-06（Asia/Shanghai）。

| 项目 | 当前状态 |
| --- | --- |
| 成员 | YHT，成员4 |
| 负责方向 | 场景需求与三维数据建模 |
| 展示安排 | PPT 第3–4页，已提供两页可编辑PPT及讲稿 |
| 技术成果状态 | 模块可交付 |
| 集成状态 | YHT-01/02/03/04 已修复并通过 owner 审计 / LQ 专项复核，待复核；与 ZC/LQ 导出接口已实测，ZQO 发布与 LJ 验收的整链路联调待集成方推进 |

## 已完成成果

- [模块入口](../modules/yht/README.md)：需求、数据模型、存储选型、评估、PPT 与复现方式。
- [设计](../modules/yht/design.md)：用户与 Q1/Q2 需求、合成片区、坐标/高度/时间口径、五层数据模型、对象约束、版本与质量规则、YHT-D1..D12。
- [存储与索引](../modules/yht/storage.md)：PostGIS/MongoDB/Neo4j/Elasticsearch/SQLite R\*Tree/网格的候选比较，SQLite 三维 R\*Tree 实现，2,400 栋基准与生产演进路径。
- [治理](../modules/yht/governance.md)：数据分类、生命周期、来源与血缘、质量门禁、隐私伦理、访问控制、保留与缺口。
- [评估](../modules/yht/evaluation.md)：42 项测试、200 条查询的三规模基准、缓存/WAL 小实验、12 类故障注入、更新实例、ZC/LQ 导出实测、YHT-01/02/03/04 最终集成回归与未执行评估。
- [集成](../modules/yht/integration.md)：字段映射、五版与清单、Q1/Q2 接口、ZC/LQ 导出约束、ZQO/LJ 接入检查及发布走查。
- [两页PPT](../modules/yht/slides/yht-data-model.pptx)与[讲稿](../modules/yht/slides/notes.md)：对应第3–4页。
- [原型](../modules/yht/prototype/)（`yht_model.py`、`query.py`、`store.py`、`cache.py`、`quality.py`、`export_zc.py`、`export_lq.py`、`evaluate.py`、`test_yht.py`）与[原始结果](../modules/yht/results/)；原生合成场景样例见[scene.json](../modules/yht/results/scene.json)。
- [参考文献](../modules/yht/references.md)。

## 已执行验证

在仓库根目录运行：

    python3 -m unittest discover -s docs/modules/yht/prototype -v
    python3 docs/modules/yht/prototype/evaluate.py
    python3 -B docs/integration/audit.py --owner YHT

42 项测试通过。200/800/2,400 栋三个规模、120 条 Q1 + 80 条 Q2 上，索引与全扫的状态/命中完全一致；Q2 中位耗时 0.985/3.680/10.390 ms 降至 0.0767/0.0768/0.0794 ms，Q1 为 7.690/39.540/122.936 ms 降至 0.148/0.159/0.155 ms。12 类故障全部检出；缺高度、覆盖不完整、版本不一致均返回 unknown。查询缓存热命中中位 17.45 µs（冷 617.85 µs），版本换代后 1 次 miss；SQLite WAL 下读事务可在写事务期间继续读。ZC 导出通过 preflight，A\* 得到 612.5483 m、61.2548 s 的可行航线，同快照直线航段被 B-001 阻断。LQ 适配器把 6 个分区编译成 profile 后，仍得到同一条 612.5483 m 航线、risk_proxy 4.2120；q 最大 0.82，未触发 0.9 硬阈值。最终集成回归 `python3 -B docs/integration/audit.py --owner YHT` 三项通过：未知风险在 ZC/LQ 两个导出入口均被 `ValueError` 拒绝；不完整覆盖和非平地被拒绝；58 m + 5 m 半径对 60 m 限高返回 blocked，与 ZC 一致。YHT-04 由 `python3 -B docs/modules/lq/prototype/review_integration.py` 覆盖，25/25 通过：单独缺 `E` 或 `C`、保留旧 `q` 时，直接 ZC 导出也抛 `ValueError`；`E/C/q` 全部存在但不满足 `q=E×C` 时同样拒绝。以上均为单机合成数据结果，未测真实数据、PostGIS 实库和生产级并发。

PPT 共 2 页，含可编辑表格和图表，逐页渲染检查；未代填成员认可、贡献比例或课程签字。

## 本轮协作记录

- 已检查提交：`c357ac3a032c896eccf1b4b19fc953facf73ad91`（LQ 新增 YHT-04 复核记录，2026-11-06；修复前基线）。五个模块均已交付；已读 AGENTS.md、课程要求、五人交接、`docs/integration/README.md`、`issues.md`、`audit.py` 与 LQ 的 `review_integration.py`。
- 最终集成修复（`81bd270dd004e7e26e52cea3b95c58ea75b45ba7`，已提交到 `main`，待复核）：YHT-01 未知 `q`/`E`/`C` 不再被丢弃，ZC/LQ 两个导出入口分别抛 `ValueError`；YHT-02 不完整覆盖、非平地、非零基面直接拒绝，不改写质量字段；YHT-03 Q1 限高改为“最高点 + 垂直半径 > ceiling_m”，接触边界不阻断，与 ZC 的 `buffer_m` 语义一致。证据见 [评估](../modules/yht/evaluation.md) 第 2.1 节与 `docs/integration/issues.md`。
- YHT-04 修复（本轮，提交 `1862ab44ca094bc493fab6fc7ce0cd6f51f2e2db`）：`export_snapshot` 新增 `require_verifiable_exposure`，每个分区的 `E`/`C`/`q` 必须为 [0,1] 内有限数且 `q=E×C`；单独缺 E/C、保留旧 q 或三者不一致时抛 `ValueError`，不再让 ZC 把旧 q 当已知风险。LQ 入口保持独立校验。证据见评估第 2.1 节与 LQ 的 `review_integration.py`（YHT 本地运行 25/25）。
- 已复用：`starter-v0`、五类版本键、Q1/Q2 状态语义、ZC 的 snapshot 与 preflight 约束、LQ 的 `compile_profiles`/`q=E×C` 口径、课程报告与 PPT 要求。
- 技术决定：YHT-D1..D12 见[决策表](../modules/yht/design.md#9-设计决策)，覆盖内部格式、几何表示、版本/质量、查询语义、覆盖/地形、存储索引与 ZC/LQ 导出。
- 跨模块影响：向 ZC 提供可直接加载的快照与 `source_release`；向 LQ 提供带 `E`/`C` 的暴露 profile；向 ZQO 提供五版/清单字段；向 LJ 提供 `status/reasons/versions/coverage` 审计字段。未修改其他成员的工作记录和共同口径。
- 未做：真实数据接入、地形起伏、PostGIS 实库对照、生产级并发/跨进程缓存一致性、LQ 最终风险模型替换。均列入评估“未执行”表。

## 可供其他成员使用

- ZC：`results/zc-export.json` 可直接绑定；L 形建筑取包围盒，搜索域外建筑不导出；未知 `q`、单独缺 `E`/`C`、`q != E×C`、覆盖不完整、非平地输入会抛 `ValueError`，调用方应修复源发布而不是当作背景。
- LQ：`results/lq-export.json` 含 6 个 profile（`box/periods/E/C`）和 LQ 编译后的规划结果；`q=E×C` 是暴露代理，不是事故概率；缺 `E`/`C`/`q` 或 `q != E×C` 时导出抛 `ValueError`，不会跳过分区变成背景风险。
- ZQO：`versions/manifest` 是内容身份，不是签名；发布审批和清单原子切换需在 ZQO 侧实现。
- LJ：Q1/Q2 返回 `status/reasons/versions/coverage/candidates/checked`，可作验收与审计输入。

任务依据：[项目说明](../project-brief.md)、[共同场景约定](../scenario-contract.md)、[五人分工](../team-tasks.md)、[课程要求全文](../course-requirements.md)、[异步协作](../agent-collaboration.md)、[AI 协作指南](../../AGENTS.md)。
