# 需求与三维数据模型

本文件说明 YHT 工作包的问题边界、模拟场景、对象模型、版本语义和查询判定规则。评估数字见 [evaluation.md](evaluation.md)，存储实现见 [storage.md](storage.md)。

## 1. 问题与范围

SkyRoute 的 Q1 是"给起点、终点、出发时间和约束，返回一条可执行的三维航线"；Q2 是"给定三维航段或区域，返回它碰到的建筑、空域限制、地面暴露及其来源"。YHT 不实现规划算法，负责让这两个查询有可用的数据底座：

- 定义场景中有哪些对象、每个对象有哪些几何与属性、坐标和高度相对什么基准。
- 定义场景、地形、空域、暴露、来源五类内容的版本，以及一次查询如何绑定版本。
- 给出 Q1/Q2 的数据访问语义：什么情况判 `feasible`/`clear`、`infeasible`/`blocked`、`unknown`。
- 用合成数据实例化模型，验证三维避障、限高、禁飞、不可行、数据缺失和版本不一致。
- 向 ZC 提供可直接消费的快照，向 ZQO 提供空域与版本字段，向 LQ 提供暴露几何与质量说明，向 LJ 提供审计字段。

不在范围内：真实飞行控制、实时避障、真实人口数据、真实 NOTAM 接入、生产级高可用部署。原型只证明数据组织和访问方式可行。

## 2. 用户与查询需求

| 用户 | 关心的问题 | 对数据的直接要求 |
| --- | --- | --- |
| 物流调度员 | 这条航线现在能不能飞、绕行多少 | 快速返回状态与原因；起降点、时间窗、版本明确 |
| 无人机运营人员 | 航线碰到的限制是否在有效期内 | 每条限制带有效期和发布状态；过期限制不能静默生效 |
| 空域与安全管理员 | 限制来自哪个机构、哪一版、覆盖是否完整 | 来源、质量、版本、覆盖瓦片可追溯；缺失数据显式标 unknown |
| 系统管理人员 | 数据发布后查询是否一致、哪里出错 | 发布清单、内容哈希、索引完整性检查、错误码 |

利益相关者不止四类直接用户：被航线飞越的居民和访客、提供建筑/地形/空域数据的外部机构、负责发布的值班人员也受影响。后几类没有直接查询界面，本模块通过暴露分区、来源元数据、质量门禁和审计字段间接表达他们的约束；真实人口和隐私数据的接入不在本次范围。

由这些需求导出六个功能性要求：三维几何查询、时间有效性过滤、版本一致性校验、质量门禁、来源追溯、面向前端的稳定错误原因。非功能要求是：单机可复现、查询结果可重复、索引可重建、数据可导出给其他模块、合成数据可公开。

## 3. 模拟场景

场景 `yht-synthetic-district-v1` 是一个 600 m × 600 m、高 160 m 的局部片区，代表高层建筑、商业区、住宅区、公园、政务区和人员密集的交通枢纽并存的城市地块。所有对象由代码确定性生成，随机填充体块使用固定种子 `20261105`。密封后的完整原生快照保存在 [results/scene.json](results/scene.json)，可以直接检查字段、版本和清单。

| 图层 | 内容 | 数量 | 说明 |
| --- | --- | --- | --- |
| 建筑 | 命名建筑 + 合成体块 | 25（基线），最多 2,400 | 含一栋 L 形建筑 B-023；高度 15–120 m |
| 地形 | 规则格网 | 31 × 31，20 m 间距 | 本基线为平地，`terrain_z=0`，保留格网结构 |
| 地面暴露 | 多边形分区 | 6 | 覆盖全域且互不重叠；q=E×C 是代理值，不是人口数 |
| 空域 | 禁飞体、限高体 | 3 | NF-001 政务禁飞、NF-002 活动禁飞、HL-001 医院限高 60 m |
| 覆盖 | 100 m × 100 m 瓦片 | 36 | 每片带 `complete` 标志 |
| 来源 | 数据来源记录 | 5 | 轮廓、高度、地形、暴露、空域各一 |

场景有效期是 `2026-11-05T08:00:00Z` 到 `09:00:00Z`。查询窗口必须完全落在有效期内；窗口越界返回 `unknown`，不把"没数据"解释成"没有限制"。

