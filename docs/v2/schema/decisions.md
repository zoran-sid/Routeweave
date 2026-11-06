# SkyRoute v2 统一模式设计决定

日期：2026-11-06。逻辑模型来自 [YHT 数据字典](../../modules/yht/v2/data-dictionary.md)；本文件说明可执行模式 [schema.sql](schema.sql) 的权威边界、JSON 使用规则、方言映射和逐项决定。各表组负责人细化本组表时在第4节追加决定。

## 1 哪些数据以数据库为准

| 类别 | 表或对象 | 地位 | 丢失后怎么办 |
| --- | --- | --- | --- |
| 发布与版本 | `release`、`release_layer` | 权威 | 不可重建；依赖备份恢复（LJ） |
| 源数据与空间 | `source`、`coverage_tile`、`feature`、`building`、`terrain_*`、`airspace_restriction`、`exposure_zone` | 权威 | 不可重建；依赖备份恢复 |
| 事件与审计 | `airspace_event`、`audit_event`、`lineage_edge` | 权威，只追加 | 不可重建 |
| 模型与权限 | `risk_model`、`actor`、`access_policy` | 权威 | 不可重建 |
| R*Tree 索引 | `rtree_building`、`rtree_airspace`、`rtree_exposure` | 派生 | 由基表 `INSERT … SELECT` 重建；触发器保持同步 |
| 内容哈希 | `release.content_hash`、`release_layer.content_hash` | 派生校验值 | 由内容重算，用于核对而不是存储真相 |
| v1 JSON 快照与导出 | YHT→ZC、YHT→LQ 导出对象 | 派生 | 给定 `release_id` 从数据库重新生成 |
| 规划派生图缓存 | ZC 预留 | 派生 | 按 `release_id` 重建（ZC 第6章评估重建成本） |

规则：查询结果只能来自绑定 `release_id` 的权威表；派生对象必须能说明由哪个发布生成，并能在丢失后重建。v1 链路交换的 JSON 快照在 v2 中降为可重建的导出，不再作为事实来源。

**历史查询**：每次发布的对象行全量保留，查询历史发布时把 `release_id` 换成旧值即可，SQL 与当前查询相同。代价是重复存储：K 次发布保存 K 份同一限制。操作 A 的实验显示，时空索引在 K=20 时候选数随之增加但仍远低于 B-tree 路径（见 YHT 第4.3节）；组件共享与全量复制的存储开销由 ZQO 第5章测量。

## 2 JSON 字段

| 字段 | 内容 | 为什么用 JSON |
| --- | --- | --- |
| `release.manifest` | 层版本、对象计数、瓦片摘要、工具版本 | 供复核与展示，结构随工具演进；关键值另有类型化列 |
| `feature.attrs` | 子类型扩展属性 | 多源字段差异大；暂存灵活、发布严格 |
| `exposure_zone.uncertainty` | 置信区间、样本量或定性说明 | 不同来源的不确定性表达不同 |
| `risk_model.params` | 阈值、聚合、包络参数 | 模型版本的参数集合，整体随版本变化 |
| `access_policy.condition` | 时间、机构、用途条件 | 条件组合多样；LQ 细化时可改为类型化列 |
| `lineage_edge.evidence` | 参数、哈希、命令摘要 | 复现证据，不参与查询判定 |
| `audit_event.detail` | 请求参数摘要 | 只读追查；不得存完整敏感轨迹 |

**规则**：参与硬约束、连接、索引、权限判断或安全结论的值必须是类型化列，不能只放在 JSON 中。所有 JSON 列用 `json_valid` 校验格式。

## 3 SQLite 原型与 PostgreSQL/PostGIS 部署的对应

