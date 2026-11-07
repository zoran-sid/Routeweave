# LJ 的工作记录

项目：SkyRoute。最后更新：2026-11-07（Asia/Hong_Kong）。

| 项目 | 当前安排 |
| --- | --- |
| 成员 | LJ，成员1 |
| 负责方向 | 运维保障与验收支持 |
| 展示安排 | PPT 第9–10页 |
| 技术成果状态 | v1 模块可交付；v2 恢复与验收交付完成 |

## v2 任务（2026-11-06 重组，第5棒，待开始）

| 项目 | 内容 |
| --- | --- |
| v2 数据库重点 | 运行保障与恢复验收；权衡汇总 |
| 报告章节 | 3.3、8.2–8.3 |
| PPT | 第9–10页 |
| 开工条件 | ZC 的 v2 PR 已合入 `develop`；第一步审阅 ZC |
| 分支 | `lj/v2-recovery`，从 `develop` 创建，PR 到 `develop`，checks 通过后自行合入 |
| 交付位置 | `docs/modules/lj/v2/`：`section.md`、`slides.md`、`references.md`、`experiments/`；`docs/v2/schema/` 中本人表组 |
| 提示词 | [v2 提示词](../v2-prompts.md) |

具体任务与验收见[任务安排](../team-tasks.md)第4–10节。以下 v1 记录保留为证据。

## 主要职责

- 设计模拟系统的运行监控、日志记录、数据更新异常处理和恢复安排。
- 配合核对数据版本、航线查询结果和异常提示，形成可复用的验收说明。
- 从核心查询和模拟异常独立起草运维与验收说明，后期按其他模块的新成果补充核对。

## 交付与协作

主要交付：运维保障与验收说明，配合必要的情境检查记录及2页 PPT。

协作关系：与 ZQO 对齐系统运行和更新流程，与 LQ 对齐审计及权限要求，与 ZC 配合后期验证。

独立起点：先依据 Q1/Q2 与版本定义整理正常查询、数据缺失和更新失败的监控及验收说明，部署方式暂以假设表示。

成果入口：[LJ 模块](../modules/lj/README.md)，图表、样例和验证材料在同目录。

后续对齐：读取 ZQO 的发布与恢复流程、LQ 的审计要求、ZC 的结果状态与验证方法，按实际差异修订本模块。

## AI 自主完成范围

自行研究、比较并决定：监控状态、日志与告警信息、异常恢复动作和验收判据；用模拟情境完成轻量走查。

即使其他成员尚未提交，也应补齐最小模拟输入，完成本模块的方案、决定依据与验证说明。读取新成果后主动检查和修订，记录核对的版本；无需等待 ZQO 或其他成员批准。详细规则见 [AI 自主研究与协作](../agent-collaboration.md)。

## 本轮协作状态

- 已检查提交：共享 `main` 最新提交 `42948c0f6d62a8746ba5ba30be2fb80130f0ca20`；
  集成问题基线 `cc20db8a6c3d2c92f030c8322cdf067ece249f91`，并读取 ZQO 发布提交
  `130f7b03bda513baaac306f6666904f0dc05009c`、ZC 输入修复 `0c2cb23852c7e075660c0e717c939d60afb8d846`
  及五人交接。当前副本无 `.git` 元数据，未执行本地合并或推送。
- 已复用的其他模块成果：ZQO `Catalog.query` 的 `freshness`、`release_id`、
  `observed_head` 字段；ZC 的五类版本与 Q1 状态；共同约定的当前/历史及
  `unknown` 语义。
- 技术决定与假设：验收默认 `purpose="current"`；仅 `freshness="stale"` 的已知发布
  可用 `purpose="history"` 查看，`unavailable` 始终失败。五类版本必须为非空字符串；
  指标和耗时必须为有限、非负且排除布尔值的数值。
- 集成检查：LJ-01、LJ-02、LJ-03 已修复待复核；审查脚本三项均 PASS。YHT-01/02/03
  和 ZQO-01 仍交由所属成员处理，I-01 仍待 ZQO 主责整链路验证。
