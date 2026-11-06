# 跨模块接口与检查

## 首次交付检查（历史基线）

读取完整课程材料、共同约定、五人交接、ZC设计/评估/接口/原型/结果与PPT文字，基线为`be027dc9c94d2416836f2b8f24fe4e3fee81000c`。其他三模块此版本只有任务记录，不能记作已集成。

`compile_profiles(snapshot, query, profiles)`返回深拷贝的`(snapshot, query)`，保留ZC五类版本语义，使用其内容摘要绑定函数。风险数据附`profile_inputs`作为血缘，新增`risk_model.source`以区分LQ处理含义。失效版本检查继续由ZC执行。

输入profiles为非空区域列表，每个区域含唯一id、3D盒表达的水平范围、source和periods；每个period含带时区的半开valid区间、E与C。实际风险计算只用盒的x/y，z不影响地面包络。输入格式可参考`prototype/test_risk.py:region`。E或C为null产生unknown；无profiles或非法数值由`evaluate`返回unknown。

输出`risk_data.zones`仍使用ZC的`id/box/q`字段。时间覆盖完整的区域编译为最大已知q；缺口编译为已知q加独立unknown区，避免丢失已知硬危险。显式背景覆盖、来源、窗口与五类版本保留。当前合成默认参数不提供公开人口密度到E的映射。

| 负责人 | 可复用内容 | 映射/验收 |
| --- | --- | --- |
| ZC | `compile_profiles`与`assess_segment`，19项测试和三权重联合输出 | r仍为长度/100×q，非负可加，阈值及未知优先级与现有代码一致。21项原测试通过，无需修改搜索 |
| YHT | exposure_profile、risk_model、source_catalog、risk_assessment字段 | 换成真实几何时检查水平投影包络、单位、时间覆盖与索引候选完整性；真实源缺失不得套用合成背景 |
| ZQO | 版本编译、五类引用、不可变对象及发布规则 | 内容摘要不是事务发布；业务清单仍需原子切换，读取时校验数据/模型兼容。变化后重验路线 |
| LJ | 治理验收清单、unknown原因、策略模拟 | 实际角色鉴权、审计落库、故障恢复另行运行，不能把can_publish纯函数当作生产授权服务 |

新模型若改成累计风险硬预算、路径历史相关风险或负权收益，需扩展规划状态并重新证明搜索条件。保持现有可加代理时无需迁移现有ZC输入；LQ适配为新增入口，不覆盖ZC的原始场景和历史结果。

## 2026-11-06：最终集成风险接口复核

### 读取版本与同步

本轮基线为共享`main`的`6567a583969d8131e850c34222ea8005a65c66ef`。已读最新AGENTS、课程要求、共同场景、项目说明、异步协作、五人交接及`docs/integration/README.md`和`issues.md`，并检查YHT两种导出、LQ编译、ZQO来源适配/窗口校验/发布与ZC航段评估代码。当前历史中对应修复为YHT `525c1ee`、ZQO `f3d3378`、LJ `2431f18`、ZC `7eebcae`；部分旧交接中的提交号来自改写前历史，以本轮完整基线及结果中的源码SHA-256为准。

开工工作区干净；fetch发现远程强制更新且与原本地主线无共同祖先。先建立`backup/lq-before-integration-20261106`保留旧主线，再让本地`main`跟踪最新远程内容，没有把旧历史强行合入或推送覆盖远程。提交前fetch仍为上述基线。

### 实际链路与风险语义

| 检查对象 | 本轮实际结果 | 适用边界 |
| --- | --- | --- |
| YHT未知q及E/C/q全空 | 两个导出入口各自显式抛ValueError，完整prepare_source链路拒绝 | 没有生成一个unknown航段结果，而是在导出/质量门禁停止。来源区域ID保留在拒绝原因，输入几何与来源保存在专项证据，输入没有被修改 |
| 仅E或C缺失、q仍已知 | LQ导出拒绝，ZQO质量门禁拒绝；YHT直接ZC导出仍allowed | 发现YHT-04，未代修；不能用完整链路的拒绝掩盖直接入口的旁路 |
| LQ原生profile中E/C为None | 编译后保留同box/source的`:unknown`区域，profile_inputs保留原记录；ZC Q2返回unknown并列出区域ID | 当前YHT选择拒绝，所以这组验证从YHT已知输入生成合法结构后注入未知，属于LQ/ZC边界验证，不冒充未知源通过YHT全链路 |
| ZC原生q=None | 返回unknown，sources含原区域ID | 当前YHT拒绝q=None，直接在ZC输入注入用于检查评估内核 |
| 半窗时间覆盖缺口 | LQ生成未知标记，ZC返回unknown，box/source保留 | 背景不能填补区域时间缺口 |
| 发布查询窗口 | 原窗口允许，延长、平移及缩短窗口均unknown/risk_window_mismatch | ZQO当前要求时间区间相同，不仅是“编译窗包含查询窗”；即使子窗也必须重新编译 |
| 阈值与偏好 | q=0.9在lambda=0/8时均forbidden；q=0.7仍按长度/100×q计算代理和目标 | 沿用0.9、5米影响包络与非负可加定义，保持合成代理语义；没有改成概率或累计硬预算 |
| 来源与数据库重开 | 原始YHT场景/清单/摘要、profile来源、查询五类版本、Q2及编译窗口一致 | 读取实际prepare_source输出并发布到临时SQLite，再重开读取；完整城市规划另由整链路11项检查覆盖 |