规模与增长按算术估算，不是实测结论：25 栋基线紧凑 JSON 约 52 KB（34 个 feature，另有 36 个覆盖瓦片和 961 个地形点；缩进后的 `results/scene.json` 约 107 KB）；200 栋基准场景约 112 KB（209 个要素），2,400 栋约 884 KB（2,409 个要素），约 360 B/要素。对象数增长 10 倍时，单版 JSON 约 8.8 MB，三维 R\*Tree 大约同量级。若每天保留一版、保留 30 天，原始发布约 260 MB；实际增长主要来自新发布和历史版本，而不是单版内对象数。查询量、并发和真实几何复杂度没有数据，不能据此推算生产容量。

25 栋建筑中，B-001 高 120 m，B-002 高 80 m，B-013 高 70 m，B-023 为 L 形；这些对象用于覆盖"建筑高于航线""航线从楼顶擦过""L 形轮廓不能当矩形"等情形。空域体只覆盖部分高度：NF-001、NF-002 从地面到 120 m，HL-001 的绝对上限是 160 m、运行限高是 60 m。

## 4. 坐标、高度与时间

- 坐标：局部直角坐标，x 向东、y 向北、z 向上，单位米，原点在片区西南角地面。`crs = starter-v0-local-m`。
- 高度：`z` 是相对共同参考平面（z = 0）的椭球高代理；建筑 `base_z` 是底部高程，`top_z = base_z + height_m`。本场景 `base_z` 均为 0，地形格网也为 0，因此可以直接与 ZC 的平地假设对接。
- 不使用 GeoJSON 作为内部格式。RFC 7946 固定 WGS-84 经纬度，局部米制坐标直接标成 GeoJSON 会产生错误的坐标语义；导出到需要经纬度的系统时应先做局部投影并记录投影参数。见 [references.md](references.md) 的 RFC 7946 条目。
- 时间：ISO 8601、带时区、统一转 UTC；有效期是半开区间 `[start, end)`。查询窗口和对象有效期做区间重叠判断；窗口必须被场景有效期完全包含。
- 精度：几何顶点为 0.1 m 量级的合成坐标；距离用双精度计算。索引中的包围盒按 32 位浮点向外取整，精确判定在 Python 中完成，避免"索引说相交就当成相交"。

## 5. 数据模型

一次发布是一个不可变的 `release` 对象，结构如下（字段名为实际 JSON 键）：

```json
{
  "schema": "yht-scene-0.1",
  "scene_id": "yht-synthetic-district-v1",
  "crs": "starter-v0-local-m",
  "bounds": [[0, 0, 0], [600, 600, 160]],
  "valid": ["2026-11-05T08:00:00Z", "2026-11-05T09:00:00Z"],
  "terrain": {"kind": "grid-dem", "spacing_m": 20, "size": [31, 31],
               "z": 0, "flat": true, "posts": [{"x": 0, "y": 0, "z": 0}],
               "source_id": "SRC-TERRAIN", "valid": ["...", "..."]},
  "buildings": [{"id": "B-001", "kind": "building", "name": "云塔一号",
                  "footprint": [[30,30],[90,30],[90,90],[30,90],[30,30]],
                  "base_z": 0, "top_z": 120, "height_m": 120,
                  "footprint_source": "SRC-FOOTPRINT",
                  "height_source": "SRC-HEIGHT", "quality": "observed",
                  "valid": ["...", "..."]}],
  "ground_zones": [{"id": "G-001", "exposure_class": "commercial",
                     "exposure_e": 0.975, "consequence_c": 0.8, "q": 0.78,
                     "polygon": [[0,0],[300,0],[300,300],[0,300],[0,0]],
                     "source_id": "SRC-EXPOSURE", "quality": "derived",
                     "valid": ["...", "..."]}],
  "airspace": [{"id": "HL-001", "kind": "height_limit",
                 "footprint": [[330,100],[430,100],[430,170],[330,170],[330,100]],
                 "floor_z": 0, "ceiling_z": 160, "ceiling_m": 60,
                 "state": "published", "authority": "mock-airspace-office",
                 "source_id": "SRC-AIRSPACE", "quality": "assumed",
                 "valid": ["...", "..."]}],
  "coverage": [{"id": "T-00-00", "min": [0,0], "max": [100,100],
                 "complete": true, "source_id": "SRC-FOOTPRINT"}],
  "sources": [{"id": "SRC-HEIGHT", "kind": "lidar-derived",
                "license": "CC0-1.0 (synthetic)", "acquired_at": "...",
                "valid": ["...", "..."], "accuracy_xy_m": 1.0,
                "accuracy_z_m": 1.5, "method": "roof DSM minus flat plane"}],
  "versions": {"scene": "mock-yht-scene-…", "terrain": "...",
                "airspace": "...", "exposure": "...", "sources": "..."},
  "manifest": {"schema": "yht-scene-0.1", "scene_id": "...",
                "content_hash": "…", "counts": {"buildings": 25, "..." : 0},
                "owner": "YHT", "created_at": "..."}
}
```

