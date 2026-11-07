# 最终集成问题清单

## v2 问题（2026-11-06 起）

| 编号 | 负责人 | 问题 | 处理 | 状态 |
| --- | --- | --- | --- | --- |
| YHT-V2-01 | YHT | 缺可执行统一模式与测试（任务安排第4、7.1节） | ZC 按用户指示新增 `docs/v2/schema/`，13项测试 | 已复核通过（YHT，2026-11-07）：合并后 `discover -s docs/v2/schema` 59项通过 |
| YHT-V2-02 | YHT | 操作 A 缺 `EXPLAIN QUERY PLAN` 与索引对比 | ZC 新增访问路径实验与第4.3.1节 | 已复核通过（YHT，2026-11-07）：重跑 6配置×6路径，`mismatched_queries` 全0；N=10000、K=20 四维 R*Tree 37.4 µs |
| YHT-V2-03 | YHT | `coverage_tile`、`terrain_surface` 单列主键在第二次发布冲突 | 主键加 `release_id`（决定 S-01） | 已复核通过（YHT，2026-11-07）：`test_tile_and_terrain_ids_repeat_across_releases` 通过 |
| YHT-V2-04 | YHT | 空域 `state` 原地维护与发布不可变冲突；限高体索引范围错误 | 状态随发布固定；增加禁止范围生成列（S-02、S-03） | 已复核通过（YHT，2026-11-07）：状态/限高相关 schema 测试通过；ZQO 发布/撤销事务按 S-02 实现 |


## v2 第2棒审阅（ZQO，基线 `5ee1a19`）

YHT PR #1（`f05459c`）已合入，GitHub `checks` 为 SUCCESS。修改前13项统一模式测试通过；完整运行 YHT `op_a_index_comparison.py`，6配置×6路径的 `mismatched_queries` 合计0。[独立复跑结果](../modules/zqo/v2/experiments/results/yht-index-review.json)保留修改前 schema SHA；YHT 第4章的性能数值属于其原实验，本轮不替换该结论。字典、SQL、操作 A 的基础接口可承载本轮发布扩展。

| 编号 | 负责人 | 真实缺口与复现 | 完成判据 | 状态 |
| --- | --- | --- | --- | --- |
| YHT-V2-05 | YHT | draft 的 feature 可 UPDATE 到已发布 release；已发布 feature 可后补子类型；已发布版本可新增地形。原 immutable 触发器未覆盖所有 INSERT / NEW 所属版本检查 | 源空间表检查旧/新 owner 和新增子行；拒绝全部已发布内容变更；增加覆盖 feature、子类型、coverage、terrain 的回归，保持合法 draft 写入和原索引实验 | 已修复：`0748f2d`；`feature_immutable_update` 检查 OLD/NEW，子表 INSERT 加 draft-only 触发器；合并后 schema 59项、YHT 42项、ZQO 14项通过，4 条 YHT 探针全部 rejected。验证：`python3 -B -m unittest discover -s docs/v2/schema -v`；`python3 -B docs/modules/zqo/v2/experiments/run.py --counts 10 --output /tmp/zqo.json` |
| YHT-V2-06 | YHT | `source.license` 在发布后仍可原地修改；历史来源跟着改变 | 已引用 source 采用不可变版本编号或真正的历史源表；测试旧发布可重开且来源不变、新来源可合法入库；更新字典与迁移约定 | 已修复：`0748f2d`；`source_provenance_usage` 汇总全部非 draft 引用，`source_immutable_update/delete` 拒绝原地改/删，修订登记新 `source_id`；字典与 S-08 已更新；合并后 schema 59项、LQ 18项通过。验证：`python3 -B -m unittest discover -s docs/v2/schema -v`；`python3 -B docs/modules/lq/v2/experiments/run.py --output /tmp/lq.json` |
| LQ-V2-01 | LQ | 已引用 `risk_model.formula` 仍可原地修改，历史 exposure 的模型解释漂移 | 模型版本不可变或独立版本表；审批/状态调整与计算参数历史分开；测试旧发布模型参数稳定、修订使用新版本 | LQ第3棒已修复；ZC第4棒复核通过（[探针](../modules/zc/v2/experiments/results/lq-review.json)） |

