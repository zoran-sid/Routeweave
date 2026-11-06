# 已执行评估与结果

## 1. 执行条件

- 日期：2026-11-05；时区 Asia/Shanghai。
- 环境：Windows 11（10.0.26300）、Python 3.12.14、SQLite 3.53.1、单进程、内存库；无数据库服务端、无网络。
- 数据：`yht-synthetic-district-v1`，基线 25 栋建筑；扩展场景用固定种子 `20261105` 生成 200/800/2,400 栋。
- 计时：每个方法先做一次预热，再交替跑 5 轮；报告单次调用中位数与 p95（最近秩）。计时包含预检、索引查询、Python 精确复核，不含落盘和结果序列化。
- 查询集：120 条 Q1（半径 15 m）、80 条 Q2，起止点与高度由固定种子生成，窗口 `2026-11-05T08:05:00Z`–`08:15:00Z`。
- 版本校验：每个场景加载时校验一次发布清单；查询计时只比较版本字符串，不重复重算内容哈希。这项选择在 [storage.md](storage.md) 第 7 节说明。

复现命令：

```bash
python3 -m unittest discover -s docs/modules/yht/prototype -v
python3 docs/modules/yht/prototype/evaluate.py
```

## 2. 功能正确性

42 项单元测试全部通过（`exit=0`）。分组如下：

| 组 | 数量 | 覆盖 |
| --- | ---: | --- |
| 几何 | 5 | 平地格网、版本/清单、环闭合与自交、线段–盒距离、缺高度建筑命中 |
| Q2 | 6 | 允许、建筑命中、限高、限高以下、禁飞激活、版本不一致 |
| Q1 | 4 | 净空、命中、垂直净空差异、限高垂直半径边界 |
| 存储 | 5 | 统计与 R\*Tree 查询计划、Q2/Q1 与全扫一致、2D 候选保守性、WAL 读写 |
| 质量 | 5 | 基线干净、12 类故障、缺高度、覆盖不完整、变异后查询 |
| 网格 | 1 | 网格索引与全扫一致 |
| 缓存 | 3 | 命中/深拷贝、版本失效、LRU 淘汰 |
| 跨模块 | 13 | ZC 快照 preflight/规划、LQ profile 形状、LQ 适配器规划；未知风险/覆盖不完整/非平地/非零基面拒绝；E/C 单独缺失、q 单独缺失、E/C 与 q 不一致拒绝（ZC 与 LQ 分别验证） |

各查询示例的实测状态（窗口 08:05–08:15Z）：

| 示例 | 航段 | 状态 | 原因 |
| --- | --- | --- | --- |
| Q2 建筑 | `[240,40,20]`→`[300,40,20]` | `forbidden` | `building:B-010` |
| Q2 禁飞 | `[140,150,80]`→`[160,150,80]` | `forbidden` | `airspace:NF-002` |
| Q2 限高 | `[325,105,65]`→`[335,105,65]` | `forbidden` | `ceiling:HL-001` |
| Q2 允许 | `[20,260,80]`→`[90,260,80]` | `allowed` | 无硬命中，覆盖完整 |
| Q2 旧版本 | 同建筑航段，传旧 scene 版本 | `unknown` | `version_mismatch:scene` |
| Q1 净空 | `[20,20,140]`→`[240,220,140]`，r=15 m | `clear` | 无硬命中 |
| Q1 阻断 | `[20,20,80]`→`[240,220,80]`，r=20 m | `blocked` | `building:B-001`、`airspace:NF-002` |

这些例子证明三维避障（建筑）、限高（HL-001）、禁飞（NF-002）、不可行/阻断、版本不一致五类语义都按设计返回。原始响应见 [results/query-examples.json](results/query-examples.json)。

### 2.1 最终集成回归（YHT-01/02/03/04）

在 `c357ac3` 的复核基线上修复并复测四项。YHT-01/02/03 的命令为 `python3 -B docs/integration/audit.py --owner YHT`，三项均通过；YHT-04 由 `python3 -B docs/modules/lq/prototype/review_integration.py` 覆盖，25/25 通过：

| 编号 | 修复前实际 | 修复后实际 |
| --- | --- | --- |
| YHT-01 | 未知 q 的分区被丢掉，下游返回 `allowed`、背景 `q_max=0.02` | ZC 与 LQ 两个入口都抛 `ValueError:unknown_or_invalid_exposure:G-001`，不默认背景 |
| YHT-02 | 不完整覆盖/非平地被写成 `complete=True`、`terrain_z=0.0`，preflight 通过 | 分别抛 `ValueError:incomplete_coverage:T-00-00` 与 `unsupported_terrain:only_flat_supported` |
| YHT-03 | 58 m 中心线、5 m 半径、60 m 限高被判 `clear` | YHT `blocked`，ZC `forbidden`；54/55 m 仍为 `clear`，55.1 m 起阻断，接触边界与 ZC 一致 |
| YHT-04 | 单独缺 E 或 C、保留 q=0.78 时，直接 ZC 导出仍为 `allowed`、`q_max=0.78` | 直接 ZC 导出新增 `require_verifiable_exposure`，抛 `ValueError:unknown_or_invalid_exposure:G-001`；E/C 与 q 不一致时抛 `inconsistent_exposure:G-001` |