`compile_profiles`本身按传入query窗口计算最大值，但原始输出不提供独立的复用窗口门禁。发布路径必须走`prepare_risk`（或`prepare_source`内部包装），将`risk_data.compiled_window`写入后重新绑定版本，交给ZQO validate检查。不得只改查询窗口后直接复用原生LQ编译快照。

### I-01实际字段映射

YHT原始五类版本为`scene/terrain/airspace/exposure/sources`。LQ的profile保留`id/box/source/periods(E,C,valid)`，其中source对应YHT的source_id，输入时段采用源发布valid。LQ最大值计算后，profile_inputs与区域来源一起纳入risk_data的内容版本。编译窗采用实际任务窗08:05–08:15 UTC，区别于更长的源有效区间。

ZQO快照的`lineage.source_release`保存原版本与manifest，`source_snapshot`保存原场景，`source_sha256`核对其摘要；`query_versions`和`version_mapping`指向查询五类版本。risk_data映射到源`scene/exposure/sources`，risk_model和planner_config是派生模型/配置，不能声称它们等于某个源数据版本。Q2的正常和窗口错误分支均返回原versions、source_release及compiled_window。重开数据库后映射保持一致，已在[source_mapping_and_reopen](results/integration-review-20261106.json)记录实际输入、profile、lineage及响应。

`risk_data.source=synthetic-lq-v1`是当前变换标签；实际YHT来源需沿zones.source、profile_inputs.source与发布lineage解析，不能仅凭顶层标签认定数据由LQ采集。ZC响应sources提供区域ID，通过这些记录回溯source_id。

### 运行命令与证据

```sh
python3 -B -m unittest discover -s docs/modules/lq/prototype -v
python3 -B -m unittest discover -s docs/modules/yht/prototype -v
python3 -B -m unittest discover -s docs/modules/zc/prototype -v
python3 -B -m unittest discover -s docs/modules/zqo/prototype -v
python3 -B -m unittest discover -s docs/modules/lj/prototype -v
python3 -B docs/integration/audit.py --output work/lq/audit-risk-review.json
python3 -B docs/integration/five_module.py --output work/lq/five-module-risk-review.json
python3 -B docs/modules/lq/prototype/review_integration.py --output work/lq/risk-review-new.json
```

- 模块测试：LQ19、YHT37、ZC24、ZQO31、LJ15，共126项通过。
- 原审查7项及五模块整链路11项通过，摘要/日志见[本轮集成检查](results/integration-checks-20261106.json)。历史性能数据未重算。
- [新增风险专项](prototype/review_integration.py)：25项中23项通过，2项为YHT直接导出的单独E/C缺失；退出码1用于保留可复现失败，不将其记成通过。结果及源码摘要见[风险专项原始证据](results/integration-review-20261106.json)。

### 发现与后续

没有发现需要修改LQ模型或实现的确认缺陷。本轮只新增复核脚本、证据和说明，不修改其他成员代码。YHT-04已写入共享问题清单交给YHT：直接export_snapshot应在单独E/C缺失时明确拒绝，或保留unknown区域及来源；当前严格prepare_source的质量门禁继续有效。

读取YHT后续修复提交后，重跑专项脚本中全部独立导出用例及模块/受影响审查，再决定是否关闭YHT-04。若YHT改为导出unknown而非拒绝，还需确认输出保留box/source、LQ编译和ZC Q2仍unknown。编译窗口、profile/source字段、阈值/聚合或发布lineage发生变化时，重跑时间缺口、发布窗口与来源重开检查。最终报告/PPT和生产部署验证不属于本轮改动。

## 2026-11-06：YHT-04修复后的独立复测（最新）

本轮读取共享主线`621786a7a0816c9c3582026a1ca78b440d9fe6bc`，增量为YHT修复`1862ab44ca094bc493fab6fc7ce0cd6f51f2e2db`及其状态交付。工作区干净，从`c357ac3`快进同步；没有改动LQ或其他成员的模型/实现。

直接ZC导出现在在`require_exportable`之后执行`require_verifiable_exposure`：E/C/q须为[0,1]内有限数且q与E×C一致。LQ入口保留自己的独立检查。风险专项的E/C单独缺失、q缺失、三者全缺失各路径都明确拒绝；原生LQ未知和时间缺口仍按unknown传递并保留范围/来源。正常输入、硬阈值与优化代理、ZQO编译窗口绑定及来源重开映射继续通过。

| 检查 | 本轮实际结果 | 证据 |
| --- | --- | --- |
| 风险专项 | 25/25通过，退出码0；此前失败的2项均明确拒绝 | [修复后原始结果](results/integration-review-post-yht04-20261106.json) |
| 模块回归 | LQ19、YHT42、ZC24、ZQO31、LJ15，共131项通过 | [日志及摘要](results/integration-checks-post-yht04-20261106.json) |
| 原问题审查 | 7项全部通过 | 同上audit字段 |
| 五模块实际链路 | 11项全部通过 | 同上five_module字段 |

复现命令沿用上节，把专项输出改为`--output work/lq/risk-post-yht04.json`，audit/five_module也分别使用新路径，避免覆盖历史结果。YHT新增的5项测试包含E缺失、C缺失、q缺失、三者乘积不一致及LQ独立入口缺失检查；本轮实际运行了完整42项YHT测试。

YHT-04由LQ独立复测后确认通过，先前23/25结果仍表示`6567a58`上的历史缺陷。当前复核没有新增阻塞项。只有风险相关代码、输入定义或发布追溯再次变化时才需增量复测；报告合稿和生产验收属于单独事项。