复现脚本：`python3 -B docs/modules/zqo/v2/experiments/run.py --counts 10 --output /tmp/zqo-v2-review.json`。`known_other_owner_defects` 保存5条原始SQL、预期 rejected、实际 accepted 和 `pass=false`，不把这些结果计作通过。完整证据在 [transactions-storage.json](../modules/zqo/v2/experiments/results/transactions-storage.json)。ZQO 的 `snapshot()` 检查关系行摘要，漂移明确报错，不能恢复已被原地改写的数据；该检测不关闭问题。

本轮仅修复自己发布表组的直接插入 published、未完成层发布和 release_layer 迁移到已发布版本旁路，并新增统一模式回归。其他表组实现保持不变。新增组件共享改变查询的版本解析：ZC 使用逻辑 release_id → component → physical owner；直接按 feature.release_id 过滤逻辑新版会漏行，详见 [接口映射](../modules/zqo/v2/integration.md)。

## v2 第3棒审阅与交接（LQ，基线61fed41）

确认ZQO PR #4已合入develop且checks成功。修改前27项统一模式测试通过；完整复跑ZQO的10/100/1000版实验，14项事务回归及共享/全量历史摘要一致。结果见[LQ独立审阅](../modules/lq/v2/experiments/results/zqo-review-before.json)。存储结论支持81.7%空间减少，未推定稳定的读取加速。

- **LQ-V2-01**：新增模型不可变触发器、独立启停表和新ID修订/历史重开测试；模型原地UPDATE/DELETE拒绝，旧发布解释保持。证据见[治理实验](../modules/lq/v2/experiments/results/governance.json)。后续ZC按下一棒审阅流程复核，本记录不代写其认可。
- **ZQO-V2-01（ZQO，P2，待负责人修复）**：catalog.publish只核对source_versions键集合，空版本值或空compiler_version仍可发布。复现命令`python3 -B docs/modules/lq/v2/experiments/review_zqo.py --output /tmp/zqo-provenance.json`；两项当前accepted、退出码1，见[原始结果](../modules/lq/v2/experiments/results/zqo-provenance-review.json)。请ZQO要求上游版本值与编译器为有效非空字符串，并补无效类型/空白值及正常发布回归；保留失败审计与幂等语义。LQ未代改其代码。当前正常实验使用非空合成标识，因此这不是对既有事务结果的反证。
- **ZC-V2-C01（接口需求，非缺陷）**：正式query_run需含query_id、release_id、actor_id、window_lo/hi；route_segment_source需含query_id、segment_no、component_id、zone_rid、dataset_id，并索引query_id。LQ以TEMP表验证操作C，SQL见[op_c.sql](../modules/lq/v2/experiments/op_c.sql)。ZC下一棒在正式表上落实外键、版本一致和访问校验，并复跑SQL；不能把TEMP夹具写成已部署结果服务。
- **保留其他责任**：YHT-V2-05/06仍由YHT修复。LQ新增派生质量、访问及审计约束不覆盖源表的已知旁路，不以本棒测试通过关闭这些项。

## v2 第4棒审阅与交接（ZC，基线 ca2bf58）

确认 LQ PR #6 已合入 develop 且 checks 成功。修改前统一模式45项、LQ 18项、ZQO 事务回归通过；LQ `run.py` 与 ZQO `run.py --counts 10` 复跑一致。12项独立探针见 [lq-review.json](../modules/zc/v2/experiments/results/lq-review.json)，11项通过。

| 编号 | 负责人 | 问题与复现 | 完成判据 | 状态 |
| --- | --- | --- | --- | --- |
| LQ-V2-02 | LQ | （已修复，见“v2 第6棒整合”）`docs/modules/lq/v2/experiments/op_c.sql` 要求 `q.window = dataset.window`。数据集窗口按 LQ 触发器等于发布有效期（2026全年），规划任务是10分钟窗口；同一条已写入正式表的航线，LQ 版追溯0行，ZC 正式版 [op_c.sql](../v2/schema/op_c.sql) 2行。复现：`python3 -B docs/modules/zc/v2/experiments/review_lq.py --output /tmp/zc-lq.json`，探针 `op_c_task_window` | LQ 版改为任务窗口落在数据集窗口内，或说明保留相等合同的理由并与正式表约束一致；复跑探针为通过 | 待 LQ 确认 |
| ZQO-V2-01 | ZQO | 空上游版本值与空 compiler_version 仍可发布 | 见上节 LQ 记录 | 已修复，见“v2 第6棒整合” |
| YHT-V2-05/06 | YHT | 见上节 | YHT PR #5 已开，checks 成功 | PR #5 已于 2026-11-07 合入 develop；ZC 整合时复跑 ZC 9 项与统一模式全部测试通过 |