各实体的键与约束：

| 实体 | 关键字段 | 约束 |
| --- | --- | --- |
| building | `id, footprint, base_z, top_z, height_m, footprint_source, height_source, quality, valid` | 轮廓闭合、简单、面积 > 0；`top_z > base_z`；`height_m = top_z - base_z`；两个来源都必须存在 |
| terrain | `spacing_m, origin, size, z, flat, posts, source_id, valid` | 格网点数与 `size` 一致；`flat` 为真时所有 `z` 相同 |
| ground_zone | `id, exposure_class, exposure_e, consequence_c, q, polygon, source_id, quality, valid` | 多边形合法；`E,C ∈ [0,1]`；`q=E×C`；分区并集恰好覆盖场景一次 |
| airspace | `id, kind, footprint, floor_z, ceiling_z, ceiling_m, state, valid` | `kind` 只能是 `no_fly`/`height_limit`；禁飞体 `ceiling_m=null`；限高体必须有有限 `ceiling_m` 且落在 `[floor_z, ceiling_z]` |
| coverage | `id, min, max, complete, source_id` | 瓦片面积合计 = 场景面积；`complete=false` 时查询必须返回 unknown |
| source | `id, kind, license, acquired_at, valid, accuracy_xy_m, accuracy_z_m, method` | 每个被引用的来源都要能查到；精度可为 null（表示未知），不能编造 |

实体关系：一个 `release` 包含多栋建筑、一个地形格网、多个地面分区和空域体；建筑、地面分区、空域体在存储层统一映射到 `feature` 的 `rid`，再各自扩展几何和属性；`coverage` 与对象通过 `source_id` 关联到来源记录；五层版本按层聚合后再由 `manifest.content_hash` 绑定成一次发布。原型把这些关系放在一份 JSON 中，生产模式按 `storage.md` 的 SQL 表拆分。

`quality` 的四个取值：`observed`（有直接观测）、`derived`（由其他数据推导）、`assumed`（合成或假设）、`unknown`（缺失）。高度为 `unknown` 且 `top_z` 为空时，建筑仍保留在数据集中，但任何可能与之相交的 Q1/Q2 查询返回 `unknown`，不把缺失当成"没有楼"。

## 6. 版本、发布清单与一致性

五个内容层各自独立寻址：`scene`（建筑）、`terrain`、`airspace`、`exposure`（地面分区）、`sources`。每层版本是 `mock-yht-<layer>-<digest>`，`digest` 是该层规范化 JSON 的 SHA-256 前 12 位十六进制。发布清单额外记录五版组合的 `content_hash` 和各类对象计数。

发布流程是：改内容 → `seal()` 重算五版和清单 → `verify_release()` 校验"存下来的版本"与"按当前内容重算的版本"一致。查询时 `preflight` 先比较调用方传入的 `versions` 与快照 `versions`，再校验清单；任何不一致都返回 `unknown`，而不是用旧版本继续算。这条规则直接支撑课程要求的"规划窗内限制有效性"与"查询数据版本一致性"分开验证：时间过滤看 `valid`，版本一致性看 `versions`/manifest，两者不互相替代。

