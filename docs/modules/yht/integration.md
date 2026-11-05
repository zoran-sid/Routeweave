# 模块交换与集成检查

## 1. 已检查基线

- 检查提交：`de2033a0b13296dcadd991e101a3bee3c1df4596`（LQ 模块交付），2026-11-05。
- 已读：共同口径 `docs/scenario-contract.md`、课程要求、协作规则，以及五人交接记录。ZC、LQ 模块已交付；ZQO、LJ 仍为待开始，没有可供字段核对的共享内容实现或服务。
- 本模块所有场景、来源、暴露值均为合成数据，五类版本用 `mock-yht-*` 标识；没有把模拟值写成实测值。

**模块可交付；与 ZC、LQ 的导出接口已实测，ZQO/LJ 接入待检查。** 已做的检查是：ZC 导出快照通过 ZC `preflight` 并得到可行航线；LQ profiles 通过 `compile_profiles` 编译后仍得到同一条航线；本模块 Q1/Q2 与索引/全扫结果一致；版本不一致返回 unknown。尚未与 ZQO 的发布服务和 LJ 的验收脚本做端到端联调。

## 2. 可直接复用的输入输出

### 2.1 场景对象

完整场景由 `prototype/yht_model.scene()` 生成，`seal()` 后是带版本和清单的只读快照。顶层字段：

| 字段 | 含义 | 使用方 |
| --- | --- | --- |
| `schema` | `yht-scene-0.1` | 所有 |
| `scene_id` | `yht-synthetic-district-v1` | 所有 |
| `crs` | `starter-v0-local-m`（局部 ENU，米，z=0 共同参考面） | ZC、LQ |
| `bounds` | `[[0,0,0],[600,600,160]]` | 所有 |
| `valid` | 数据集覆盖窗口，本基线 08:00–09:00Z | 所有 |
| `buildings[]` | `id/name/footprint/base_z/top_z/height_m/footprint_source/height_source/quality/valid` | ZC、LQ |
| `terrain` | `kind/spacing_m/origin/size/z/flat/posts/source_id/valid` | ZC、LQ |
| `ground_zones[]` | `id/polygon/exposure_class/exposure_e/consequence_c/q/source_id/quality/valid` | LQ |
| `airspace[]` | `id/kind(name no_fly 或 height_limit)/footprint/floor_z/ceiling_z/ceiling_m/valid/state/authority/source_id` | ZQO、ZC |
| `sources[]` | `id/name/kind/license/acquired_at/valid/accuracy_xy_m/accuracy_z_m/method` | LQ、LJ |
| `coverage[]` | 100 m 瓦片 `id/min/max/complete/source_id` | 所有 |
| `versions` | `scene/terrain/airspace/exposure/sources` 五键 | 所有 |
| `manifest` | `content_hash/counts/created_at/owner` | ZQO、LJ |

对象级来源和图层版本是两条线：`buildings[].footprint_source`、`height_source` 回答"这个字段从哪来"；`versions.scene` 回答"这一版场景是什么"。两者都不能单独证明数据正确。

### 2.2 版本与清单

`versions(s)` 对每层内容（排除 `version` 字段）做规范化 JSON 的 SHA-256 前 12 位，得到 `mock-yht-<layer>-<digest>`；`manifest.content_hash` 是五版字典的摘要。`verify_release(s)` 重算并比对，返回 `version_mismatch:<layer>` 或 `manifest_content_hash_mismatch`。

这是内容身份标签，不是签名，也不证明发布者身份。ZQO 接入时应把"版本计算"和"发布审批"分开：版本保证内容未变，审批记录保证谁允许发布。

### 2.3 查询接口

```python
from query import query_segment, query_corridor, preflight

preflight(s, window, a, b, versions, verify=True)
query_segment(s, a, b, window, versions, building_candidates=None, verify=True)
query_corridor(s, a, b, radius, window, versions, building_candidates=None, verify=True)
```

- `window` 是 `{start,end}`，UTC，半开区间 `[start,end)`；`versions` 是五键字典。
- 返回统一含 `status`、`reasons`、`buildings`/`nearby`、`airspace`、`ground`、`versions`、`coverage`、`candidates`、`checked`。
- Q2 状态 `allowed/forbidden/unknown`；Q1 状态 `clear/blocked/unknown`。硬命中优先于 unknown；unknown 不会被写成"安全"。
- `verify=False` 只在调用方已经校验过发布、且同一快照内重复查询时使用；跨发布或持久化读取必须重新校验。