- 可供其他 agent 使用的输出：[验收原型](../modules/lj/prototype/acceptance.py)、
  [回归测试](../modules/lj/prototype/test_acceptance.py)、[集成说明](../modules/lj/integration.md)
  及本记录中的复核证据。

## 成果记录

| 成果 | 路径 | 本轮验证 |
| --- | --- | --- |
| 运行与验收设计 | [design.md](../modules/lj/design.md) | 状态、版本、异常恢复和预算判据 |
| 验收原型与测试 | [acceptance.py](../modules/lj/prototype/acceptance.py)、[test_acceptance.py](../modules/lj/prototype/test_acceptance.py) | 15 项 `unittest` 通过；LJ 专项审查 3 项 PASS |
| 集成衔接 | [integration.md](../modules/lj/integration.md) | ZQO freshness 与历史查看语义已接入；其他成员问题未代修 |

### 2026-11-05：最终集成复核修复

- LJ-01：验收前严格检查双方五类版本字段及非空字符串值，空字典、缺字段、
  单边缺字段、空值和错误类型均失败。
- LJ-02：当前推荐拒绝 `stale`/`unavailable` 发布结果；已知 stale 结果仅在显式
  `purpose="history"` 下保留历史查看语义。
- LJ-03：三个指标和耗时拒绝负数、布尔值、NaN、正负无穷，并按有限耗时执行预算。
- 实际命令：`python3 -B -m unittest discover -s docs/modules/lj/prototype -v`；
  `python3 -B docs/integration/audit.py --owner LJ`。两者均通过。

### 2026-11-07：v2 第5棒恢复交付

- **开工条件**：远程 `develop` 已包含 ZC 合入提交 `0f1dfcb`/`d5685c0`；在
  `lj/v2-recovery` 分支完成本棒工作。
- **ZC 审阅**：统一模式测试 18 项通过；ZC 查询回归 9 项通过。Windows 默认编码
  运行暴露 ZC-V2-02（SQL UTF-8 读取与临时连接清理），已记入
  [集成问题清单](../integration/issues.md)，未修改 ZC 结论。
- **v2 交付**：[章节稿](../modules/lj/v2/section.md)、[展示文字](../modules/lj/v2/slides.md)、
  [参考文献](../modules/lj/v2/references.md)、[恢复实验](../modules/lj/v2/experiments/recovery.py)
  和[结果](../modules/lj/v2/experiments/results/recovery.json)。
- **实测**：合成 R0/R1 发布经 SQLite `Connection.backup()` 恢复后，
  `integrity_check=ok`、外键违规为0、发布父链通过、历史查询摘要一致；截断备份被
  检测为损坏。环境为 Python 3.14.7、SQLite 3.50.4、Windows 11；命令：
  `python -X utf8 -B docs/modules/lj/v2/experiments/recovery.py --output docs/modules/lj/v2/experiments/results/recovery.json`。
- **跨模块影响**：恢复后丢弃并按发布重建 ZC `route_graph_cache`；保留 ZQO 不可变
  发布和 LQ 审计/保留约束；成本估算采用 YHT 的 2,400 栋、三年约2 GB 假设，未
  声称生产部署或云端性能。

任务依据：[项目说明](../project-brief.md)、[共同场景约定](../scenario-contract.md)、[五人分工](../team-tasks.md)、[课程要求全文](../course-requirements.md)、[异步协作](../agent-collaboration.md)、[AI 协作指南](../../AGENTS.md)。

## 2026-11-07：LJ 发现的 ZC-V2-02 已关闭（ZC 记录）

LJ 在第5棒审阅中发现的 ZC-V2-02（Windows 默认编码下读取 SQL 失败、临时连接未关闭）已由 ZC 修复。由于整合环境没有 Windows，ZC 关闭 Python UTF-8 模式并强制 C 语言环境（默认编码 US-ASCII，比 Windows 代码页更严格）重跑全部 20 组命令，全部通过，233 项测试。排查中发现 v1 的 ZC、ZQO、LQ 与集成脚本也存在同类写入问题，已一并修复。LJ 若在 Windows 复跑，可直接使用 `python -B docs/integration/v2_verify.py --output <临时路径>`，不再需要 `-X utf8`。本记录不代写 LJ 的复核结论。
