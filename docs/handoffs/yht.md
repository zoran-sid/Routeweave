# YHT 的工作记录

项目：SkyRoute。最后更新：2026-11-06（Asia/Shanghai）。

| 项目 | 当前状态 |
| --- | --- |
| 成员 | YHT，成员4 |
| 负责方向 | 场景需求与三维数据建模 |
| 展示安排 | PPT 第3–4页，已提供两页可编辑PPT及讲稿 |
| 技术成果状态 | 模块可交付 |
| 集成状态 | YHT-01/02/03/04 已修复并通过 owner 审计 / LQ 专项复核；YHT-05 文档已修订待复核；与 ZC/LQ 导出接口已实测，ZQO 发布与 LJ 验收的整链路联调待集成方推进 |

## v2 任务（2026-11-06 开始）

| 项目 | 内容 |
| --- | --- |
| v2 职责 | 需求与数据分析、数据模型与数据库设计；数据字典供全体先行对齐 |
| 报告章节 | 2、4 |
| PPT | 第3–4页 |
| 分支 | `yht/v2-data-model`，从 `develop` 的 `4b60453` 创建 |
| 修复分支 | `yht/v2-immutability`，从 `develop` 的 `61fed41` 创建；YHT-V2-05/06 修复 `0748f2d`，模型文档 `4e501c3` |
| PR | [#1](https://github.com/zoran-sid/Routeweave/pull/1)（已合入）；本轮修复 [#5](https://github.com/zoran-sid/Routeweave/pull/5)，目标 `develop` |
| 交付位置 | `docs/modules/yht/v2/`：`data-dictionary.md`、`section.md`、`slides.md`、`references.md` |
| 当前状态 | 数据字典 `a35aeac`；第2、4章、两页讲稿与引用 `50f109c`，字段对齐与引用编号 `fcccbce`/`4aee9d2`，交接记录 `ec460b2`；均已推送；GitHub Actions `checks` 成功；YHT-V2-01—04 复核通过，YHT-V2-05/06 已修复并与 `develop` 合并验证通过，PR #5 待合入 |

具体任务、依赖与验收见[任务安排](../team-tasks.md)第5–8节。本轮已完成：

- 数据字典：三类数据、五层版本、16 个实体、单位/坐标、来源/更新频率、敏感级别、ER 关系、PostGIS/SQLite 索引映射、三年规模假设。
- 第2章：功能/非功能需求、三类数据规模与增长、生命周期、访问模式、利益相关者。
- 第4章：ER 图、关系模式与主外键/约束、Q1/Q2 典型 SQL、三维与时间索引、空间瓦片与时间分区、冷热分层、灵活模式 vs 数据质量权衡。
- 两页讲稿：第3页数据挑战，第4页模型与索引；引用 IEEE 格式。
- 验证：相对链接 0 处失效；`git diff --check` 通过；GitHub Actions `checks` 在 `ec460b2` 上成功；未改动其他成员 v2 目录；v1 成果保留。

影响：四名成员可据此对齐 `release_id`、五层版本、`feature_id`、三维几何、`effective`/`valid`、E/C/q 与来源字段；字段变更需在数据字典记录影响。

### 2026-11-06：AI 按 ZC 指示补齐 v2 合入前要求（记为 AI 的工作，不计入 ZC 工作量）

依据 [任务安排](../team-tasks.md) 第4、5、7.1节与第10节验收清单核对本分支 `44c897e`。数据字典、第2章、第4章与两页讲稿基本满足；缺可执行模式与操作 A 的执行计划证据，另有三处建模问题。用户要求直接修改提交，ZC 在本分支完成以下修订，**待 YHT 复核确认**，不代表 YHT 已认可：

- 新增 [`docs/v2/schema/`](../v2/schema/schema.sql)：按数据字典生成16张表的 SQLite DDL、39个触发器、三个 R*Tree、[ER 图](../v2/schema/er.md)、[设计决定](../v2/schema/decisions.md)、[操作 A SQL](../v2/schema/op_a.sql)、[测试夹具](../v2/schema/fixtures.py)与13项[测试](../v2/schema/test_schema.py)。
- 修正建模问题（决定 S-01—S-03）：瓦片与地形主键加 `release_id`；`airspace_restriction.state` 随发布固定；限高体禁止范围为 `ceiling_m` 以上。数据字典第3、7、9节同步。
- 新增 [操作 A 访问路径实验](../modules/yht/v2/experiments/op_a_index_comparison.py) 与 [结果](../modules/yht/v2/experiments/results/op_a_index_comparison.json)：六种路径结果一致；N=10,000、K=20 时四维 R*Tree 中位37.4 µs，全扫12,429 µs，发布 B-tree 878 µs。
- `section.md` 第4.2节、新增第4.3.1节；`slides.md` 第4页；`references.md` 新增 [17]–[21]。

验证：`python3 -B -m unittest discover -s docs/v2/schema -v` 13项通过；五个 v1 模块测试通过；实验命令 `python3 -B docs/modules/yht/v2/experiments/op_a_index_comparison.py`（约45秒）。

### 2026-11-07：修复 YHT-V2-05/06 并与 develop 合并验证

基线 `develop` `61fed41`，分支 `yht/v2-immutability`。

- YHT-V2-05：`feature_immutable_update` 同时检查 OLD/NEW 所属发布；新增 `building`、`airspace_restriction`、`exposure_zone`、`coverage_tile`、`terrain_surface`、`terrain_post` 的 INSERT draft-only 触发器，堵住“已发布 feature 后补子类型/地形/覆盖”的旁路。
- YHT-V2-06：新增 `source_provenance_usage` 视图，汇总所有非 draft 引用（含 feature、子类型来源列、空域/暴露/地形/覆盖/事件/模型及 `component_source` 的 owner 与映射发布）；`source_immutable_update/delete` 在引用后拒绝原地修改/删除，错误提示登记新 `source_id`。旧发布重开仍解析旧行，新来源可正常入库。
- 回归：`docs/v2/schema` 32 项测试通过；YHT v1 42 项测试通过；ZQO `run.py --counts 10` 14 项回归通过，4 条 YHT 探针（feature/building/terrain/source）全部 `rejected`；LQ-V2-01 仍为 LQ 的待修项。ZQO 的 `test_reference_metadata_drift_is_visible_failure` 改为 `test_reference_source_metadata_is_immutable`，只调整测试以匹配“写时拒绝”的新保证，不改 ZQO 发布实现。
- 修复提交 `0748f2d50129c2b301069d5c59ccc6d5a804bef6`（`fix(schema): close published-release write bypasses`）。

**与 develop 合并验证（2026-11-07）。** 将 `develop` `0f1dfcb`（含 LQ PR #6、ZC PR #7）合入修复分支。`schema.sql` 冲突按“LQ v2 extension 在前、YHT 的 `source_provenance_usage` 与 `source_immutable_*` 在后、ZC 第6节保持原样”合并；`issues.md` 保留 ZQO/LQ/ZC 三棒审阅小节，只把 YHT-V2-05/06 改为“已修复”并补验证命令，未改 LQ-V2-02、ZQO-V2-01 等他人条目。

- 合并后测试：`docs/v2/schema` 59 项、ZC v2 9 项、ZQO 14 项、LQ 18 项通过；ZC 的 `review_lq.py` 12 项探针中 11 项通过，唯一失败是已知 LQ-V2-02（0 行 vs 2 行），未改 LQ 代码或结论。该脚本在 Windows 上退出时清理临时库报 `WinError 32`，用 `TemporaryDirectory(ignore_cleanup_errors=True)` 包装重跑以取得结果，探针语义不变。
- v1 五模块测试：YHT 42、ZQO 31、ZC 24、LQ 19、LJ 15，全部通过。`audit.py --owner YHT` 三项 PASS；全量 `audit.py` 七项 PASS；`five_module.py` 11 项 PASS。命令输出写入 `/tmp`，未覆盖各成员 `experiments/results/` 下的既有 JSON。
- YHT-V2-01—04 复核：01 统一模式 59 项通过；02 操作 A 六配置×六路径 `mismatched_queries=0`，N=10,000、K=20 时四维 R\*Tree 37.4 µs、全扫 12,429 µs；03 `test_tile_and_terrain_ids_repeat_across_releases` 通过；04 空域状态/限高相关 schema 测试通过。四项均为复核通过，未改 ZC 实现。

以下 v1 记录保留为证据。

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

- 已检查提交：`bdefc03775c0bc5bc5713ad949a1828c27c04c8f`（整合最终报告与证据，2026-11-06）；五个模块均已交付；已读 AGENTS.md、课程要求、五人交接、`docs/integration/README.md`、`issues.md`、`audit.py` 与 LQ 的 `review_integration.py`。
- 最终集成修复（`81bd270dd004e7e26e52cea3b95c58ea75b45ba7`，已提交到 `main`，待复核）：YHT-01 未知 `q`/`E`/`C` 不再被丢弃，ZC/LQ 两个导出入口分别抛 `ValueError`；YHT-02 不完整覆盖、非平地、非零基面直接拒绝，不改写质量字段；YHT-03 Q1 限高改为“最高点 + 垂直半径 > ceiling_m”，接触边界不阻断，与 ZC 的 `buffer_m` 语义一致。证据见 [评估](../modules/yht/evaluation.md) 第 2.1 节与 `docs/integration/issues.md`。
- YHT-04 修复（本轮，提交 `1862ab44ca094bc493fab6fc7ce0cd6f51f2e2db`）：`export_snapshot` 新增 `require_verifiable_exposure`，每个分区的 `E`/`C`/`q` 必须为 [0,1] 内有限数且 `q=E×C`；单独缺 E/C、保留旧 q 或三者不一致时抛 `ValueError`，不再让 ZC 把旧 q 当已知风险。LQ 入口保持独立校验。证据见评估第 2.1 节与 LQ 的 `review_integration.py`（YHT 本地运行 25/25）。
- YHT-05 文档修订（本轮，提交 `c4ed005f38e1bdc927eba22d23afe69cf35f1fa8`）：`storage.md` 将错误的 `gist_geometry_ops_3d` 改为 PostGIS 3.5 官方 n 维操作符类 `gist_geometry_ops_nd`，并区分默认二维 GiST 包围盒、n 维候选过滤与 `ST_3DIntersects` 精确判定；`references.md` 补第 14 条出处。示例明确标注未在本机执行；SQLite 原型与 131/7/11/25 验证不受影响。
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

## 2026-11-07：实验改用香港九龙开放数据（AI 按 ZC 指示完成）

- `op_a_index_comparison.py` 改为在九龙 L 区（3.3 km 见方，HK1980 Grid）上运行。每个发布含 8 处民航处公告的真实限飞区，其余为放在真实建筑位置上的场景限制，尺寸与时段分布不变。
- 新结果：1 万条限制、20 个发布时，四维 R*Tree 44.1 µs，发布 B-tree 1,045 µs，全表扫描 13.7 ms；6 种路径结果一致。结论与合成数据版本相同。
- 数据字典的坐标说明改为 HK1980 Grid（EPSG:2326）与 mPD；单元测试仍使用 starter-v0 合成片区。
