# SkyRoute AI 协作指南

本文件适用于整个仓库。开始工作前阅读当前项目说明、共同口径与成员职责，按实际成果记录进度。

**当前版本状态（2026-11-07）**：v2 已发布到 `main`（标签 `v2.0-submission`）；v1（算法方向）保留在标签 `v1.0-algorithm-baseline`。v2 以数据库为中心，五棒完成后由 ZC 整合：21 页 PDF 报告、12 页 PPT 与证据见[最终交付](docs/final/README.md)，逐棒审阅发现的问题见[问题清单](docs/integration/issues.md)。正式提交前的修改仍从 `develop` 创建个人分支，再经发布 PR 进入 `main`，规则见第6节。

## 1. 开始工作

1. 阅读 `README.md`、`docs/course-requirements.md`、`docs/project-brief.md`、`docs/scenario-contract.md`、`docs/agent-collaboration.md` 和 `docs/team-tasks.md`，再阅读五名成员的全部交接记录，确认各模块当前状态、已完成成果和未解决问题。课程原文与贡献表规则已写入 Markdown，开工无需访问本地 PDF 或 Word。
2. 运行 `git status --short --branch` 与 `git log -5 --oneline`，保留已有修改。按异步协作规则检查远程和其他成员的新提交，记录本轮读取的版本。课程要求与交付映射见 `docs/requirements-audit.md`；最终材料的章节和页码映射见 `docs/final/course-coverage.md`。
3. 按成员缩写确认工作包，使用 `starter-v0` 和模块交换约定独立完成设计交付。缺少其他模块时补齐最小模拟输入及验证，不能停在占位接口或等待清单。
4. 各 agent 自行研究、比较并决定范围内的技术方案，记录证据和适用条件后继续完成工作。无需等待 ZQO 的架构或逐项审批；跨模块兼容检查可由当前 agent 读取已提交成果后执行。

## 2. 项目共同口径

- 项目：SkyRoute，面向城市无人机配送的时空数据管理系统设计（v2）。
- 英文名：SkyRoute: Spatio-temporal Data Management for Urban UAV Delivery。
- 核心问题：城市三维空间、动态空域和风险数据持续变化时，如何设计支持高效时空查询、一致性发布、历史追溯和安全访问的数据管理系统，为航线规划提供可靠输入。航线规划是验证数据库设计的业务场景。
- 统一模式：逻辑模型以 YHT 的数据字典为准，可执行模式在 `docs/v2/schema/`。
- 代码与文档仓库：<https://github.com/zoran-sid/Routeweave>。
- 场景：包含高层建筑、商业区、住宅区及人员密集区域的模拟城市片区。
- 数据：城市三维环境、动态空域限制、地面暴露与风险信息。
- 用户：物流调度员、无人机运营人员、空域及安全管理员、系统管理人员。
- 核心服务：Q1 三维航线查询；Q2 航段或区域状态与来源查询。
- 新兴技术：深入讨论数据血缘与版本化派生数据管理；湖仓快照/时间旅行与 PostgreSQL 时态表作为比较对象。
- 证据：以数据库实验为主（执行计划、并发发布、更新可见性、历史存储开销、恢复后完整性、规划查询耗时分解）；A* 保留为应用验证，报告与 PPT 各不超过一页。
- 范围：数据管理、模拟规划及验证，可选三维可视化或模拟原型；真实飞控、实时自主避障和实际飞行部署在范围之外。

必须统一的研究口径：

- 完整三维航段的几何与缓冲检查，明确坐标、垂直基准、单位及离散精度。
- 规划时间窗内限制的有效性，与查询使用的数据版本一致性分别验证。
- 硬约束先判断可行性，可行航线再比较距离、时间、风险或能耗代理指标。
- 风险模型说明失效或坠落、影响范围、暴露和后果等假设；人口密度不直接等同于安全性。代理评分、概率及实测结果分别记录。
- 查询结果可追溯到场景、空域、风险输入、风险模型和规划配置。具体架构、算法组合与参数经论证后确定。

完整定义见 `docs/scenario-contract.md`。

## 3. 成员职责

v2 按课程报告章节分工，详见[任务安排](docs/team-tasks.md)。仓库使用缩写，个人履历和身份对照不写入共享文档。

