# SkyRoute

## 面向城市复杂三维环境的无人机物流配送航线规划与数据管理设计

**SkyRoute: Urban UAV Delivery Route Planning and Data Management in Complex 3D Environments**

SkyRoute 研究模拟城市片区中的三维空间数据、动态空域限制与地面风险，设计兼顾配送效率、人员安全和数据管理性能的无人机航线查询系统。

项目以数据管理设计为核心：管理建筑与地形、禁飞及限高事件、人口暴露与风险数据；在满足硬约束的前提下比较航程、时间和风险。算法以 Dijkstra 为对照，重点探索 `3D A*`，研究 `D* Lite` 等方法在动态更新中的适用性。

研究成果包括需求、模型、架构、选型、风险分析、航线方法和验证方案。三维可视化或模拟原型按进度选做；真实飞控、实时自主避障及实际飞行部署在范围之外。

## 项目文档

- [完整项目说明](docs/project-brief.md)：背景、目标、用户、功能、技术方向和研究范围。
- [共同场景与查询约定](docs/scenario-contract.md)：三维空间、时间有效性、风险约束和一致性口径。
- [五人任务安排](docs/team-tasks.md)：各人主要责任与协作关系。
- [课程要求全文](docs/course-requirements.md)：PDF 全部文字与贡献表规则，其他成员直接读 Markdown 即可。
- [作业要求对照](docs/requirements-audit.md)：课程要求与对应交付。
- [AI 自主研究与协作](docs/agent-collaboration.md)：独立工作包、AI 技术决策、缺失输入的补齐与主动集成。
- [AGENTS.md](AGENTS.md)：AI 协作和提交规范；也可通过 [agent.md](agent.md) 进入。

## 成员分工

| 成员 | 负责方向 | PPT | 个人记录 |
| --- | --- | --- | --- |
| ZQO | 空域更新、版本一致性与架构整合 | 第1–2页 | [ZQO](docs/handoffs/zqo.md) |
| YHT | 场景需求与三维数据建模 | 第3–4页 | [YHT](docs/handoffs/yht.md) |
| LQ | 地面风险评估与安全治理 | 第5–6页 | [LQ](docs/handoffs/lq.md) |
| ZC | 三维航线算法与评估 | 第7–8页 | [ZC](docs/handoffs/zc.md) |
| LJ | 运维保障与验收支持 | 第9–10页 | [LJ](docs/handoffs/lj.md) |

五个工作包并行推进，各自的 AI 使用 `starter-v0` 和模块交换约定自主研究、选型、设计与验证，形成可交付版本。ZQO 主责空域更新和版本一致性，持续整合总体架构；其他模块可以直接完成自己的技术决定。通过 Git 读取新成果后，当前 AI 主动检查与修订。

ZC 已完成[三维航线算法与评估模块](docs/modules/zc/README.md)，包括设计、合成场景验证、原型和第7–8页PPT；模块可交付，实际跨模块集成待检查。其余成员状态见各自记录，具体技术方案按研究成果持续对齐。

LQ已完成[地面风险与安全治理模块](docs/modules/lq/README.md)，包括报告章节、时段风险适配、治理方案、19项测试、与ZC联合验证及第5–6页PPT。其他模块实际接入状态见LQ记录。
