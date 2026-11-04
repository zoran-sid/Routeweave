# SkyRoute AI 协作指南

本文件适用于整个仓库。开始工作前阅读当前项目说明、共同口径与成员职责，按实际成果记录进度。

## 1. 开始工作

1. 阅读 `README.md`、`docs/project-brief.md`、`docs/scenario-contract.md` 和 `docs/team-tasks.md`，再阅读对应成员记录。
2. 运行 `git status --short --branch` 与 `git log -5 --oneline`，保留已有修改。课程要求及来源页码见 `docs/requirements-audit.md`。
3. 按成员缩写确认责任与依赖，依据项目研究范围开展工作。技术方案与参数待论证时明确标记假设。

## 2. 项目共同口径

- 项目：SkyRoute，面向城市复杂三维环境的无人机物流配送航线规划与数据管理设计。
- 英文名：SkyRoute: Urban UAV Delivery Route Planning and Data Management in Complex 3D Environments。
- 代码与文档仓库：<https://github.com/zoran-sid/Routeweave>。
- 场景：包含高层建筑、商业区、住宅区及人员密集区域的模拟城市片区。
- 数据：城市三维环境、动态空域限制、地面暴露与风险信息。
- 用户：物流调度员、无人机运营人员、空域及安全管理员、系统管理人员。
- 核心服务：Q1 三维航线查询；Q2 航段或区域状态与来源查询。
- 算法方向：Dijkstra 基础对照、`3D A*` 重点研究、`D* Lite` 等增量方法作为动态更新候选。
- 范围：数据管理、模拟规划及验证，可选三维可视化或模拟原型；真实飞控、实时自主避障和实际飞行部署在范围之外。

必须统一的研究口径：

- 完整三维航段的几何与缓冲检查，明确坐标、垂直基准、单位及离散精度。
- 规划时间窗内限制的有效性，与查询使用的数据版本一致性分别验证。
- 硬约束先判断可行性，可行航线再比较距离、时间、风险或能耗代理指标。
- 风险模型说明失效或坠落、影响范围、暴露和后果等假设；人口密度不直接等同于安全性。代理评分、概率及实测结果分别记录。
- 查询结果可追溯到场景、空域、风险输入、风险模型和规划配置。具体架构、算法组合与参数经论证后确定。

完整定义见 `docs/scenario-contract.md`。

## 3. 成员职责

分工按方向明确主要责任与协作，不强制拆成细碎任务。仓库使用缩写，个人履历和身份对照不写入共享文档。

| 角色 | 成员 | 负责方向 | PPT |
| --- | --- | --- | --- |
| 成员1 | [LJ](docs/handoffs/lj.md) | 运维保障与验收支持 | 第9–10页 |
| 成员2 | [ZQO](docs/handoffs/zqo.md) | 总体架构与动态空域管理 | 第1–2页 |
| 成员3 | [LQ](docs/handoffs/lq.md) | 地面风险评估与安全治理 | 第5–6页 |
| 成员4 | [YHT](docs/handoffs/yht.md) | 场景需求与三维数据建模 | 第3–4页 |
| 成员5 | [ZC](docs/handoffs/zc.md) | 三维航线算法与评估 | 第7–8页 |

ZQO 统筹方案与接口，YHT 组织需求和三维数据，LQ 定义地面风险与安全治理，ZC 研究航线算法和评估，LJ 配合运行保障及后期验收。正式提交负责人由小组确认。

每人完成本模块的主要说明、依据与验证素材，展示约2页为内部安排；实际工作量与贡献按成果记录确认。模块技术成果当前均为待开始。

## 4. 文件入口

| 路径 | 内容 |
| --- | --- |
| `docs/project-brief.md` | 完整项目背景、目标、功能和研究范围 |
| `docs/scenario-contract.md` | 空间、时间、风险、版本和查询的共同定义 |
| `docs/team-tasks.md` | 当前责任与协作安排 |
| `docs/requirements-audit.md` | 课程要求及对应交付 |
| `docs/handoffs/` | 五名成员的实际工作记录和通用模板 |

成果文件在实际产生时补充到个人记录，使用仓库相对链接。当前仓库没有已配置的业务代码、构建或测试命令。

## 5. 工作记录与协作

- 个人记录说明当前任务、已完成成果路径、依据、执行过的验证、跨成员影响与下一步；尚未完成的工作保持待开始或进行中。
- 仅将真实任务成果记为贡献。常规提交、推送和文档整理由 Git 历史记录。
- 修改共同口径或分工时同步维护相关文档及成员记录，保留其他成员正在进行的工作。
- 文档只使用成员缩写，不添加全名对照。共享数据采用合成数据或适合公开的数据，实际身份与敏感轨迹由合适的渠道管理。
- 技术结论引用论文、官方技术文档或可核查实验；课程要求注明文件名和页码。模拟假设、预期结果和实测结果分别标记。
- 保持说明直接、准确。可使用 `anti-defensive-writing` 技能去除重复免责声明和无依据的自我贬低，保留影响解释的假设与限制。
- 验证覆盖三维避障、限高与禁飞、不可行任务、风险约束与权衡、动态更新和版本一致性；规模与性能结论记录条件。

## 6. Git 提交命名规则

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

依据用户提供的《作业要求.pdf》（7页），项目交付为小组报告与路演；建议报告不少于 2500 中文字，不含参考文献及附录，汇报时长另行通知。评分关注问题、设计依据、探索、证据、技术判断与反思；原型和代码属于可选加分材料。具体页码和覆盖情况见 `docs/requirements-audit.md`。

《团队项目贡献度确认表.docx》要求贡献比例合计 100%，每名成员所在行由全体成员签字，人数不足时多余签名栏可留空。当前任务均衡安排与最终实际贡献分别记录。仓库使用缩写，正式表格的身份和签名信息由成员按提交要求填写。

正式汇报时长、截止时间、AI 使用声明及提交流程以 Moodle 或教师通知核实，确认后记录来源和日期。
