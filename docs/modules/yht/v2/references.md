# YHT v2 参考文献

状态：v2 初稿，IEEE 风格。访问日期均为 2026-11-06。仓库内文档按 Routeweave 相对路径引用；课程要求按《作业要求.pdf》页码引用。

[1] PostGIS Project, “ST_3DIntersects,” *PostGIS 3.5 Manual*. [Online]. Available: https://postgis.net/docs/ST_3DIntersects.html. [Accessed: Nov. 6, 2026].

[2] PostGIS Project, “Geometry Overlaps (&&&),” *PostGIS 3.5 Manual*. [Online]. Available: https://postgis.net/docs/geometry_overlaps_nd.html. [Accessed: Nov. 6, 2026].

[3] PostGIS Project, “Spatial Indexes,” *PostGIS 3.5 Manual*. [Online]. Available: https://postgis.net/docs/manual-3.5/using_postgis_dbmanagement.html#build-indexes. [Accessed: Nov. 6, 2026].

[4] PostGIS Project, “ST_3DDWithin,” *PostGIS 3.5 Manual*. [Online]. Available: https://postgis.net/docs/ST_3DDWithin.html. [Accessed: Nov. 6, 2026].

[5] PostgreSQL Global Development Group, “Table Partitioning,” *PostgreSQL 17 Documentation*. [Online]. Available: https://www.postgresql.org/docs/current/ddl-partitioning.html. [Accessed: Nov. 6, 2026].

[6] PostgreSQL Global Development Group, “GiST Indexes,” *PostgreSQL 17 Documentation*. [Online]. Available: https://www.postgresql.org/docs/current/gist.html. [Accessed: Nov. 6, 2026].

[7] PostgreSQL Global Development Group, “BRIN Indexes,” *PostgreSQL 17 Documentation*. [Online]. Available: https://www.postgresql.org/docs/current/brin.html. [Accessed: Nov. 6, 2026].

[8] PostgreSQL Global Development Group, “Range Types,” *PostgreSQL 17 Documentation*. [Online]. Available: https://www.postgresql.org/docs/current/rangetypes.html. [Accessed: Nov. 6, 2026].

[9] SQLite, “R*Tree Module.” [Online]. Available: https://www.sqlite.org/rtree.html. [Accessed: Nov. 6, 2026].

[10] H. Butler, M. Daly, A. Doyle, S. Gillies, S. Schaub, and T. Schaub, “The GeoJSON Format,” RFC 7946, Internet Engineering Task Force, Aug. 2016. [Online]. Available: https://www.rfc-editor.org/rfc/rfc7946.

[11] SkyRoute 课程作业要求, 《作业要求.pdf》, pp. 2, 4–7, 2026.

[12] YHT, “SkyRoute v1 存储与索引评估,” Routeweave repository, `docs/modules/yht/storage.md`, 2026.

[13] YHT, “SkyRoute v1 数据模型与质量规则,” Routeweave repository, `docs/modules/yht/design.md`, 2026.

[14] YHT, “SkyRoute v2 数据字典,” Routeweave repository, `docs/modules/yht/v2/data-dictionary.md`, 2026.

[15] ZQO, “SkyRoute 发布与一致性设计,” Routeweave repository, `docs/modules/zqo/design.md`, 2026.

[16] LQ, “SkyRoute 地面风险与治理设计,” Routeweave repository, `docs/modules/lq/design.md`, 2026.

[17] SQLite, “EXPLAIN QUERY PLAN.” [Online]. Available: https://www.sqlite.org/eqp.html. [Accessed: Nov. 6, 2026].

[18] SQLite, “The SQLite Query Optimizer Overview,” Sec. “Manual Control Of Query Plans Using CROSS JOIN.” [Online]. Available: https://www.sqlite.org/optoverview.html. [Accessed: Nov. 6, 2026].

[19] SQLite, “CREATE TRIGGER.” [Online]. Available: https://www.sqlite.org/lang_createtrigger.html. [Accessed: Nov. 6, 2026].

[20] YHT and ZC, “SkyRoute v2 统一数据库模式,” Routeweave repository, `docs/v2/schema/`, 2026.

[21] YHT and ZC, “操作 A 访问路径实验,” Routeweave repository, `docs/modules/yht/v2/experiments/results/op_a_index_comparison.json`, 2026.

## 使用说明

- 第 2 章的数据规模、更新频率和生命周期引用 [11]、[12]、[14]；三维几何和索引语义引用 [1]–[4]；时间范围与分区引用 [5]、[8]。
- 第 4 章的 ER、关系模式、Q1/Q2 SQL 引用 [1]–[4]、[8]–[10]、[12]–[14]；风险字段 E/C/q 的语义引用 [14]、[16]；统一模式、操作 A 的执行计划与访问路径实验引用 [9]、[17]–[21]。
- 上述仓库文档为团队内部成果，正式报告引用时保留版本与访问日期；外部网页只引用其方法语义，不把示例当作本项目实测结果。
