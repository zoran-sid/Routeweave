# LQ v2 对接、审阅与实验范围

## 读取与前棒审阅

开工基线`61fed41bbcea5b40495d8de37d13f19a0b0ba4ed`，包含YHT PR #1与ZQO PR #4的合入。读取AGENTS、v2提示词第3段、任务安排全文、课程/共同约定、五人交接、统一模式、YHT数据字典/章节/操作A证据、ZQO章节/架构/发布原型及LQ v1模型与门禁。

修改前统一模式27项测试通过。实际复跑ZQO完整`run.py`（10/100/1000版、共享/全量、每档30次历史读取），14项事务测试通过，历史内容摘要相同；1000版数据库6,500,352与35,553,280字节，节省81.7%，支持其章节的存储结论；读取微小差异不能推广为稳定的查询加速。证据`zqo-review-before.json`保留原模式摘要。

发布表组的release/组件映射、来源清单、模型/窗口、审计与outbox可以承载治理引用。直接SQL已知旁路实际仍可复现：YHT-V2-05/06交YHT；LQ-V2-01在本棒修复。新增前棒问题ZQO-V2-01：来源版本值或compiler_version为空仍能发布，由独立`review_zqo.py`复现并交ZQO，不改其代码。当前实验使用非空合成标识，不受该无效输入路径影响。

## 新表与既有字段

统一模式从23个实体扩展到30个：新增`risk_model_control/risk_dataset/risk_input_period/derived_risk/quality_check/governance_request/governance_approval`。没有给既有actor/risk_model增加列，旧夹具与发布payload保持兼容。更新schema实体清单并新增`test_governance_v2.py`，CI通过共享入口执行治理回归。

- risk_model已批准/被引用后不可更新或删除；新版本使用新ID。历史模型不通过status原地退役，启停写独立控制表，历史快照不变；受控发布网关拒绝被停用模型用于新发布。风险原型公式保持v1定义。
- risk_dataset绑定逻辑release、exposure组件、模型和完全相同的编译窗口；risk_input_period保存实际时段输入，细时段可以作为源分区静态E/C之外的版本化补充，不能只留下最终q。
- 直接SQL对E/C缺失与q不一致由既有NOT NULL/CHECK拒绝，LQ复核保留；新增模型有效期、草稿状态、时期重叠和全窗覆盖/最大值门禁。服务复用v1 score检查原生输入，未知拒绝生成完整派生层，不改写成零。
- 血缘新增component/dataset端点类型，按类型校验存在性，dataset入边只能引用实际source/model/component，证据不可改写。递归查询用UNION去重定位候选重建范围。
- access_policy新增approve动作；audit_event新增approve/quality/model_control动作。LQ脚本用可信连接身份，不信任SQL中的自报角色；业务只读请求固定为两个视图查询，另有连接authorizer拒绝原表和写SQL。策略实际处理role/resource/read/status/max_sensitivity和机构范围，JSON condition是元数据，不能被描述为已实现的通用策略语言。

创建脚本仅用于新实验库。已有持久库需备份、导出校验后重建/迁移，并核对外键与快照哈希，不能在运行库重复执行CREATE。模型control与审批属于治理元数据，不进入原组件内容哈希；计算公式及参数仍在模型版本中不可变。

## ZC操作C合同（下一棒）

本轮只创建TEMP夹具，未抢先实现ZC正式表。至少需要：

| 未来实体 | 必需字段/约束 |
| --- | --- |
| query_run | query_id主键、release_id外键、actor_id、window_lo/hi；结果不能跨发布混用 |
| route_segment_source | query_id、segment_no、component_id、zone_rid、dataset_id；允许一个航段多个来源；含query_id的索引 |

`op_c.sql`使用这些字段，关联逻辑发布、真实物理owner、来源组件清单与模型。实验明确让R1复用R0:exposure，2段结果均追溯到旧owner。正式接入需将SQL中的TEMP表替换为ZC真实表，并增加外键/发布匹配约束；trace入口要核验认证actor、任务机构与权限，不能直接向客户端开放这条内部SQL。

**LQ-V2-02 修订（2026-11-07，ZC 按用户指示代为修复）**：`op_c.sql` 原要求查询窗口等于数据集窗口，而数据集按发布有效期编译，规划任务是10分钟窗口，正式航线因此追溯为0行。现改为“数据集窗口包含任务窗口”，`run.py` 用10分钟任务窗验证追溯，并以超出数据集窗口的查询验证过滤；结果见更新后的 [governance.json](experiments/results/governance.json)。正式表上的同一规则见 [docs/v2/schema/op_c.sql](../../../v2/schema/op_c.sql)。

使用`compile_dataset`生成派生表，外部时段按zone_id传入LQ原生periods；默认演示从同一组件的exposure_zone读取常量时段。SQL质量结果和封存状态决定是否可供追溯，非validated派生层不参与操作C。新任务窗需新数据集且与对应发布窗匹配，不能只改查询时间。

`publish_approved`是外部发布入口示例：请求先绑定payload/expected/provenance，再由独立reviewer审批，重新验摘要后调用ZQO publish。原始catalog.publish与数据库写连接仅供可信服务/测试，不应直接暴露给业务用户。审计并非自动覆盖所有管理员原始SQL，文件所有者和操作系统权限仍是部署边界。

## LJ及后续复测

内部保留参数：90日热审计、365日归档；仍被历史结果引用的模型/发布/质量/血缘共同保留。当前append-only触发器阻止删除，归档和授权清理没有实施，交LJ补恢复/保留流程。恢复需同时检查risk_dataset/input/derived/quality与审批审计的外键及历史模型，不只检查head。

privacy演示200米网格且每格至少两个合格分区，展示代理为四舍五入值，严禁用于规划判定；它不构成匿名保证。真实人口数据、AI治理准确率和PostgreSQL RLS均没有实测。YHT-V2-05/06未修复前，源层的历史防改写仍有已登记边界，不能由本棒模型修复推定全库不可变已完成。

输出实验结果记录环境、规模、SQL、计划与源码摘要。正式表、审批接口、源版本验证或字段发生变化时，ZC下一棒重跑共享模式测试和本目录run.py；读取ZQO-V2-01修复后重跑review_zqo.py，只有两项明确拒绝后再关闭该项。
