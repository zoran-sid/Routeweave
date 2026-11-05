# 存储、索引与访问路径

本文件回答三个问题：YHT 的数据放在哪、查询怎样走索引、为什么选这套方案。基准数字来自 [results/benchmark.json](results/benchmark.json) 和 [results/summary.csv](results/summary.csv)，缓存数字来自 [results/cache.json](results/cache.json)，执行条件见 [evaluation.md](evaluation.md)。

## 1. 访问模式

| 访问 | 频率（设计假设） | 形状 | 延迟目标 |
| --- | --- | --- | --- |
| Q2 单航段状态 | 高，规划器每轮大量调用 | 短线段、已知起止点、固定窗口 | 单次毫秒级 |
| Q1 走廊检查 | 中，用户输入或规划器复核 | 较长线段 + 15–20 m 半径 | 单次毫秒级 |
| 发布/重发布 | 低 | 整场景写入 + 重建索引 | 秒级可接受 |
| 版本审计 | 低 | 按版本取清单与对象 | 不要求低延迟 |
| 导出给 ZC | 低 | 全量读出并裁剪 | 一次数百毫秒可接受 |

写入是"整版发布"，不是逐条编辑；读取是"按版本读"。这个不对称决定了索引可以按发布重建，不必支持频繁原地更新。

## 2. 候选方案

| 方案 | 三维体支持 | 查询方式 | 证据 | 结论 |
| --- | --- | --- | --- | --- |
| 内存全扫（基线） | 直接 | 每条线段遍历所有建筑 | 本次实测 | 语义基准，规模大时不可用 |
| SQLite R\*Tree 3D | 是 | 7 列虚拟表，三维包围盒过滤 + 回表精算 | SQLite 官方文档：R\*Tree 支持 1–5 维，3 维为 7 列，32 位浮点向外取整 | **原型采用** |
| SQLite R\*Tree 2D + z 列 | 二维索引，z 在回表时过滤 | 5 列虚拟表 + `top_z/base_z` 条件 | 同上；z 条件只能减少回表后的精确检查 | 保留为对照，不单独作为三维方案 |
| 均匀网格 3D | 是 | 40 m 立方单元格，对象跨格重复登记 | 本次实测 | 构建快，候选重复多，规模增大后变慢 |
| PostGIS | 是 | `geometry(PolyhedralSurfaceZ)`、`&&&`、`ST_3DIntersects`，GiST `gist_geometry_ops_3d` | PostGIS 官方文档：三维相交自动包含包围盒比较并使用可用索引；`&&&` 为 n 维包围盒相交 | 生产候选，未在本机实库验证 |
| MongoDB 2dsphere | 球面二维 | GeoJSON/球面几何 | 文档以地球球面查询为主，未取得三维体索引的明确说明 | 不选 |
| Neo4j point index | 点 | 2D/3D 点、距离/包围盒 | 官方文档：point index 只索引点，使用空间填充曲线 | 不选（建筑是体，不是点） |
| Elasticsearch geo_shape | 二维 | 经纬度形状 | 官方文档：只有经纬度入索引，`ignore_z_value` 默认 true | 不选 |

选择 SQLite 的理由不是"它最强"，而是：标准库自带、无服务端依赖、单文件可随仓库复现；R\*Tree 的三维包围盒足以把候选压到 0.5% 量级；精确几何本来就要在应用层做，索引只当过滤器，语义与基线完全一致。PostGIS 是更合适的生产路线，原因见第 5 节。

## 3. 选定的库结构

原型库 `SQLiteStore` 的表：

```sql
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE source (source_id TEXT PRIMARY KEY, name TEXT, kind TEXT,
                     license TEXT, acquired_at TEXT, valid_from TEXT,
                     valid_to TEXT, accuracy_xy_m REAL, accuracy_z_m REAL,
                     method TEXT);
CREATE TABLE coverage (tile_id TEXT PRIMARY KEY, minx REAL, miny REAL,
                       maxx REAL, maxy REAL, complete INTEGER, source_id TEXT);
CREATE TABLE feature (rid INTEGER PRIMARY KEY, feature_id TEXT UNIQUE,
                      layer TEXT, name TEXT, source_id TEXT, quality TEXT,
                      valid_from TEXT, valid_to TEXT);
CREATE TABLE building (rid INTEGER PRIMARY KEY REFERENCES feature(rid),
                       footprint TEXT, base_z REAL, top_z REAL,
                       height_m REAL, height_source TEXT);
CREATE TABLE ground (rid INTEGER PRIMARY KEY REFERENCES feature(rid),
                     polygon TEXT, exposure_class TEXT, exposure_e REAL,
                     consequence_c REAL, q REAL);
CREATE TABLE airspace (rid INTEGER PRIMARY KEY REFERENCES feature(rid),
                       footprint TEXT, floor_z REAL, ceiling_z REAL,
                       ceiling_m REAL, kind TEXT, state TEXT, authority TEXT);
CREATE TABLE release (version TEXT PRIMARY KEY, created_at TEXT, manifest TEXT);
CREATE VIRTUAL TABLE rtree_building USING rtree(
    rid, minx, maxx, miny, maxy, minz, maxz);
CREATE VIRTUAL TABLE rtree_building_2d USING rtree(
    rid, minx, maxx, miny, maxy);
CREATE VIRTUAL TABLE rtree_ground USING rtree(rid, minx, maxx, miny, maxy);
CREATE VIRTUAL TABLE rtree_airspace USING rtree(
    rid, minx, maxx, miny, maxy, minz, maxz);
CREATE INDEX feature_layer ON feature(layer);
```

