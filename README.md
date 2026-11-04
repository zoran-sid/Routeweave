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
- [独立推进与异步协作](docs/agent-collaboration.md)：各人立即可做的工作、缺失输入的处理与新提交对齐流程。
- [AGENTS.md](AGENTS.md)：AI 协作和提交规范；也可通过 [agent.md](agent.md) 进入。

## 成员分工

| 成员 | 负责方向 | PPT | 个人记录 |
| --- | --- | --- | --- |
| ZQO | 总体架构与动态空域管理 | 第1–2页 | [ZQO](docs/handoffs/zqo.md) |
| YHT | 场景需求与三维数据建模 | 第3–4页 | [YHT](docs/handoffs/yht.md) |
| LQ | 地面风险评估与安全治理 | 第5–6页 | [LQ](docs/handoffs/lq.md) |
| ZC | 三维航线算法与评估 | 第7–8页 | [ZC](docs/handoffs/zc.md) |
| LJ | 运维保障与验收支持 | 第9–10页 | [LJ](docs/handoffs/lj.md) |

五位成员和各自的 agent 可直接使用 `starter-v0` 开工，将初稿写入各自模块目录，通过交接记录读取和对齐其他人的提交。总体架构与模块初稿并行推进。

项目处于准备阶段，各成员技术成果均为待开始。具体技术架构、算法组合、风险模型及实验设置在研究中论证后确定。
