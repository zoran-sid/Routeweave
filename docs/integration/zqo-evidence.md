# ZQO 发布追溯修复与五模块集成证据

日期：2026-11-05（Asia/Shanghai）。起始工作区干净，从 `cc20db8` 快进至远程 `508ca3e`，在 `codex/zqo-traceability-integration` 完成修复。已读取课程要求、共同约定、五人交接、集成问题和对应实现；本轮复用 YHT `81bd270`、ZC `0c2cb23` 与 LJ `508ca3e` 的修复。结果中的 `baseline` 是开工提交，`source_sha256` 标识实际运行的源码；历史 JSON、性能实验和 PPT 保留原基线。

修复与整链路提交：[`1630c27`](https://github.com/zoran-sid/Routeweave/commit/1630c27)。原交付分支为 `codex/zqo-traceability-integration`，现已按用户要求快进合入 `main`。

## 1. 发布追溯修复

| 情境 | 当前结果 | 证据 |
| --- | --- | --- |
| 正常 Q2 | 保留五类查询版本、发布/接收时间、组件来源、限制、源清单与风险编译窗口 | `test_q2_normal_keeps_snapshot_provenance`；整链路正常 Q2 |
| 已知历史发布、任务窗口错误 | 返回 `unknown / risk_window_mismatch`，保留所选历史快照的版本及来源；不会换成当前发布版本 | `test_q2_window_failure_keeps_old_release_versions`；`window_trace` |
| 发布不存在 | `unknown / release_unavailable`；`versions={}`、`provenance_state=unavailable`，源清单和时间为 `null` | `test_q2_missing_release_marks_provenance_unavailable`；`missing_release` |

[修复前失败记录](results/zqo-before.json)与[修复后 owner 审查](results/zqo-after.json)分别保存。旧三模块快照没有 YHT 源清单时，`source_release=null`；它仍可提供已有组件来源，不补造源版本。

## 2. 实际链路与版本映射

`YHT scene/seal → check_scene + export_snapshot/profiles_from_scene → LQ compile_profiles → ZQO prepare_risk/prepare_source → Catalog.publish/pin → ZC plan/assess_segment → LJ validate_result`。

ZQO 的 [source_adapter.py](../modules/zqo/prototype/source_adapter.py) 消费已封存源输入，不自动重新封存、不改写源质量标志。质量错误或警告在本链路阻止发布；导出仍执行 YHT 的能力检查，要求完整覆盖、零基面平地和已知暴露值。风险未知与不完整覆盖不会转成背景低风险。

| 查询快照版本 | 源版本依赖 | 转换与绑定依据 |
| --- | --- | --- |
| `scene`（规划场景） | YHT `scene / terrain / sources` | 保守包围盒、裁剪搜索域、零基面平地；沿用导出坐标与米制 |
| `airspace`（查询空域） | YHT `scene / airspace / sources` | 保留与任务窗口相交的已发布限制；已撤销记录仍保存在源快照 |
| `risk_data`（派生风险） | YHT `scene / exposure / sources` | E/C 时段经 LQ 取整窗最大值，保留 `profile_inputs`；ZQO 绑定 `compiled_window` |
| `risk_model`（风险模型） | 模型配置与转换实现 | LQ 的 `q=E×C`、整窗聚合，以及导出的阈值和影响半径；不冒充 YHT 源图层版本 |
| `planner_config`（规划配置） | 配置与导出实现 | 20米网格、5米缓冲、10米/秒、风险权重0；实现摘要随证据保存 |

两组版本分别记录，内容标识不要求相等。每个发布快照的 `lineage` 保存完整 `source_snapshot`（源输入）、`source_release.versions/manifest`（源版本与清单）、源 SHA-256、投影参数、质量检查、五类 `query_versions`、逐项 `version_mapping` 和编译窗口。原子发布的快照摘要覆盖全部血缘信息，数据库重开后逐项核对。Q1/Q2 回传精简来源字段，完整源对象按 `release_id` 从 `pin()` 取得。

## 3. 整链路验证

复现：`python3 -B docs/integration/five_module.py --output /tmp/skyroute-five-module.json`。保存文件：[完整输入、结果与源码摘要](results/five-module-zqo.json)。源输入位于每个阶段的 `snapshot.lineage.source_snapshot`；数据库重开结果保存发布元数据和快照摘要，并在运行时比较完整快照。

| 检查 | 实际结果 |
| --- | --- |
| 正常输入 | 三个阶段均实际调用五个模块；正常发布为1，Q1可行，路线全部 Q2 航段允许，LJ 当前验收通过 |
| 空域更新 | 在原路线中段添加全高度临时禁飞体并封存新源发布；发布2使旧路线5个航段禁止，新路线避开限制且通过 LJ |
| 路线变化 | 新旧路线长度均为612.5483米，但三维路径不同；风险代理从4.2120变为4.4526。该场景采用距离权重，存在等长绕行，不据此声称路程增加 |
| 撤销限制 | 发布3恢复原路线和4.2120风险代理；查询组件版本与发布1相同，源空域版本仍不同，保留撤销记录 |
| 旧结果验收 | 发布1在新发布出现后标记 `stale`，当前推荐验收失败，显式历史查看通过；发布3与1组件同版也不能放行旧推荐 |
| 发布失败 | 在提交前注入失败；组件/成功审计/通知/发布数量及当前指针不变；失败尝试另行持久记录请求、预期父发布、候选摘要及错误 |
| 历史重开 | 重新建立 Catalog 后，发布1/2/3的完整快照一致，当前指向3，失败审计保留，旧发布可按历史语义查看 |
| 质量故障 | 未知暴露、不完整覆盖、非平地、修改后未封存均被拒绝；另由原审查分别检查 YHT 两个导出入口 |
| 窗口与来源 | 错误风险窗口返回 unknown，仍保留发布1版本、源清单、原编译窗口；不存在的发布明确标为来源不可用 |

整链路11项判据通过；[完整审查](results/audit-after-zqo.json)7项通过；[五模块回归](results/regression-zqo.json)为 ZQO 31、YHT 37、LQ 19、ZC 24、LJ 15，共126项通过。

## 4. 接口变化与验证影响

| 变化 | 兼容与受影响检查 |
| --- | --- |
| Q1/Q2 新增来源字段 | 原 `status/state/reason/versions/release_id` 保留；`provenance_state` 区分是否取得快照，`null` 表示该类来源不存在。ZQO正常、窗口错误及缺失发布回归覆盖 |
| 新增 `prepare_source` | 封存源 → 质量检查 → 导出 → 风险编译 → 血缘；6项来源适配回归覆盖源清单持久化、字段篡改及质量故障 |
| 新增 `failed_attempts` 和 `Catalog.failures()` | 原成功事务计数 `counts()` 的四项含义不变，失败记录独立读取；2项新增测试覆盖回滚后重开和失败审计本身不可用。成功审计写入异常等旧测试继续通过 |
| 历史验收 | 直接调用 LJ `purpose="history"`；当前验收使用默认模式。未修改 LJ、YHT、LQ、ZC 的实现或过滤其错误 |

失败审计在回滚后使用独立连接写入；若写入也失败，会显式抛出同时含原发布错误和审计错误的异常。进程在回滚与记账之间被终止、数据库整体不可写时，需要外部持久日志补充，本轮验证的是进程正常执行的失败处理。

## 5. 剩余事项

已登记的7项缺陷在本轮组合中均通过复核，没有仍需他人修复的阻塞代码项。其他成员可在各自记录中引用本页，确认最新协作状态；本页不代写成员认可或签字。最终报告与 PPT 等整体内容复核后统一定稿。当前证据适用于声明的合成平地、固定任务窗口和本地 SQLite 原型，生产身份服务、外部通知及跨机恢复沿用部署设计。