说明：

- 几何以 JSON 文本存原始轮廓/多边形，R\*Tree 只存包围盒。回表后用 Python 做"线段–多边形"或"线段–盒"精确判定。
- `rid` 是内部整数键，`feature_id` 是业务 ID（如 `B-001`）。两者分离，重发布时可以重建 `rid` 而不改业务标识。
- 建筑同时建 3D 和 2D 索引，是为了在同一份数据上对照两种访问路径；生产环境只保留选中的一种。
- `coverage` 与 `source` 是普通表，不参与空间索引；查询预检直接按瓦片 ID 和范围判断。
- `release` 保存发布清单，便于按版本追溯；原型一次只装一个发布，未实现多版本并存。

## 4. 查询计划

Q2 的 3D 路径：

1. 用线段起止点构造三维包围盒 `lo/hi`。
2. `rtree_building` 做六条件包围盒相交，得到候选 `rid`。
3. 回表取 `footprint/base_z/top_z`，对每个候选做完整三维线段–盒判定。
4. 对空域表用同样的包围盒过滤 + 三维命中/限高判定；地面分区用二维包围盒 + 线段–多边形相交。

`EXPLAIN QUERY PLAN` 在测试中确认走了 `VIRTUAL TABLE INDEX`，不是全表扫描。R\*Tree 的包围盒用 32 位浮点存储，下界向下、上界向上取整；SQLite 文档明确这保证重叠查询不会漏掉合法条目（包含式查询需要额外外扩约 0.000012%）。因此"索引漏检"不是本方案的风险，"索引多给候选"才是，而多给的候选会被精确判定剔除。

Q1 的路径相同，只是包围盒按半径外扩；建筑用线段–盒距离 ≤ 半径，空域用水平距离和垂直间隙都不超过半径。半径同时作用于水平和垂直，是保守近似，不做椭球或方向相关缓冲。

2D 路径把第 2 步换成 `rtree_building_2d`，再在回表条件里加 `top_z >= lo_z AND base_z <= hi_z`。它仍然正确，但 z 过滤发生在连接之后，候选集通常不小于 3D；本次场景中两者候选数相同，是因为建筑高度普遍覆盖查询高度，2D 少掉的只是索引列，不是候选。

## 5. 基准结果

执行条件：Windows 11、Python 3.12.14、SQLite 3.53.1、单进程、内存库；每个方法先做一次不计时的预热，再交替跑 5 轮；120 条 Q1（半径 15 m）和 80 条 Q2；中位数与 p95 为单次调用耗时，含预检、索引查询、Python 精确复核，不含落盘。原始数据见 [results/benchmark.json](results/benchmark.json)。

| 建筑数 | 方法 | 构建 ms | Q1 中位 µs | Q1 p95 µs | Q2 中位 µs | Q2 p95 µs | 平均候选 | 候选比例 |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 200 | 全扫 | 0 | 7,690 | 11,280 | 985 | 1,025 | 200.0 | 100% |
| 200 | SQLite 3D | 4.1 | 148 | 441 | 76.7 | 105 | 0.9 | 0.44% |
| 200 | SQLite 2D+z | 4.8 | 146 | 392 | 77.8 | 104 | 0.9 | 0.44% |
| 200 | 网格 3D | 0.4 | 211 | 1,283 | 79.5 | 112 | 3.1 | 1.53% |
| 800 | 全扫 | 0 | 39,540 | 51,192 | 3,680 | 5,897 | 800.0 | 100% |
| 800 | SQLite 3D | 13.0 | 159 | 2,212 | 76.8 | 170 | 3.1 | 0.39% |
| 800 | SQLite 2D+z | 13.3 | 145 | 1,715 | 90.8 | 263 | 3.1 | 0.39% |
| 800 | 网格 3D | 1.4 | 218 | 7,033 | 88.3 | 573 | 14.2 | 1.77% |
| 2,400 | 全扫 | 0 | 122,936 | 144,967 | 10,390 | 15,732 | 2,400.0 | 100% |
| 2,400 | SQLite 3D | 37.0 | 155 | 7,343 | 79.3 | 486 | 13.9 | 0.58% |
| 2,400 | SQLite 2D+z | 37.9 | 208 | 7,342 | 92.2 | 529 | 13.9 | 0.58% |
| 2,400 | 网格 3D | 4.2 | 583 | 17,519 | 120 | 1,084 | 49.7 | 2.07% |

