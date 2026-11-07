# 参考文献（IEEE）

[1] SQLite, “CREATE TRIGGER.” [Online]. Available: https://www.sqlite.org/lang_createtrigger.html. [Accessed: Nov. 7, 2026]. 触发器与RAISE拒绝机制；本项目跨行覆盖规则及结果由SQL实验给出。

[2] SQLite, “Compile-Time Authorization Callbacks.” [Online]. Available: https://www.sqlite.org/c3ref/set_authorizer.html. [Accessed: Nov. 7, 2026]. 连接级授权与SQLITE_DENY；固定查询端点和身份边界为本项目设计。

[3] PostgreSQL Global Development Group, “5.9. Row Security Policies,” PostgreSQL 18 Documentation. [Online]. Available: https://www.postgresql.org/docs/18/ddl-rowsecurity.html. [Accessed: Nov. 7, 2026]. 默认拒绝、拥有者/超级用户/BYPASSRLS边界；PostgreSQL为未部署候选。

[4] NIST, Security and Privacy Controls for Information Systems and Organizations, SP 800-53 Rev.5, 2020 (Dec.10 update). [Online]. Available: https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final. [Accessed: Nov. 7, 2026]. 借鉴AC-5/AC-6/AU-3/AU-9的职责分离、最小权限及审计保护，不声称正式控制合规。

[5] 香港教育大学, “INT6164课程大作业：面向真实场景的新一代数据管理系统设计,” 《作业要求.pdf》, pp.1–7, 课程提供材料。仓库[逐页转写](../../../course-requirements.md)。

## 证据边界

- 200米、两个分区、90/365日及风险公式都是项目演示/内部设计参数，没有把它们归因于法规或匿名标准。
- 实际实验及代码见[run.py](experiments/run.py)、[治理结果](experiments/results/governance.json)及[ZQO审阅](experiments/results/zqo-review-before.json)。
- [ZQO章节](../../zqo/v2/section.md)的存储结论经原脚本独立复跑；各模块各自原始性能记录保留。