`test_yht.py` 增加了上述正常、异常和边界用例；完整平地、已知 `E`/`C`/`q` 的基线导出仍通过 ZC `preflight`、A\* 和 LQ 编译。

## 3. 索引基准

完整表在 [storage.md](storage.md) 第 5 节，原始数据在 [results/benchmark.json](results/benchmark.json) 与 [results/summary.csv](results/summary.csv)。关键对比：

| 规模 | Q2 全扫中位 | Q2 SQLite 3D 中位 | 倍数 | Q1 全扫中位 | Q1 SQLite 3D 中位 | 倍数 | 3D 候选比例 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 200 | 985 µs | 76.7 µs | 12.8× | 7,690 µs | 148 µs | 51.9× | 0.44% |
| 800 | 3,680 µs | 76.9 µs | 47.9× | 39,540 µs | 159 µs | 249× | 0.39% |
| 2,400 | 10,390 µs | 79.4 µs | 131× | 122,936 µs | 155 µs | 792× | 0.58% |

构建时间 4.1 ms / 13.0 ms / 37.0 ms；库文件在 2,400 栋时为 1.07 MB，发布 JSON 为 884 KB。全扫的 Q1 中位耗时随规模近似线性增长（7.69 → 39.54 → 122.94 ms），索引路径基本稳定在 0.148–0.159 ms；Q2 全扫 0.985 → 3.680 → 10.390 ms，索引 0.0767–0.0794 ms。

正确性对照：三种索引方法与全扫在 200/800/2,400 三个规模、200 条查询上状态与命中集合完全一致（`signature_mismatches` 全为 0）。这说明索引只改变候选集，不改变语义。

### 3.1 查询缓存与 WAL 并发（已执行）

`prototype/cache.py` 的版本键 LRU 用同一批 20 条查询（10 条 Q1 + 10 条 Q2）测了冷/热路径：冷 miss 中位 602.1 µs，热命中中位 17.5 µs，约 34.4 倍；热阶段 60 次命中，换代后 1 次 miss，`invalidations=1`。缓存值先深拷贝，避免调用方修改污染条目。原始结果见 [results/cache.json](results/cache.json)。

WAL 并发只覆盖单文件场景：写连接持有 `BEGIN IMMEDIATE` 时，读连接仍能读到 25 栋建筑的完整快照（`test_wal_reader_during_writer`）。它证明读不被写事务阻塞，但没有测发布切换、写队列、跨进程协调和生产 QPS，不能当作并发能力结论。

## 4. 数据质量与故障注入

- 基线：34 个要素（25 建筑 + 3 空域 + 6 暴露分区），0 错误、0 警告，发布清单计数一致。
- 12 类故障全部检出：重复 ID、自交轮廓、未闭合环、顶低于底、缺高度、未知来源、q 越界、瓦片不完整、非法空域类型、缺限高、越界、版本过期。
- 缺高度（B-006）查询返回 `unknown`，原因 `unknown_height:B-006`；瓦片 `T-02-02` 不完整时查询返回 `unknown`，原因 `incomplete_coverage`。
- 这说明"数据可发布"与"查询可判定"是两件事：缺高度不阻断发布，但会阻断确定性结论。

原始结果见 [results/quality.json](results/quality.json)。

## 5. 动态更新

在场景中新增临时禁飞体 NF-003（`x=40–80, y=250–290, z=0–120`，有效期 08:00–09:00Z），重新 `seal()`：

- 更新前，航段 `[50,240,60]`→`[50,300,60]` 为 `allowed`。
- 更新后，同一航段为 `forbidden`，原因 `airspace:NF-003`。
- 用旧五版查询新快照，返回 `unknown`，原因 `version_mismatch:airspace`；只有 airspace 版本变化，其余四版不变。
- 该例验证"限制生效 + 版本一致性"分开判定：新版本下限制生效，旧版本下查询被拒绝，而不是静默用旧数据。

原始结果见 [results/update-example.json](results/update-example.json)。未测 D\* Lite 或增量重规划，这属于 ZC 的算法评估；YHT 只保证发布切换时查询不会混用版本。

## 6. 跨模块导出

用 `export_zc.write_export` 把场景裁剪到搜索域 `[[0,0,10],[450,450,120]]`，起点 `(20,20,70)`、终点 `(420,420,70)`：