**ZC-V2-C01 已落实**：`query_run`（query_id、release_id、actor_id、window_lo/hi 等）与 `route_segment_source`（query_id、segment_no、component_id、zone_rid、dataset_id，含 zone 索引）为正式表，外键与发布、窗口、数据集一致性由触发器在写入时校验。

## v2 第6棒整合（ZC，基线 1500683 + LJ）

整合前五棒均已完成：YHT PR #1/#5、ZQO PR #4、LQ PR #6、ZC PR #7、LJ 见下。全量复核脚本 `docs/integration/v2_verify.py` 重跑全部测试、实验与审阅脚本，20/20 组命令符合预期，231 项测试通过；修复 LQ-V2-02、ZQO-V2-01、ZC-V2-02 后于发布前重跑为 233 项（[verification-v2.json](../final/evidence/verification-v2.json)）。

| 编号 | 负责人 | 记录 | 状态 |
| --- | --- | --- | --- |
| INT-V2-01 | ZC | LJ 的 PR #8 以 `main` 为目标，ZC 整合时未核对目标分支即合并，`main` 一度包含未完成的 v2。经用户确认后将 `main` 以 `--force-with-lease` 恢复到 `5d4034b`（临时放开 force push，完成后恢复保护：须 PR、须 `checks`、禁止 force push 与删除）；同一分支经 PR #9 合入 `develop`。CI 新增检查：发往 `main` 的 PR 只能来自 `develop` 或 `hotfix/*`。GitHub 上 PR #8 仍显示为已合并，其内容只存在于 `develop` | 已处理 |
| ZC-V2-02 | ZC | 读取 `op_c.sql` 与 LQ SQL 时显式使用 UTF-8；`review_lq.py` 的授权连接在 `finally` 中关闭；ZQO `catalog.initialize()` 读取 `schema.sql` 时显式使用 UTF-8（一行兼容修订，行为不变，所有成员实验都经此入口） | **已关闭（2026-11-07）**：关闭 UTF-8 模式、C 语言环境（默认编码 US-ASCII，严于 Windows 代码页）下全量复核 20/20、233 项测试通过；同类写入问题在 v1 ZC/ZQO/LQ 脚本与 `audit.py`、`five_module.py` 中一并修复 |
| LQ-V2-02 | LQ | 整合复跑 `review_lq.py`：`op_c_task_window` 仍为 LQ 版 0 行、ZC 正式版 2 行 | **已修复（2026-11-07，ZC 按用户指示代修，记在 LQ 名下）**：LQ `op_c.sql` 改为数据集窗口包含任务窗口；`run.py` 以 10 分钟任务窗验证 2 行、超窗 0 行；`governance.json` 重跑；探针 12/12。修复日志见 [LQ 交接](../handoffs/lq.md) |
| ZQO-V2-01 | ZQO | 整合复跑 `review_zqo.py` 退出码 1，空上游版本值与空编译器版本仍可发布 | **已修复（2026-11-07，ZC 按用户指示代修，记在 ZQO 名下）**：`catalog.publish` 在事务内拒绝空/空白/非字符串来源版本与编译器版本并留失败审计；新增 7 种无效输入回归；`review_zqo.py` 退出码 0。修复日志见 [ZQO 交接](../handoffs/zqo.md) |

## 最新状态（2026-11-06，整合基线2850d89）