| 棒次 | 成员 | v2 数据库重点 | 报告章节 | PPT |
| --- | --- | --- | --- | --- |
| 1 | [YHT](docs/handoffs/yht.md) | 三维时空数据模型与物理设计；统一模式 | 2、4 | 第4–5页 |
| 2 | [ZQO](docs/handoffs/zqo.md) | 事务、并发控制与版本管理；新兴技术；总体架构 | 摘要、1、3.1–3.2、5 | 第1–3、6页 |
| 3 | [LQ](docs/handoffs/lq.md) | 风险数据治理与数据库访问控制 | 7 | 第7–8页 |
| 4 | [ZC](docs/handoffs/zc.md) | 面向规划的查询负载与性能；v2 整合与发布 | 6、8.1、9、附录 | 第9–10页 |
| 5 | [LJ](docs/handoffs/lj.md) | 运行保障与恢复验收；权衡汇总 | 3.3、8.2–8.4 | 第11–12页 |

按棒次串行执行：上一棒 PR 合入 `develop` 后下一棒开始，并先审阅上一棒。每人在 `docs/modules/<缩写小写>/v2/` 交付章节、两页展示文字、引用与实验，并细化 `docs/v2/schema/` 中本人表组；v1 模块成果保留为证据。各 agent 自主研究和决定本章技术方案，跨模块兼容修订可由任何 agent 完成并记录。正式提交负责人由小组确认。

## 4. 文件入口

| 路径 | 内容 |
| --- | --- |
| `docs/final/README.md` | 整合报告、PPT、Markdown源稿、课程覆盖及验证证据 |
| `docs/project-brief.md` | 完整项目背景、目标、功能和研究范围 |
| `docs/scenario-contract.md` | 空间、时间、风险、版本、查询及模块交换的共同定义 |
| `docs/team-tasks.md` | 当前责任与协作安排 |
| `docs/course-requirements.md` | PDF 全文、贡献表规则及课程建议与内部安排的区分 |
| `docs/requirements-audit.md` | 课程要求及对应交付 |
| `docs/agent-collaboration.md` | AI 自主研究、技术决策、独立交付与集成检查 |
| `docs/modules/<成员缩写小写>/` | 各成员首次工作时创建的独立成果目录 |
| `docs/handoffs/` | 五名成员的实际工作记录和通用模板 |

成果文件在实际产生时补充到个人记录，使用仓库相对链接。各模块的原型与测试命令见对应 `docs/modules/<成员缩写小写>/README.md`。

## 5. 工作记录与协作

- 个人记录说明当前任务、已完成成果路径、依据、执行过的验证、跨成员影响与下一步；尚未完成的工作保持待开始或进行中。
- 各成员主责自己的工作包；AI 自主完成资料研究、方案比较、技术选择、设计与验证。每轮读取其他模块的新成果并主动融合，流程见 `docs/agent-collaboration.md`。
- 交接记录保留已检查提交、引用文件与版本、技术决定、假设、可复用输出和集成检查。由执行修改的 AI 核对受影响的已提交成果，无需等待负责人或其他成员在线；不得代写他人的认可和结果。
- 必要的共用说明及兼容修订可由任何 agent 完成，记录依据和影响。破坏兼容性的改动先提供迁移与检查，未满足时保留当前基线下可用的交付；已证明错误的结论应标记失效并修正。
- 仅将真实任务成果记为贡献。常规提交、推送和文档整理由 Git 历史记录。
- 修改共同口径或分工时同步维护相关文档及成员记录，保留其他成员正在进行的工作。
- 文档只使用成员缩写，不添加全名对照。共享数据采用合成数据或适合公开的数据，实际身份与敏感轨迹由合适的渠道管理。
- 技术结论引用论文、官方技术文档或可核查实验；课程要求注明文件名和页码。模拟假设、预期结果和实测结果分别标记。
- 保持说明直接、准确。撰写或修改专业说明时使用 `anti-defensive-writing` 技能（若环境提供）；核心原则同时适用于所有 agent：直接说明有依据的结论，去除重复免责声明和无依据的自我贬低，保留影响解释的假设与限制。
- 验证覆盖三维避障、限高与禁飞、不可行任务、风险约束与权衡、动态更新和版本一致性；规模与性能结论记录条件。

## 6. Git 分支与提交规则

### 6.1 分支结构

| 分支 | 含义 | 写入方式 |
| --- | --- | --- |
| `main` | 已完成、可正式提交的版本；GitHub 默认展示 | 只合并来自 `develop` 的发布 PR：全部检查通过、小组确认后由整合方合并，并打版本标签 |
| `develop` | 中间开发版本，汇总已完成审阅的章节、PPT和修订 | 只合并成员分支 PR；保持检查通过，可随时生成候选版本 |
| `<成员缩写小写>/<主题>` | 个人工作，例如 `zc/tech-selection`、`lq/governance` | 从最新 `develop` 创建，完成后 PR 到 `develop`，合并后删除 |
| `hotfix/<主题>` | 已发布 `main` 的紧急更正 | 从 `main` 创建，PR 回 `main`，再合入 `develop` |

