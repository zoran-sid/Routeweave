# 参考文献与资料用途

读取日期均为 2026-11-05（Asia/Shanghai）。网页只用于核对产品能力和标准语义；本模块的场景、数值和结论来自 `prototype/` 中的合成程序运行。

1. PostGIS. *ST_3DIntersects*. <https://postgis.net/docs/ST_3DIntersects.html>
   用于三维相交语义、包围盒预过滤与空间索引使用方式；文中明确浮点鲁棒性问题可改用 `ST_3DDWithin`。

2. PostGIS. *Geometry Overlaps (&&&)*. <https://postgis.net/docs/geometry_overlaps_nd.html>
   用于 n 维包围盒运算及"二维重叠但三维不重叠"的反例，支撑"2D 索引不能替代 3D 判定"的论证。

3. PostgreSQL Global Development Group. *GiST Indexes*. <https://www.postgresql.org/docs/current/gist.html>
   用于 GiST 的平衡树结构、可实现 R-tree、lossy 索引与 recheck 机制。

4. PostgreSQL Global Development Group. *BRIN Indexes*. <https://www.postgresql.org/docs/current/brin.html>
   用于 BRIN 按物理页块存储摘要、适合与物理顺序相关的数据、索引小但需 recheck 的取舍。

5. SQLite. *R\*Tree Module*. <https://www.sqlite.org/rtree.html>
   用于 1–5 维 R\*Tree 虚拟表、32 位浮点边界取整、候选集需回表精算、`rtreecheck()` 与并发写限制。本模块的三维索引即基于该模块的 7 列 3D 表。

6. IETF. *RFC 7946: The GeoJSON Format*. <https://www.rfc-editor.org/rfc/rfc7946>
   用于说明 GeoJSON 坐标参考系固定为 WGS-84、position 第三位可选高程；因此局部米制坐标不使用 GeoJSON 标签。

7. MongoDB. *2dsphere Indexes*. <https://www.mongodb.com/docs/manual/core/2dsphere/>
   用于球面几何索引和 `$geoWithin`/`$geoIntersects`/`$near` 的能力边界。官方文档以地球球面语义描述检索；本模块未验证其三维体查询，因此不把 2dsphere 列为三维候选。

8. Neo4j. *Spatial Values*. <https://neo4j.com/docs/cypher-manual/current/values-and-types/spatial/>
   用于 POINT 的 2D/3D 与 CRS 支持、点索引适用于距离和包围盒查询、以及"只索引点"的限制。

9. Elasticsearch. *geo_shape field type*. <https://www.elastic.co/guide/en/elasticsearch/reference/current/geo-shape.html>
   用于说明 geo_shape 只索引经纬度、`ignore_z_value` 默认忽略第三维、使用 WGS-84 与二维球面语义。

10. Open Geospatial Consortium. *CityGML*. <https://www.ogc.org/standards/citygml>
    用于三维城市模型的分层细节（LOD）、语义对象和城市数据交换背景；本项目只借用其"建筑/地形/空域分层"的思想，没有实现 CityGML 编码。

11. SkyRoute 课程资料。`docs/course-requirements.md`、`docs/scenario-contract.md`、`docs/requirements-audit.md`。
    用于报告章节、数据类别、查询服务、索引/分区/缓存要求、验证覆盖范围与 PPT 页码安排。

12. ZC 模块。`docs/modules/zc/design.md`、`docs/modules/zc/integration.md`。
    用于 `starter-v0` 消费端字段、五类版本、ZC preflight 约束和导出接口；本模块的 `export_zc.py` 按该接口生成快照。

13. LQ 模块。`docs/modules/lq/design.md`、`docs/modules/lq/prototype/risk.py`。
    用于 `q=E×C` 的暴露/后果分解、`compile_profiles(snapshot, query, profiles)` 的时段与版本适配；本模块的 `export_lq.py` 按其 profile 结构导出并复跑联合检查。