ZC读取全部成员修复并独立复测，131项回归、原7项审查、11项整链路和25项风险专项均通过，见[最终证据](https://github.com/zoran-sid/Routeweave/blob/v1.0-algorithm-baseline/docs/final/evidence/verification.json)。报告与PPT已整合。YHT-05为生产候选文档问题，已由YHT修订并提交待复核。下文保留历次问题触发与修复证据，当前状态以总表及最新复核为准。

日期：2026-11-05。检查基线：`cc20db8a6c3d2c92f030c8322cdf067ece249f91`，叠加 ZC 输入校验修复。记录中的“实际”均来自 [审查脚本](audit.py) 与 [原始输出](results/audit.json)。源码 SHA-256 随结果保存，便于核对修复前后版本。

首次审查由ZC处理自身输入校验，YHT、LJ、ZQO分别修复所属问题。本轮在这些修复基础上完成验证，实际状态见下表；成员认可与签字由本人确认。

## 本轮复核（ZQO，2026-11-05）

在 `508ca3e` 上加入ZQO修复和来源适配后，完整审查7项、五模块回归126项、整链路11项判据均通过。修复来源：YHT `81bd270`、LJ `508ca3e`；ZQO修复与集成提交 `1630c27`，详细记录见[集成证据](zqo-evidence.md)和[交接](../handoffs/zqo.md)。D-01已核对LJ实际交接更新。下文“触发/实际”保留原缺陷复现，不代表当前仍失败；历史证据不覆盖。

## 分派总表

P1：影响约束、未知数据或当前推荐验收，合稿采用相关原型结论前处理。P2：影响追溯或异常结果校验，同轮完成。

| 编号 | 负责人 | 优先级 | 问题 | 状态 |
| --- | --- | --- | --- | --- |
| YHT-01 | YHT | P1 | 未知风险区域在两种导出中被丢弃，变成背景低风险 | 本轮复核通过 |
| YHT-02 | YHT | P1 | 导出忽略不完整覆盖及不支持的非平地输入 | 本轮复核通过 |
| YHT-03 | YHT | P1 | 走廊限高检查未计入垂直安全缓冲 | 本轮复核通过 |
| YHT-04 | YHT | P1 | 单独E/C缺失但q保留时，直接ZC导出绕过源质量门禁 | LQ独立复核通过（`621786a`，2026-11-06） |
| YHT-05 | YHT | P2文档 | 生产候选稿使用不存在于所引官方说明的`gist_geometry_ops_3d`名称 | 已修复：`c4ed005`；修复日志见 [YHT 交接](../handoffs/yht.md)（按修复日志关闭） |
| LJ-01 | LJ | P1 | 双方缺失版本字段仍可验收通过 | 本轮复核通过 |
| LJ-02 | LJ | P1 | 已标记 stale 的旧发布结果仍可通过当前推荐验收 | 本轮复核通过 |
| LJ-03 | LJ | P2 | NaN、Infinity、布尔指标及 NaN 耗时未被拒绝 | 本轮复核通过 |
| ZQO-01 | ZQO | P2 | Q2 已知发布的校验失败分支丢失五类版本 | 本轮复核通过 |
| D-01 | LJ | 文档 | 交接仍为待开始，与已提交成果不符 | 本轮复核通过 |
| I-01 | ZQO 主责整合，各模块配合 | 集成 | 五模块整链路和两组版本的来源映射待验证 | 整链路11项通过 |

LQ 本轮未发现独立阻塞缺陷；YHT-01 修复后参与风险输入映射及未知语义复核。ZC 已完成的修复见本页末尾。

## YHT：数据与导出

复现：`python3 -B docs/integration/audit.py --owner YHT`。

### YHT-01：保留未知风险的空间范围

位置：[export_zc.py](../modules/yht/prototype/export_zc.py) 的 `export_snapshot`、[export_lq.py](../modules/yht/prototype/export_lq.py) 的 `profiles_from_scene`。

- **触发**：将合成场景 G-001 的 `q/exposure_e/consequence_c` 设为 `None`，重新 seal；移除建筑和空域以隔离风险条件。检查该区域上方 `[20,20,70] → [40,20,70]` 航段。
- **实际**：`export_zc` 跳过 `q=None` 区域；`export_lq` 跳过缺 E/C/q 的 profile。两条路径都返回 `allowed`、`q_max=0.02`、来源仅有 `background`。
- **影响**：源数据明确未知，下游却把区域作为已知背景低风险处理。
- **修复要求**：保留未知区域及来源，让下游返回 `unknown`；或在导出时明确拒绝该输入。缺失源数据不能由默认背景覆盖。
- **验收**：两个导出入口分别测试，不能用一个入口的提前拒绝掩盖另一个入口丢失数据。补充局部缺失与正常已知输入回归，核对 LQ 编译后及 ZC Q2 的状态和来源。

### YHT-02：导出必须继承覆盖与地形质量约束

位置：[export_zc.py](../modules/yht/prototype/export_zc.py) 的 `export_snapshot`，尤其 `scene.complete=True` 与 `terrain_z=0.0`。

- **触发**：分别把 `coverage[0].complete` 设为 `False`；或将 `terrain.flat=False`、`terrain.z=20` 且所有地形点高度设为 20。每次修改后重新 seal，再导出和运行 ZC `preflight`。
- **实际**：两个输入均导出为 `complete=True`、`terrain_z=0.0`，`preflight` 返回 `None`，即通过校验。
- **影响**：覆盖质量被提升为完整，不支持的地形被默认为零高程，破坏避障输入假设。
- **修复要求**：校验源数据质量和当前导出能力；不完整覆盖保留未知语义，不支持的地形明确拒绝。项目可以继续采用平地原型，无需为本项扩展地形算法。
- **验收**：两个故障输入分别被明确拒绝或导致 `unknown`；原有完整平地输入保持可用。记录支持的地形类型和高程约束。

### YHT-03：限高判定计入走廊安全包络

位置：[query.py](../modules/yht/prototype/query.py) 的 `query_corridor`，`height_limit` 分支目前比较 `zhi > ceiling_m`。

- **触发**：无建筑干扰，使用既有限高区 HL-001；航段 `[350,120,58] → [400,120,58]`，半径 5 米，限高 60 米，时间窗 `2026-11-05T08:05:00Z` 至 `08:15:00Z`。
- **实际**：YHT 返回 `clear`；相同场景和 5 米缓冲下 ZC 返回 `forbidden`。58 米中心线加 5 米包络已超过 60 米上限。
- **修复要求**：按共同约定对完整航段及其安全包络检查限高，统一碰触边界的含义。若中心线查询另有用途，在接口中明确区别。
- **验收**：新增包络低于、接触、超过限高的案例，核对 YHT 走廊结果与 ZC 对应航段判定；保留禁飞和建筑几何回归。

## LJ：运行验收

复现：`python3 -B docs/integration/audit.py --owner LJ`。

### LJ-01：五类版本需完整有效

状态：**本轮复核通过**。证据：`python3 -B -m unittest discover -s docs/modules/lj/prototype -v`
（15 项通过）及 `python3 -B docs/integration/audit.py --owner LJ`（LJ-01 PASS）。

位置：[acceptance.py](../modules/lj/prototype/acceptance.py) 的 `validate_result`。

- **触发**：使用真实 ZC 可行结果，将 `result.versions` 与 `current_versions` 都设为 `{}`。
- **实际**：逐项 `.get()` 比较得到 `None == None`，返回 `pass`。
- **修复要求**：双方均为有效字典，五个必需键齐全，值为有效非空版本字符串，再比较内容；无效输入返回明确失败。
- **验收**：双方为空、缺同一键、单边缺键、空值及错误类型均失败；五类有效版本一致通过、任一不同失败。

### LJ-02：区分当前推荐与历史结果

状态：**本轮复核通过**。证据：同一组件版本的 release 1/2 场景由
`python3 -B docs/integration/audit.py --owner LJ` 实测为 LJ-02 PASS；回归测试明确要求
`freshness=stale` 只有 `purpose="history"` 可查看，不能作为当前推荐通过。

位置：[acceptance.py](../modules/lj/prototype/acceptance.py) 的 `validate_result`，与 ZQO 的发布查询结果衔接。

- **触发**：用 ZQO `Catalog` 连续发布相同组件快照为 release 1 和 2，再用固定的 release 1 查询。组件五类版本相同，但发布编号已更新。
- **实际**：ZQO 明确返回 `freshness=stale`、`release_id=1`、`observed_head=2`，LJ 仍返回 `pass`。
- **修复要求**：当前推荐验收检查发布新鲜度及发布身份；组件版本相同不能覆盖已知的 stale 状态。历史结果可以保留用于追溯，但应使用明确的历史查看语义。
- **验收**：同组件版本的新发布也使旧推荐需要重验；当前发布通过；stale/unavailable 不能作为当前推荐通过。若调整验收接口，同步说明独立 ZC 原型结果与已发布结果的适用方式。

### LJ-03：指标与耗时必须为有限有效数值

状态：**本轮复核通过**。证据：覆盖三个指标和耗时的 NaN、正负无穷、布尔值、
负数及预算超限回归；`python3 -B docs/integration/audit.py --owner LJ` 中 LJ-03 PASS。

位置：[acceptance.py](../modules/lj/prototype/acceptance.py) 的 `validate_result`。

- **触发**：在正常可行结果中分别将 `metrics.risk_proxy` 改成 `NaN`、`Infinity`、`True`，或将 `elapsed_ms` 改成 `NaN`。
- **实际**：四种情况全部返回 `pass`。现有类型和小于零判断不能拒绝这些值。
- **修复要求**：数值指标为有限、非负的实数，排除布尔值；耗时检查使用相同的有效数值规则并遵守执行预算。
- **验收**：覆盖各项指标及耗时的 NaN、正负无穷、布尔值、负数和正常值；正常值与超预算值按既定语义判断。

### D-01：更新交接为实际成果状态

位置：[LJ 交接](../handoffs/lj.md)。

`d84a565` 已提交 LJ 模块、8 项测试和展示材料，但交接仍写“待开始”“暂无成果”。请 LJ 补充真实成果链接、已读取版本、测试结果、当前集成问题及下一步，便于其他 agent 正确读取状态。只填写本人的实际工作和已验证结果。

## ZQO：发布与整合

复现：`python3 -B docs/integration/audit.py --owner ZQO`。

### ZQO-01：Q2 校验失败仍需保留已知版本

位置：[publication.py](../modules/zqo/prototype/publication.py) 的 `Catalog.status`，成功 `pin` 后 `validate` 的异常分支。

- **触发**：通过 `prepare_risk` 编译固定时间窗并发布；将 Q2 的查询结束时间延长，再查询同一已知发布。
- **实际**：返回 `state=unknown`、`reason=risk_window_mismatch`、`release_id=1`，缺少已知快照的 `versions`。
- **影响**：异常结果无法按统一 Q2 字段直接追溯五类输入，正常与失败分支输出不一致。
- **修复要求**：已读取快照时保留其五类版本及可用来源字段；发布不存在时明确区分无法获得的版本。
- **验收**：正常、风险窗口不匹配及发布不存在分别测试；已知发布的失败结果仍绑定其原版本，不改写为当前新版本。

### I-01：补齐五模块整链路与来源映射

这是集成完成项，当前证据为各模块测试和部分成对接入；本轮不将其记作额外已复现代码缺陷。ZQO 负责总体数据流，YHT、LQ、ZC、LJ 按接口配合，成员修复可并行开展。

完整链路：YHT 合成源及质量门禁 → LQ 时间窗风险编译 → ZQO 原子发布 → ZC Q1/Q2 → LJ 当前结果验收。

重点保留两组不同含义的版本及映射：

- YHT 源版本：`scene / terrain / airspace / exposure / sources`。
- 查询快照版本：`scene / airspace / risk_data / risk_model / planner_config`。

源清单应随发布保存或有不可变引用，使查询版本可追溯至源版本和风险编译窗口。已有导出中的 `source_release` 等元数据应贯通，不能仅给字段改名或假定两组版本相等。

完成判据：

1. 正常链路实际消费各模块输出，保存输入、来源、发布编号、Q1/Q2 和 LJ 验收结果。
2. 空域更新后旧路线失效，新路线按新发布生成；撤销限制后重新优化。
3. 发布失败有审计且当前指针不被错误切换；重新打开数据库后可读取历史发布。
4. 覆盖 YHT-01/02 的质量故障、LJ-02 的 stale 结果和 ZQO-01 的窗口错误。
5. 各自更新当前集成状态；历史实验基线保留。若接口调整，记录字段映射及受影响测试。

## ZC：本轮已修复

位置：[planner.py](../modules/zc/prototype/planner.py)、[test_planner.py](../modules/zc/prototype/test_planner.py)。

- Q2 现在校验实际传入的 `a/b` 航段端点。维度错误、非数值、布尔值及非有限数值返回 `unknown / invalid_segment_endpoint`，域外端点返回 `unknown / segment_outside_search_domain`，保留版本与时间窗。
- 时间解析拒绝非字符串输入，交由既有预检返回 `unknown`，避免 `None` 等值触发未处理异常。
- 新增 3 项回归测试，ZC 共 24 项通过；五模块共 102 项通过。原有 12 情境性能结果保留其原始源码摘要与实验基线。

交接与证据见 [ZC 工作记录](../handoffs/zc.md) 和 [回归原始日志](results/regression.json)。

## 2026-11-06 LQ风险接口复核新增：YHT-04

检查基线`6567a583969d8131e850c34222ea8005a65c66ef`。上述7项既有问题与I-01整链路复跑通过；本节为新增的部分缺失输入，不覆盖历史通过记录。

- **负责人**：YHT。LQ仅新增复现、证据与交接，不修改YHT实现。
- **位置**：`export_zc.require_exportable/export_snapshot`。当前只检查q有限且在范围内，没有检查源E/C是否缺失；`profiles_from_scene`和ZQO的`prepare_source`分别会拒绝。
- **触发**：创建YHT场景，去除建筑及空域以隔离风险。分别将G-001的`exposure_e`或`consequence_c`单独设为None，保留q=0.78，重新seal；直接export_snapshot后交给ZC assess_segment检查`[20,20,70]`至`[40,20,70]`。
- **实际**：两种输入均为`allowed / checked`、q_max=0.78、risk_proxy=0.156，sources为background和G-001。源的E/C缺失已被quality判为错误，但调用直接导出不经过该门禁。同样输入经LQ导出抛ValueError，经ZQO prepare_source在quality阶段拒绝。
- **影响与范围**：默认五模块完整链路已有质量门禁，不受此旁路影响；独立YHT→ZC导出仍接受无法按当前q=E×C来源核验的输入。不能用完整链路拒绝来证明独立入口也拒绝。
- **负责人处理与验收**：在直接入口拒绝单独缺失E/C，或保留未知区域与来源交给ZC返回unknown；分别测试E缺失、C缺失、q缺失、全部缺失及正常已知输入。LQ导出入口必须独立执行，不能被另一个入口的拒绝掩盖。
- **复现**：`python3 -B docs/modules/lq/prototype/review_integration.py --output /tmp/lq-risk-review.json`，25项中23项通过，`unknown_E_export_zc`和`unknown_C_export_zc`失败，退出码1。原始[专项证据](../modules/lq/results/integration-review-20261106.json)包含输入空间范围、source_id、源版本、响应和代码摘要；[本人记录](../handoffs/lq.md)与[集成说明](../modules/lq/integration.md)注明实际状态。

待YHT提交后由LQ读取修复版本再复测；此处不代写YHT认可，也未关闭新项。

YHT修复（提交`1862ab44ca094bc493fab6fc7ce0cd6f51f2e2db`，`fix(data): verify exposure factors before zc export`）：`export_snapshot`在`require_exportable`之后调用新增的`require_verifiable_exposure`，逐分区要求`E`/`C`/`q`均为[0,1]内有限数且`|q-E×C|<=1e-9`；缺字段或越界抛`ValueError:unknown_or_invalid_exposure:<id>`，三者不一致抛`ValueError:inconsistent_exposure:<id>`。LQ的`profiles_from_scene`继续独立校验，不依赖该门禁。新增5项回归测试，YHT共42项通过；`docs/integration/audit.py --owner YHT`三项通过；YHT本地运行LQ的`review_integration.py`为25/25通过。该结果只证明YHT入口按验收要求拒绝，LQ仍需在修复版本上独立复测并确认。

### YHT-04：LQ独立复核通过（2026-11-06）

读取实际修复`1862ab44ca094bc493fab6fc7ce0cd6f51f2e2db`，检查基线`621786a7a0816c9c3582026a1ca78b440d9fe6bc`。LQ运行原专项脚本25/25通过，原`unknown_E_export_zc`与`unknown_C_export_zc`现在均明确拒绝，返回`unknown_or_invalid_exposure:G-001`。LQ导出与ZQO质量门禁的独立入口仍通过，原生未知、时间缺口、阈值和来源映射检查保持通过。

五模块131项回归、原7项审查及整链路11项均通过。证据：[修复后风险专项](../modules/lq/results/integration-review-post-yht04-20261106.json)、[模块日志和集成摘要](../modules/lq/results/integration-checks-post-yht04-20261106.json)。据本轮独立复测关闭YHT-04，保留上文触发条件和修复前失败证据供追溯。该确认是LQ执行的接口复核，不代替其他成员的个人认可或生产部署验收。

## YHT-05：PostGIS n维GiST操作符类名称（2026-11-06）

- **负责人／优先级**：YHT，P2文档。检查基线`2850d89`。
- **位置**：[storage.md](../modules/yht/storage.md)第25行比较表、第129行生产建议，均写为`gist_geometry_ops_3d`。
- **依据**：[PostGIS 3.5官方索引说明](https://postgis.net/docs/manual-3.5/using_postgis_dbmanagement.html#build-indexes)给出的n维GiST操作符类是`gist_geometry_ops_nd`。默认GiST索引通常采用二维包围盒；应区分带Z几何、n维候选过滤和精确三维几何判断。
- **影响**：当前说明会使后续部署者采用错误的索引定义；SQLite R*Tree原型及本轮131/7/11/25验证不受影响。整合报告保留PostGIS为后续候选，不复用该名称或声称已做实库验证。
- **修复要求**：YHT核对目标PostGIS版本，更新上述名称及其配套查询说明，引用官方出处；如提供SQL示例，应明确目标版本和是否实际执行。无需为了本项临时部署数据库。
- **验收**：模块全文不再出现未经核实的操作符类名称；区分包围盒过滤与精确几何语义；更新本人交接并提交。整合方读取提交后复核、关闭本项。本轮未代改YHT文件或代写其认可。
- **修复（YHT，2026-11-06）**：提交`c4ed005`（`docs(data): correct PostGIS 3D index operator class`）。[storage.md](../modules/yht/storage.md)比较表与生产建议均改为`gist_geometry_ops_nd`，明确默认二维GiST包围盒、n维候选过滤和`ST_3DIntersects`精确判定三者的区别；示例按PostGIS 3.5官方说明标注，未在本机执行。[references.md](../modules/yht/references.md)补充第14条官方出处。
- **修复验证**：YHT模块全文不再出现`gist_geometry_ops_3d`；42项原型测试通过，`audit.py --owner YHT`三项PASS，SQLite原型和既有131/7/11/25验证不受影响。当前状态：已修订待复核。

## ZC-V2-02：Windows 实验复现与资源清理（2026-11-07）

- **负责人／优先级**：ZC，P2。LJ 第5棒审阅，不修改 ZC 的查询或性能结论。
- **复现**：在 Windows Python 3.14、默认系统编码下运行
  `python -B docs/modules/zc/v2/experiments/test_query.py -v`，ZC 的
  `catalog.initialize()` 对 `schema.sql` 调用未指定编码的 `Path.read_text()`，
  因 UTF-8 字节触发 `UnicodeDecodeError`；`review_lq.py` 随后因数据库连接未及时
  关闭，在临时目录清理时触发 `PermissionError`。
- **整合修复（ZC，2026-11-07）**：见上方“v2 第6棒整合”中 ZC-V2-02 一行，已在非 UTF-8 语言环境下全量复核后关闭。
- **当前处理**：使用 `python -X utf8` 后，统一模式 18 项和 ZC 查询回归 9 项通过；
  取数实验的正确性检查为 0 不一致。该环境开关是本轮 LJ 实验的复现前提，但不关闭
  ZC-V2-02。
- **完成判据**：实验源码显式按 UTF-8 读取仓库 SQL，所有打开的 SQLite 连接在临时
  目录退出前关闭；在 Windows 默认编码下重新运行相关测试和审阅脚本通过。
- **影响**：不改变 ZC 的访问路径、缓存失效或性能数值；只影响 Windows 的可复现性和
  清理可靠性。LJ 恢复脚本已显式使用 UTF-8，并独立通过正常恢复与截断故障检测。
