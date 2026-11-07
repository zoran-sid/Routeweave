# SkyRoute

## 面向城市无人机配送的时空数据管理系统设计（v2）

**SkyRoute: Spatio-temporal Data Management for Urban UAV Delivery**

核心问题：城市三维空间、动态空域和风险数据持续变化时，如何设计一个支持高效时空查询、一致性发布、历史追溯和安全访问的数据管理系统，为三维航线查询（Q1）与航段/区域状态和来源查询（Q2）提供可靠输入。航线规划是验证数据库设计的业务场景，主要证据来自数据库实验。

研究对象是合成的模拟城市片区。v1 的原型与测试保留为佐证；真实飞控、实时自主避障及实际飞行部署在范围之外。

## 版本与分支

`main` 只保存项目成果，当前为 v2（标签 `v2.1-submission`）。重组前的 v1（算法方向）保留在标签 `v1.0-algorithm-baseline`。协作过程文件保留在 `develop` 分支，包括 AI 协作说明、任务安排、提示词、成员交接记录、问题清单与课程要求对照。

## 项目文档

- [v2 最终交付](docs/final/README.md)：报告 LaTeX 源与 Markdown 镜像、PPT 构建脚本与讲稿、课程覆盖对照、贡献依据与整合证据。报告 PDF（23 页）和 PPT（12 页）在本地由源文件构建。
- [统一数据库模式](docs/v2/schema/schema.sql)：34 个实体、约束、触发器与时空索引，含 [ER 图](docs/v2/schema/er.md) 与 [设计决定](docs/v2/schema/decisions.md)。
- [完整项目说明](docs/project-brief.md)：背景、目标、用户、功能、技术方向和研究范围。
- [共同场景与查询约定](docs/scenario-contract.md)：三维空间、时间有效性、风险约束和一致性口径。
- [课程要求全文](docs/course-requirements.md)：《作业要求.pdf》全部文字与贡献表规则。
- 协作过程（`develop` 分支）：[AI 协作说明](https://github.com/zoran-sid/Routeweave/blob/develop/AGENTS.md)、[任务安排](https://github.com/zoran-sid/Routeweave/blob/develop/docs/team-tasks.md)、[问题清单](https://github.com/zoran-sid/Routeweave/blob/develop/docs/integration/issues.md)、[成员交接记录](https://github.com/zoran-sid/Routeweave/tree/develop/docs/handoffs)。

## 成员分工（v2）

| 棒次 | 成员 | v2 数据库重点 | 报告章节 | PPT | 模块成果 |
| --- | --- | --- | --- | --- | --- |
| 1 | YHT | 三维时空数据模型与物理设计；统一模式 | 2、4 | 第4–5页 | [YHT v2](docs/modules/yht/v2/) |
| 2 | ZQO | 事务、并发控制与版本管理；新兴技术；总体架构 | 摘要、1、3.1–3.2、5 | 第1–3、6页 | [ZQO v2](docs/modules/zqo/v2/) |
| 3 | LQ | 风险数据治理与数据库访问控制 | 7 | 第7–8页 | [LQ v2](docs/modules/lq/v2/) |
| 4 | ZC | 面向规划的查询负载与性能；v2 整合与发布 | 6、8.1、9、附录 | 第9–10页 | [ZC v2](docs/modules/zc/v2/) |
| 5 | LJ | 运行保障与恢复验收；权衡汇总 | 3.3、8.2–8.4 | 第11–12页 | [LJ v2](docs/modules/lj/v2/) |

实际贡献依据见 [contributions.md](docs/final/contributions.md)。

v1 五个模块的成果（保留为证据）：

| 成员 | 成果入口 | 主要内容 |
| --- | --- | --- |
| ZQO | [空域发布与架构整合](docs/modules/zqo/README.md) | 一致性方案、架构图、事务原型、发布验证及第1–2页PPT |
| YHT | [场景需求与三维数据建模](docs/modules/yht/README.md) | 需求、数据模型、存储与索引、合成场景验证及第3–4页PPT |
| LQ | [地面风险与安全治理](docs/modules/lq/README.md) | 风险评估、时段适配、治理方案、联合验证及第5–6页PPT |
| ZC | [三维航线算法与评估](docs/modules/zc/README.md) | 算法设计、合成场景验证、原型及第7–8页PPT |
| LJ | [运维保障与验收支持](docs/modules/lj/README.md) | 运行规则、异常恢复、验收原型及第9–10页展示材料 |

已实测的衔接包括YHT与ZC/LQ的导出接口、LQ与ZC的风险接口，以及ZQO与LQ/ZC的事务发布与查询。五模块实际链路与来源映射已完成验证，本轮复核证据见[整合验证记录](https://github.com/zoran-sid/Routeweave/blob/v1.0-algorithm-baseline/docs/final/evidence/verification.json)，原链路设计见[ZQO集成记录](https://github.com/zoran-sid/Routeweave/blob/develop/docs/integration/zqo-evidence.md)；生产部署联调仍属后续设计。