版本标签：`v1.0-algorithm-baseline` 为 v1 完整交付；v2 候选版本用 `v2.0-rc.N`，最终提交用 `v2.0-submission`。

开工流程：

```bash
git fetch origin
git switch develop && git pull --ff-only
git switch -c <缩写>/<主题>
```

- GitHub 分支保护（2026-11-06 起）：`main` 必须经 PR 合并且 `checks` 通过，禁止 force push 和删除；`develop` 禁止 force push 和删除，允许直接推送。PR 不强制审批人数。
- 常规工作不直接推送 `main` 或 `develop`；`develop` 上的小修（错字、链接）可直接推送，推送后确认 `checks` 通过。
- PR 标题沿用下方提交命名格式；正文写明改动、验证命令与结果、受影响的其他成员。合并方式使用 merge commit，保留成员提交和作者记录。
- 合并前分支须基于最新 `develop`，GitHub Actions 的 `checks` 通过；跨成员内容至少由一名其他成员（或其 agent）审阅。
- `develop` → `main` 的发布 PR 附课程覆盖表与验证证据，合并后打标签。发往 `main` 的 PR 只能来自 `develop` 或 `hotfix/*`，CI 的 `checks` 会拒绝其他来源；开 PR 前确认目标分支（`gh pr create --base develop`）。

### 6.2 提交命名

本项目采用 Conventional Commits 风格，统一使用以下标题格式：

```text
<type>(<scope>): <summary>
```

- `type` 和 `scope` 使用小写英文；冒号后留一个空格。
- `summary` 使用简洁英文，以动作动词开头，说明本次实际完成的改动；末尾不加句号，标题建议控制在 72 个字符以内。
- `scope` 表示改动领域，例如 `collaboration`、`requirements`、`architecture`、`model`、`governance`、`evaluation`、`report`、`slides`、`data` 或 `routing`；按实际领域选择，无需包含成员姓名。
- 一次提交围绕一项可独立理解的工作；正文按需说明原因、影响和验证结果。避免使用 `update`、`修改文件`、`final` 等无法识别改动内容的标题。
- 本规则适用于后续提交；保留已有提交历史。

| type | 使用场景 | 示例 |
| --- | --- | --- |
| `docs` | 报告、PPT、图表说明、协作与交接文档 | `docs(requirements): define route query requirements` |
| `feat` | 新增可用功能 | `feat(routing): add shortest path queries` |
| `fix` | 修复功能或数据处理错误 | `fix(routing): exclude restricted flight segments` |
| `test` | 新增或调整测试与测试夹具 | `test(routing): cover unreachable destinations` |
| `refactor` | 保持行为不变的代码结构调整 | `refactor(model): extract event validation` |
| `perf` | 性能优化 | `perf(routing): reuse adjacency indexes` |
| `chore` | 依赖、工具配置和仓库维护 | `chore(repo): ignore temporary files` |
| `build` | 构建配置与打包流程 | `build(app): configure production build` |
| `ci` | 持续集成配置 | `ci(checks): validate Markdown links` |

以上示例用于说明命名，不代表对应功能已实现。章节正文、PPT 和方案图属于 `docs`；实际原型功能属于 `feat`。提交前检查暂存区范围与 `git diff --cached --check`，将本次成果及对应交接记录一起提交。

## 7. 课程提交信息的使用

依据用户提供的《作业要求.pdf》（7页），项目交付为小组报告与路演；建议报告不少于 2500 中文字，不含参考文献及附录，汇报时长另行通知。评分关注问题、设计依据、探索、证据、技术判断与反思；原型和代码属于可选加分材料。课程全文见 `docs/course-requirements.md`，具体页码和覆盖情况见 `docs/requirements-audit.md`。

《团队项目贡献度确认表.docx》要求贡献比例合计 100%，每名成员所在行由全体成员签字，人数不足时多余签名栏可留空。当前任务均衡安排与最终实际贡献分别记录。仓库使用缩写，正式表格的身份和签名信息由成员按提交要求填写。

正式汇报时长、截止时间、AI 使用声明及提交流程以 Moodle 或教师通知核实，确认后记录来源和日期。
