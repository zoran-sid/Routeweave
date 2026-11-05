# 参考文献与用途

检索于2026-11-05。文内[1]–[4]仅用于相应设计依据，模拟参数与结果来自本仓库运行，不归因于外部文献。

1. EASA, “Specific Operations Risk Assessment (SORA),” 官方方法概览。[来源](https://www.easa.europa.eu/en/domains/drones-air-mobility/operating-drone/specific-category-civil-drones/specific-operations-risk-assessment-sora)。用于地面风险受人口、尺寸、操作和缓解条件影响的概念。本文不将q代理或0.9阈值对应为SORA风险等级，也不主张满足实际飞行授权。
2. S. Oh and Y. Yoon, “Data-driven risk analysis of unmanned aircraft system operations considering spatiotemporal characteristics of population distribution,” arXiv:2207.14520v1, 2022. [论文](https://arxiv.org/abs/2207.14520v1)。用于时变人口暴露与敏感性分析动机，非本项目效果证据。
3. NIST, *Security and Privacy Controls for Information Systems and Organizations*, SP 800-53 Rev.5, 2020（2020-12-10更新版），控制AC-5、AC-6、AU-3、AU-9。[官方出版页](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final)。借鉴职责分离、最小权限、审计内容及审计保护。出版页另列2025年的5.2.0更新，本项目未声明正式控制合规。
4. PostgreSQL Global Development Group, “5.9 Row Security Policies,” *PostgreSQL 18 Documentation*。[固定版本官方文档](https://www.postgresql.org/docs/18/ddl-rowsecurity.html)。用于默认拒绝、角色策略与超级用户/拥有者绕过行为。方案未部署PostgreSQL，不能把策略模拟视为数据库验证。

项目依据：[课程要求](../../course-requirements.md)第2、5–7页，[共同约定](../../scenario-contract.md)及ZC在`be027dc9c94d2416836f2b8f24fe4e3fee81000c`的[设计](../zc/design.md)和[集成说明](../zc/integration.md)。
