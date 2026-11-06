# SkyRoute

## 面向城市无人机配送的时空数据管理平台设计（v2，开发中）

**SkyRoute: A Spatio-temporal Data Management Platform for Urban UAV Delivery**

城市三维环境、动态空域限制和地面暴露三类数据来源不同、更新频率不同、敏感程度不同。SkyRoute 设计一个管理这三类数据接入、版本、质量、血缘与权限的平台，使每次三维航线查询（Q1）和航段/区域状态与来源查询（Q2）都基于一致、可追溯的数据快照。航线规划是平台的下游查询负载。

研究对象是合成的模拟城市片区。v1 的原型与测试保留为佐证；真实飞控、实时自主避障及实际飞行部署在范围之外。

## 版本与分支

`main` 是已完成的正式版本；当前为 v1（标签 `v1.0-algorithm-baseline`，算法方向）。按课程“数据管理系统设计”要求重组的 v2 在 `develop` 分支开发，个人工作使用 `<成员缩写>/<主题>` 分支并 PR 到 `develop`。规则见 [AGENTS.md 第6节](AGENTS.md)。

## 项目文档

- [v1 最终整合交付](docs/final/README.md)：v1（算法方向）的13页报告、10页可编辑PPT、Markdown正文与讲稿、课程覆盖表及贡献依据。
- [v1 集成复核与成员修复清单](docs/integration/README.md)：131项回归、7项问题审查、11项整链路和25项风险专项通过。
- [完整项目说明](docs/project-brief.md)：背景、目标、用户、功能、技术方向和研究范围。
- [共同场景与查询约定](docs/scenario-contract.md)：三维空间、时间有效性、风险约束和一致性口径。
- [v2 五人任务安排](docs/team-tasks.md)：重组原因、章节分工、交接依赖、阶段与验收清单。
- [课程要求全文](docs/course-requirements.md)：PDF 全部文字与贡献表规则，其他成员直接读 Markdown 即可。
- [作业要求对照](docs/requirements-audit.md)：课程要求与对应交付。
- [AI 自主研究与协作](docs/agent-collaboration.md)：独立工作包、AI 技术决策、缺失输入的补齐与主动集成。
- [AGENTS.md](AGENTS.md)：AI 协作和提交规范；也可通过 [agent.md](agent.md) 进入。

## 成员分工（v2）

| 成员 | v2 职责 | 报告章节 | PPT | 个人记录 |
| --- | --- | --- | --- | --- |
| ZQO | 问题定义、总体架构与版本一致性；新兴技术主讨论 | 摘要、1、3.1–3.3 | 第1–2页 | [ZQO](docs/handoffs/zqo.md) |
| YHT | 需求与数据分析、数据模型与数据库设计 | 2、4 | 第3–4页 | [YHT](docs/handoffs/yht.md) |
| LQ | 数据治理、安全、隐私与伦理；AI 辅助治理 | 6 | 第5–6页 | [LQ](docs/handoffs/lq.md) |
| ZC | 技术选型、查询服务与性能评估；v2 整合与发布 | 5、7.1、8 | 第7–8页 | [ZC](docs/handoffs/zc.md) |
| LJ | 部署、高可用、灾备与成本；权衡汇总 | 3.4、7.2–7.3 | 第9–10页 | [LJ](docs/handoffs/lj.md) |

具体任务、交接依赖、阶段与验收清单见[五人任务安排](docs/team-tasks.md)。

v1 五个模块的成果（保留为证据）：

| 成员 | 成果入口 | 主要内容 |
| --- | --- | --- |
| ZQO | [空域发布与架构整合](docs/modules/zqo/README.md) | 一致性方案、架构图、事务原型、发布验证及第1–2页PPT |
| YHT | [场景需求与三维数据建模](docs/modules/yht/README.md) | 需求、数据模型、存储与索引、合成场景验证及第3–4页PPT |
| LQ | [地面风险与安全治理](docs/modules/lq/README.md) | 风险评估、时段适配、治理方案、联合验证及第5–6页PPT |
| ZC | [三维航线算法与评估](docs/modules/zc/README.md) | 算法设计、合成场景验证、原型及第7–8页PPT |
| LJ | [运维保障与验收支持](docs/modules/lj/README.md) | 运行规则、异常恢复、验收原型及第9–10页展示材料 |

已实测的衔接包括YHT与ZC/LQ的导出接口、LQ与ZC的风险接口，以及ZQO与LQ/ZC的事务发布与查询。五模块实际链路与来源映射已完成验证，本轮复核证据见[整合验证记录](docs/final/evidence/verification.json)，原链路设计见[ZQO集成记录](docs/integration/zqo-evidence.md)；生产部署联调仍属后续设计。