- ZC `preflight` 返回 `None`（通过）。
- A\* 返回 `feasible`，612.5483 m、61.2548 s，扩展 355 节点、8,745 次边检查，本次运行 152.7 ms（单次，不称端到端延迟）。
- 快照含 15 个障碍、NF-002 与 HL-001 两条限制、4 个裁剪后的风险区；risk_proxy 4.2120，cost 6.1255（λ=0）。
- 同一快照下，直线起点→终点 `assess_segment` 为 `forbidden`，原因 `obstacle:B-001`；规划器绕行，两者不矛盾。
- 导出时 L 形建筑 B-023 取轴对齐包围盒，属于保守近似；这不影响"有障碍"的判定，但会让比实际轮廓更大的区域不可通行。

原始结果见 [results/zc-export.json](results/zc-export.json) 与 [results/zc-export-summary.json](results/zc-export-summary.json)。

LQ 适配用 `export_lq.write_export` 把 6 个暴露分区转成 LQ profile：每个 profile 带 `box`、`source` 和覆盖整个发布有效期的 `periods[{valid,E,C}]`，且满足 `q=E×C`。`compile_profiles` 重新绑定 ZC 五类版本后：

- `preflight` 返回 `None`，A\* 仍为 `feasible`，612.5483 m、61.2548 s，扩展 355 节点、8,745 次边检查，本次 124.9 ms。
- `risk_proxy` 4.2120，与直接用 ZC 风险区时一致；原因是字段映射没有改 q，只补了 LQ 需要的 E/C 和时段结构。
- 同一直线航段仍为 `forbidden`（`obstacle:B-001`）。
- 6 个分区的 q 最大 0.82，低于 LQ 硬阈值 0.9，因此本例没有触发"风险硬约束"阻断；这验证的是接口和版本传递，不是风险模型本身。

原始结果见 [results/lq-export.json](results/lq-export.json) 与 [results/lq-export-summary.json](results/lq-export-summary.json)。

## 7. 结果判断

- 三维索引在本场景有效：候选压到 1% 以下，查询耗时随规模基本不变；但这是单机内存库，不能外推为生产 QPS。
- Q1 的收益大于 Q2，因为 Q1 全扫要对每条长线段检查全部建筑；这也说明"先做包围盒过滤"对走廊查询更关键。
- 2D 与 3D 差距小，原因是查询高度落在建筑高度范围内；不能据此得出"二维索引够用"的结论，三维体的判定仍需要 z。
- 版本校验如果放在每查询路径，会随对象数线性增长，抵消索引收益；生产应把它放在加载/发布阶段，查询只比对版本字符串。这是本模块实现中明确调整过的点。
- 质量门禁的代价是发布前多一次全量检查；收益是把"缺高度""瓦片不完整"这类问题挡在查询语义之前，而不是让调用方自己猜。
- 版本键缓存对重复查询有收益，但单进程 LRU 不能证明多实例一致性；WAL 只证明读不被写事务阻塞，不证明发布切换正确。两者都只作为机制验证。

## 8. 未执行的评估

以下项目没有实测，不能写成结论：

| 项目 | 原因 | 建议方法 |
| --- | --- | --- |
| 地形起伏与离地高度 | 当前基线 `terrain_z=0`，ZC 也只接受平地 | 构造 5–20 m 起伏格网，比较平面距离与离地净空 |
| PostGIS 实库对照 | 本机无 PostgreSQL/PostGIS 服务 | 同规模数据导入，测 `&&&` + `ST_3DIntersects` 的候选数与延迟 |
| 并发查询与写入 | 只做了 SQLite WAL 单文件读写小实验，没有发布切换和多进程 | 多线程/多进程压测，记录锁冲突、写队列与 p95 |
| 跨进程缓存一致性 | 只实现单进程版本键 LRU | 多实例共享缓存，验证换代广播、旧版本回源与失效延迟 |
| 真实数据接入 | 无真实数据许可 | 用公开城市模型做小范围试接，逐源记录质量 |
| 风险模型耦合 | LQ 已交付，但未替换本模块的合成 E/C | 用 LQ 的真实暴露/后果模型替换代理 q，比较排序变化 |
| 增量更新 | 只做整版重发布 | 比较整版重建与按瓦片增量构建的时间、版本一致性 |
| 前端交互延迟 | 无前端 | 在 API 层测序列化、网络和渲染，不与本基准混用 |

说明：PostGIS 对照曾临时启动 PostgreSQL 17.6，但 PostGIS 3.6.2 Windows bundle 下载速度过慢，未完成安装；相关进程和目录已清理，因此该行仍记为未执行，不写成"已验证"。

## 9. 复现注意事项

- 结果依赖 Python 版本、SQLite 版本和机器负载；不同机器上绝对微秒数会变，候选比例和正确性签名应保持一致。
- `evaluate.py` 会覆盖 `results/` 下的生成文件；提交前确认当前数字与文档一致。
- 基准中的 `sqlite_file_bytes` 只在 2,400 栋规模生成，因为落盘测量只做一次；其余规模是内存库。
- p95 在短基准中受离群值影响明显，报告中同时给出中位数和 p95，不把 p95 单独当 SLA。