2,400 栋时，3D 索引把 Q2 中位耗时从 10.39 ms 压到 0.0793 ms（约 131 倍），Q1 从 122.94 ms 压到 0.155 ms（约 792 倍）；库文件 1.07 MB，发布 JSON 884 KB。候选数从 2,400 降到 13.9，精确判定只跑这 13.9 个对象。

### 5.1 缓存与并发读写小实验（已执行）

`prototype/cache.py` 实现了一个单进程的版本键 LRU：键是查询类型、起终点、半径和窗口，值缓存前先绑定五层版本；`bind()` 发现版本变化就整代清空。20 条查询（10 条 Q1 + 10 条 Q2）的冷 miss 中位 602.1 µs，热命中中位 17.5 µs，约 34.4 倍；热阶段 60 次命中、换代后 1 次 miss，符合"发布切换即失效"的预期。命中包含一次 `deepcopy`，避免调用方改坏缓存值。

并发只验证了 SQLite WAL 的单文件行为：写连接持有 `BEGIN IMMEDIATE` 时，读连接仍能读到 25 栋建筑的完整快照；测试是 `test_wal_reader_during_writer`。这证明"读不被写事务阻塞"的机制可用，但没有测发布切换、写队列、跨进程协调和生产 QPS，不能当成并发能力结论。

对结果的解释：

- 收益主要来自"候选过滤"，不是"索引直接给出答案"。Q1 的倍数高于 Q2，是因为 Q1 每条查询要检查更长的线段和更多对象，全扫成本更高。
- p95 远高于中位数，主要来自进程内 GC、操作系统调度和 Python 对象分配；短基准的 p95 不适合当作 SLA，结论以中位数和候选比例为主。
- 2D 和 3D 在本场景差距很小：建筑高度从 15 m 到 120 m，查询高度 20–130 m，z 维度本身区分度有限。若场景以低层建筑和低空航线为主，3D 索引的优势会更明显；若查询高度总是落在建筑高度范围内，2D 加回表过滤也能工作，但不能声称"二维索引支持三维体"。
- 网格索引构建最快（4.8 ms），但候选重复登记导致查询比 R\*Tree 慢，且单元格大小需要按场景调；它适合内存中一次性规划，不适合作为持久化主索引。
- 这些都是单机、单进程的数字。没有测数据库服务端、网络往返、写入吞吐和并发查询；缓存和 WAL 只做了 20 条查询/单文件的小实验，不能外推为生产容量结论。

## 6. 生产化路线

若把原型搬到生产，建议：

1. **主存储用 PostgreSQL + PostGIS**：建筑用 `geometry(PolyhedralSurfaceZ, 0)` 或带 Z 的 `geometry`，空域用三维体；建 `gist_geometry_ops_3d` 索引；查询先用 `&&&` 做包围盒过滤，再用 `ST_3DIntersects` 精确判定。PostGIS 文档说明 `ST_3DIntersects` 会自动做包围盒比较并使用可用索引，但这不改变"浮点鲁棒性需用 `ST_3DDWithin` 复核"的限制。
2. **按发布分区**：每次发布一个 schema 或一个分区表，查询绑定发布 ID；旧发布保留只读，按保留策略下线。这样版本切换是"换分区"，不是"改行"。
3. **覆盖瓦片做二级分区/聚簇**：`coverage` 瓦片与来源分块对齐，按瓦片聚簇可减少大范围查询的随机 I/O；超大面用 `ST_Subdivide`，避免单个几何过大。
4. **热/温/冷分层**：热层是当前发布的 R\*Tree/GiST 索引和常用查询结果缓存；温层是历史发布的只读快照；冷层是导出 JSON 或对象存储归档。原型只实现热层的内存/单文件库。
5. **缓存**：按 `(release_id, query_hash)` 缓存 Q2 结果，发布切换时整代失效；不要缓存跨版本结果，除非键里包含全部五版。
6. **写入**：新发布在旁路构建索引，校验通过后原子切换；不做原地更新。原型用 `seal()` + `SQLiteStore.build()` 模拟这条路径。

## 7. 已知风险

- R\*Tree 只保证包围盒不漏；精确判定必须回表，任何"只查索引就返回"的优化都会改变语义。
- SQLite 的 32 位浮点包围盒在极小/极大坐标下会有精度损失；本场景坐标 0–600 m，影响可忽略，跨城市坐标应先做局部投影。
- SQLite WAL 允许读者在写事务期间继续读（`test_wal_reader_during_writer` 已覆盖单文件场景），但原型没有发布切换锁、写入队列和跨进程协调；生产仍应旁路构建索引、校验后原子切换。
- 索引重建时间随对象数增长；2,400 栋约 37 ms 是内存库数字，落盘和真实几何会更慢。
- 版本校验默认在每个查询里重算内容哈希，成本随对象数线性增长；基准中改为"每次加载校验一次，查询只比对版本字符串"，生产也应把校验放在发布/加载阶段，不要每查询重算。