发布对象不可变。动态更新采用"新发布 + 新版本"而不是原地改字段：`results/update-example.json` 中新增 NF-003 后，airspace 版本变化，旧版本查询返回 `version_mismatch:airspace`，新版本查询返回 `forbidden`。

## 7. Q1/Q2 判定语义

两个查询共用同一套预检：

1. 版本字典必须包含五键且与快照一致；否则 `version_mismatch:<layer>`。
2. `verify_release` 必须为空；否则带 `manifest_content_hash_mismatch` 或 `version_mismatch:<layer>`。
3. 窗口必须可解析、start < end、完全落在场景有效期内；否则 `bad_window` 或 `dataset_does_not_cover_window`。
4. 端点必须在场景包围盒内；否则 `endpoint_outside_scene`。
5. 航段包围盒覆盖的瓦片必须存在且 `complete=true`；否则 `no_coverage_tiles` 或 `incomplete_coverage`。

预检不通过时查询状态为 `unknown`（Q1 用 `status=unknown`，Q2 用 `status=unknown`），`reasons` 保留具体原因；任何几何命中都不会把状态降级成"安全"。

Q2（航段状态）对每个候选建筑做完整三维线段–盒判定；对空域体做三维命中（禁飞）或"穿越区域且高于限高"（限高）；对地面分区做二维线段–多边形相交，返回命中的分区及 q。状态优先级是 `forbidden` > `unknown` > `allowed`：只要命中一个建筑或禁飞体，即使还有未知字段，也报 `forbidden`；没有硬命中但有缺失高度/未知 q/未覆盖瓦片，报 `unknown`；全部可判定才报 `allowed`。

Q1（走廊）把航段看作带半径的胶囊：建筑用"线段到三维盒的距离 ≤ 半径"判定；禁飞体要求水平距离和垂直间隙都不超过半径；限高体只要求水平距离不超过半径，然后用"航段最高点 + 垂直半径"对比 `ceiling_m`，接触边界（相等）不阻断，与 ZC 的 `buffer_m` 检查一致。地面分区只报告命中，不单独阻断。状态优先级是 `blocked` > `unknown` > `clear`。半径是水平和垂直共用的保守值，原型用 15 m 和 20 m 做示例。

两类查询都返回 `versions`、`coverage`、`candidates`、`checked` 和 `reasons`。`candidates` 是索引过滤后的候选数，`checked` 是实际做精确判定的对象数；两者用于区分"索引省了多少"和"几何算了多少"。

## 8. 质量规则

发布前运行 `quality.check_scene`，错误阻断发布，警告保留但要求查询返回 unknown。规则编号与含义：

| 规则 | 检查 | 级别 |
| --- | --- | --- |
| STR-001/002/003 | 必填字段存在、类型正确、ID 唯一 | error |
| GEO-001/002/003/004/005 | 轮廓闭合、简单、面积 > 0、在场景内、`top_z > base_z` | error |
| ATTR-001/002/003 | 来源已声明；高度字段一致；q 在 [0,1] | error |
| TIME-001 | 有效期 start < end | error |
| AIR-001 | 空域类型合法；禁飞/限高字段组合正确 | error |
| RISK-001 | 暴露分区并集恰好覆盖场景一次 | error |
| COV-001 | 瓦片面积合计 = 场景面积；`complete` 标志 | error / warning |
| META-001/002 | 来源元数据完整；清单计数与内容一致 | error |
| VER-001 | 存储版本与内容重算版本一致 | error |

12 类故障注入（重复 ID、自交轮廓、未闭合环、顶低于底、缺高度、未知来源、q 越界、瓦片不完整、非法空域类型、缺限高、越界、版本过期）全部被检出；缺高度这类"数据集仍可用但答案不确定"的情况记为 warning，查询必须返回 `unknown`。结果见 [results/quality.json](results/quality.json)。

## 9. 设计决策