### 2.4 导出给 ZC

`prototype/export_zc.py` 生成 `results/zc-export.json`：

- 建筑 → ZC `obstacles[].box`，只保留与搜索域相交者；L 形 B-023 取轴对齐包围盒，保守。
- 活动空域 → `airspace.restrictions[]`，裁剪到搜索域；`no_fly` 不带 `ceiling_m`，`height_limit` 带 `ceiling_m`。
- 地面分区 → `risk_data.zones[]`，`q` 原样传递，背景 `0.02`；这是代理值，不是 LQ 的最终风险模型。
- `planner_config` 为 step 20/buffer 5/speed 10/lambda 0/length_scale 100，属于导出适配参数，不是 ZC 的默认值。
- 源发布五版写入 `source_release`，ZC 五版由 `scenarios.bind` 生成，二者分开，便于追溯"从哪版 YHT 数据导出"。

### 2.5 导出给 LQ

`prototype/export_lq.py` 生成 `results/lq-export.json`：

- 每个暴露分区 → 一个 LQ profile：`box` 为分区包围盒（z 0–120 m），`periods[0].valid` 取 YHT 发布有效期，`E`/`C` 原样传递。
- profile 的 `source` 使用分区 `source_id`；LQ 用它保留来源，不把来源合并成匿名值。
- `q=E×C` 在 `yht_model` 中已是约束，`quality.check_scene` 会拒绝不满足的分区。
- 调 `compile_profiles(snapshot, query, profiles)` 后重新绑定 ZC 五版，再跑 `preflight`/`plan`/`assess_segment`；输出同时保留 LQ 编译后的五版和原 YHT 五版。

这层适配只证明字段、时段和版本能对齐；`E`/`C` 仍是合成假设，不能当成 LQ 的实测风险模型。

## 3. 与其他模块的接入位置

| 模块 | 接入内容 | 接入后必须检查 |
| --- | --- | --- |
| ZQO | `versions`、`manifest`、`airspace[]` 的有效期/状态/来源；发布切换 | 清单原子切换；组件版本兼容；有效期与读取时间分开；旧版本查询被拒绝而不是混读；空域更新只改 airspace 层 |
| LQ | `ground_zones[].exposure_e/consequence_c/q`、`exposure_class`、`sources[]` 精度、`quality` | E/C 是否仍满足 q=E×C；分区是否恰好覆盖；未知 q 是否让查询 unknown；LQ 的后果模型替换代理 E/C 后重跑风险排序 |
| ZC | `export_zc` 快照、障碍/限制/风险区、`source_release` | 坐标/垂直基准一致；L 形包围盒保守性；限高语义；导出窗口与规划窗口一致；替换几何谓词后重跑几何反例 |
| LJ | `status/reasons/versions/coverage/checked`、发布清单 | 缺失/过期/越界返回 unknown；不可行不标成 allowed；审计能追到五版；异常场景可复现 |

### 3.1 与 ZQO 的版本字段对齐

建议共享五键命名 `scene/terrain/airspace/exposure/sources`，含义与本模块一致：`scene` 是建筑与场景框架，`terrain` 是地形，`airspace` 是限制，`exposure` 是地面暴露，`sources` 是来源表。ZQO 的发布清单应包含组件版本、内容哈希、创建时间、发布状态和审批记录；本模块的 `manifest` 只覆盖前四项中的前三项，没有审批记录。

若 ZQO 采用不同键名，适配层必须显式映射，不能靠字符串相等猜。映射后至少跑一次"旧版本查询新快照返回 unknown"的反例。

### 3.2 与 LQ 的暴露数据对齐

本模块的 `q` 由 `E×C` 构成：`E` 是暴露分量（商业 0.975、住宅 0.75、公园 0.3、公共服务 0.6875、交通 0.9111、政务 0.4），`C` 是后果分量（商业 0.8、住宅 0.6、公园 0.2、公共服务 0.8、交通 0.9、政务 0.8）。两者都是合成假设，`q` 是代理值，不是概率。LQ 接入时应：