| 语义 | SQLite 原型（本目录） | PostgreSQL 17 + PostGIS 3.5 |
| --- | --- | --- |
| 时刻 | 定长 UTC 文本 + `GLOB` 格式检查 | `timestamptz` |
| 半开区间 | `_lo` / `_hi` 两列 + `CHECK (lo < hi)` | `tstzrange`，`[)` |
| 枚举 | `TEXT + CHECK IN` | 同左或原生 `ENUM` |
| JSON | `TEXT + json_valid` | `jsonb` |
| 几何 | WKT 文本 + 包围盒列 | `geometry(PolyhedralSurfaceZ,0)` 等，`ST_IsValid` 约束 |
| 空域时空索引 | 四维 R*Tree（x, y, z, t） | `volume` 的 n 维 GiST（`gist_geometry_ops_nd`）与 `effective` 范围 GiST，规划器组合或择一 |
| 精确复核 | 包围盒列与时间文本 | `ST_3DIntersects` / `ST_3DDWithin` 与 `&&` 区间运算 |
| 禁止垂直范围 | 生成列 `forbid_lo_z` / `forbid_hi_z` | 生成列或表达式索引 |
| 发布后不可变 | `BEFORE UPDATE/DELETE` 触发器 | 触发器，配合撤销 `UPDATE/DELETE` 权限 |
| 审计只追加 | 触发器拒绝更新与删除 | 同左，并按月分区、热区90天 |

PostgreSQL 一列尚未部署实测，属于设计映射；性能结论只引用 SQLite 实验。

## 4 逐项决定

| 编号 | 问题 | 决定 | 依据与影响 |
| --- | --- | --- | --- |
| S-01 | 字典把 `coverage_tile.tile_id`、`terrain_surface.terrain_id` 作为单列主键，但瓦片编号和地形编号在每次发布都会重复 | 主键改为 `(release_id, layer, tile_id)` 与 `(release_id, terrain_id)`；`terrain_post` 主键加 `release_id` | 否则第二次发布即主键冲突；测试 `test_tile_and_terrain_ids_repeat_across_releases` |
| S-02 | 字典称 `airspace_restriction.state` 由发布流程维护，与“发布后只读”冲突 | `state` 记录该发布时刻的状态，随发布不可变；撤销写入新发布中的 `revoked` 行和一条 `airspace_event` | 保证历史可复现；ZQO 的发布/撤销事务按此实现 |
| S-03 | 限高体禁止的是 `ceiling_m` 以上，按 `floor_z..ceiling_m` 建索引会漏掉越过限高的走廊 | 增加生成列 `forbid_lo_z` / `forbid_hi_z`，R*Tree z 维与精确复核都用禁止范围 | 测试中 60 m 限高命中 40–90 m 走廊，120 m 限高不命中 |
| S-04 | 操作 A 用哪种访问路径 | 空域采用四维时空 R*Tree，`op_a.sql` 用 `CROSS JOIN` 固定由 R*Tree 驱动 | 实验比较全扫、发布 B-tree、时间 B-tree、三维与四维 R*Tree；SQLite 规划器自选时 R*Tree 退化为逐行查找 |
| S-05 | 发布不可变由谁保证 | 数据库触发器拒绝向非 draft 发布插入、修改或删除内容；发布须五层齐全；状态只能按 draft→published→superseded/retired 迁移 | 不依赖应用自觉；测试覆盖 |
| S-06 | `airspace_event.restriction_id` 引用的列在全表不唯一 | `restriction_id` 必须等于 `feature_id`；事件以 `(release_id, restriction_id)` 外键引用 `feature(release_id, feature_id)` | 由子类型触发器和复合外键保证 |
| S-07 | 血缘端点类型多样 | `lineage_edge` 不设跨类型外键，只检查取值与不自环；端点存在性由发布质检校验 | 与字典一致；LQ 可增加按类型的校验视图 |

## 5 已知限制

- SQLite 原型不解析 WKT，精确判定使用轴对齐包围盒；非矩形楼体与斜面空域需 PostGIS 精确谓词复核。
- 暴露分区互斥且恰好覆盖一次、瓦片面积和等于场景面积，属于跨行约束，由发布质检执行，不用单行 `CHECK`。
- R*Tree 以32位浮点向外取整存储，只作候选；时间维以“距 2026-01-01 的秒数”存储，一年内精度约2秒，精确时间判定使用基表文本列。