| 编号 | 问题 | 选择 | 依据 | 状态 |
| --- | --- | --- | --- | --- |
| YHT-D1 | 内部几何格式 | 自定义 JSON + 局部 ENU 米制 | GeoJSON 固定 WGS-84，局部坐标不能直接标；自定义结构可显式带版本、质量和来源 | 已采用 |
| YHT-D2 | 几何表示 | 建筑用二维闭合轮廓 + `base_z/top_z` 拉伸；空域用轮廓 + 上下界 | 与 ZC 的轴对齐盒兼容，L 形等复杂轮廓可精确保留；不需要完整 B-rep | 已采用 |
| YHT-D3 | 版本粒度 | 五层独立版本 + 清单哈希 | 建筑、地形、空域、暴露、来源的更新频率不同；整包单版本会让无关更新触发全量失效 | 已采用 |
| YHT-D4 | 缺失高度处理 | 保留对象，查询判 unknown | 删除对象会让"未知"变成"无障碍"；保留并显式标 unknown 更安全 | 已采用 |
| YHT-D5 | 时间判定 | 窗口必须被场景有效期完全包含；对象按区间重叠过滤 | 避免"部分覆盖当全覆盖"；超窗不记作无解 | 已采用 |
| YHT-D6 | 质量门禁 | 结构/几何/属性错误阻断发布；未知高度只警告 | 前者是确定错误，后者是数据缺口；两者都不许静默通过 | 已采用 |
| YHT-D7 | 覆盖表达 | 100 m 瓦片 + `complete` 标志 | 与来源分块、缓存和增量更新对齐；单块缺失可定位，不必整场景失效 | 已采用 |
| YHT-D8 | 地形基线 | 保留 31×31 格网，但本基线取平地 | ZC 当前只接受 `terrain_z=0`；保留结构便于后续接入起伏地形而不改模型 | 暂定 |
| YHT-D9 | 存储与索引 | 原型用 SQLite 3D R\*Tree 取候选，再由 Python 精确判定；生产候选是 PostGIS 3D GiST | R\*Tree 原生支持 3 维包围盒，SQLite 零依赖、可复现；PostGIS 与 `ST_3DIntersects`/`&&&` 可直接复用本模型，但需真实库实测 | 已采用（原型）/ 暂定（生产） |
| YHT-D10 | 面向 ZC 的导出 | L 形取包围盒、活动空域裁剪、只接受完整平地；未知风险/覆盖/地形直接拒绝，导出后由 ZC `preflight`/`plan` 复核 | ZC 当前接口只接受轴对齐盒与 `terrain_z=0`；保守包围盒不产生假可行，代价是可能多判障碍；拒绝不支持输入避免把质量缺口伪装成通过 | 已采用 |
| YHT-D11 | 面向 LQ 的导出 | 暴露分区输出 `E`/`C`/`q=E×C` 和整窗 profile；由 LQ `compile_profiles` 重绑版本，YHT 不替 LQ 决定风险模型 | LQ 的接口需要时段化 profile 和后果分量；YHT 只提供几何、来源和代理分解，避免把合成 q 冒充 LQ 的最终风险 | 已采用 |
| YHT-D12 | 导出质量门禁 | 未知 `q`/`E`/`C`、覆盖不完整、非平地或非零基面输入直接 `ValueError`，不丢弃、不改写 | ZC/LQ 当前接口没有 unknown 风险带或未知地形通道；丢弃会变成背景低风险，写 `complete=True`/`terrain_z=0` 会伪造质量。拒绝并让调用方修复源发布，比静默降级可核查 | 已采用 |

## 10. 假设与限制

- 合成建筑轮廓是规则多边形，未覆盖阳台、天桥、地下空间和临时施工物；真实数据接入时要补对象类型和生命周期字段。
- `q` 是土地利用类别对应的暴露代理，不是人口密度、不是伤亡概率；LQ 的风险模型应把它当作输入之一，不能直接当安全结论。
- 地形为平地，因此本模块的 ZC 导出不验证起伏地形；地形格网字段已保留，但坡面、遮挡和离地高度修正未实现。
- 空域数据是模拟参考，不代表任何真实 NOTAM、禁飞区或限高令；`authority` 字段仅为占位。
- 版本哈希用于一致性校验，不是数字签名；能发现内容与版本不匹配，不能证明发布者身份。
- 未实现并发发布和事务性切换；这些属于 ZQO 的架构整合范围，接口约定见 [integration.md](integration.md)。单进程的版本键缓存与 WAL 读写只做了机制验证，见 [storage.md](storage.md) 第 5.1 节。