- 保留 `q=E×C` 的分解，用 LQ 自己的失效概率、影响范围和后果模型替换 `E`/`C` 的假设值，再按 LQ 的聚合方式重算；
- 保持分区互斥且覆盖全域，否则查询返回 unknown；
- 若 `q` 或 `E`/`C` 变为 null，本模块查询按 unknown 处理，不默认安全；
- 不把 YHT 的 `quality=derived` 当成 LQ 模型的可信度评级；
- LQ profile 的 `box` 用分区包围盒，不是精确多边形；若 LQ 改为精确几何，应重跑边界反例。

已执行：6 个 profile 经 `compile_profiles` 后 `preflight=None`，A\* 仍为 feasible、612.5483 m、risk_proxy 4.2120；6 个分区 q 最大 0.82，低于 LQ 硬阈值 0.9。

### 3.3 与 ZC 的几何对齐

导出已验证：preflight 通过，A\* 可行 612.5483 m、61.2548 s，15 个障碍、NF-002/HL-001 两条限制、4 个风险区；同快照直线 `assess_segment` 为 forbidden（B-001），规划器绕行。限制条件：

- ZC 当前只接受平地 `terrain_z=0`，本导出用平地变体；起伏地形接入前不能声称已联调。
- ZC 端点须在 20 m 网格；本模块原始坐标不吸附，导出查询单独选取网格端点，不改原场景。
- L 形建筑取包围盒会让保守区域变大；若 ZC 改为精确多边形，应重跑 B-023 附近反例。
- 导出只覆盖搜索域 `[[0,0,10],[450,450,120]]`；域外建筑不出现，不能把"域内无解"外推为全场景无解。

## 4. 已执行的集成检查

| 检查 | 命令/位置 | 结果 |
| --- | --- | --- |
| 本模块 31 项测试 | `python3 -m unittest discover -s docs/modules/yht/prototype -v` | 全部通过 |
| 索引与全扫一致 | `evaluate.py` 的 `signature_mismatches` | 200/800/2,400 规模均为 0 |
| ZC preflight | `export_zc.bind_and_check` | 返回 None |
| ZC 规划 | 同上 | feasible，612.5483 m |
| ZC 航段复核 | 同上 | 直线 forbidden，`obstacle:B-001` |
| LQ profile 编译 | `export_lq.write_export` → `compile_profiles` | 6 个 profile，preflight 返回 None |
| LQ 规划 | 同上 | feasible，612.5483 m，risk_proxy 4.2120 |
| 版本不一致 | `query-examples.json` | unknown，`version_mismatch:scene` |
| 更新后旧路线 | `update-example.json` | 新版本 forbidden，旧版本 unknown |

这些是"本模块导出 + ZC/LQ 当前实现"的检查，不等于其他成员最终实现已联调。ZQO 交付后需要按上表重新映射字段并复测；LJ 的验收脚本接入时还要补运行侧检查。

## 5. 发布与查询交错走查（设计）

1. 发布者构建新场景，跑 `check_scene`，有错误则不发布。
2. `seal()` 生成五版与清单，写入新的只读发布；旧发布保持可读。
3. 查询读取清单并固定五版，执行 Q1/Q2；结果标记五版和覆盖瓦片。
4. 发布切换后，新查询用新清单；旧查询结果仍标旧版，不静默改标。
5. 若查询携带的版本与新清单不一致，返回 unknown（`version_mismatch:<layer>`），由调用方决定重查。
6. 下线旧发布前检查审计引用；原型没有引用计数，生产应加 `active/retired` 状态。

## 6. 已知缺口

- 没有与 ZQO 的实际发布服务、LJ 的验收脚本联调；LQ 只做了 `compile_profiles` 的进程内适配检查，没有调用其真实风险服务或审批流程。
- 没有实现缓存、并发、认证和审计落盘；接口只返回审计所需字段。
- 地形只有平地变体；起伏地形、真实坐标系转换和高度基准修正未验证。
- L 形/凹多边形在 ZC 导出中退化为包围盒；精确三维布尔运算未实现。
- 数据许可只覆盖合成数据；接入真实数据前需逐源核对。
