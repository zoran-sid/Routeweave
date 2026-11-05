# 参考文献与引用用途

检索日期：2026-11-05。统一采用编号引用，正式报告可沿用下列条目。所有方案参数及实测结果分别来自本模块的合成输入和运行输出。

1. E. W. Dijkstra, “A note on two problems in connexion with graphs,” *Numerische Mathematik*, vol. 1, pp. 269–271, 1959. DOI: [10.1007/BF01386390](https://doi.org/10.1007/BF01386390)。[论文副本](https://www.cs.yale.edu/homes/lans/readings/routing/dijkstra-routing-1959.pdf)。用于非负权最短路基准。
2. P. E. Hart, N. J. Nilsson, and B. Raphael, “A Formal Basis for the Heuristic Determination of Minimum Cost Paths,” *IEEE Transactions on Systems Science and Cybernetics*, vol. 4, no. 2, pp. 100–107, 1968. DOI: [10.1109/TSSC.1968.300136](https://doi.org/10.1109/TSSC.1968.300136)。[作者论文目录](https://ai.stanford.edu/~nilsson/publications.html)、[论文](https://ai.stanford.edu/~nilsson/OnlinePubs-Nils/PublishedPapers/astar.pdf)。用于A*下界搜索基础；本模块另外给出具体代价下的一致性推导，不声称任何情境下都更快。
3. S. Koenig and M. Likhachev, “D* Lite,” *Proceedings of AAAI-02*, pp. 476–483, 2002. [作者实验室论文](https://idm-lab.org/bib/abstracts/papers/aaai02b.pdf)。用于搜索状态复用、变化边修复和增量候选设计；论文实验不作为本项目性能数据。
4. Neo4j, “Native projection,” *Graph Data Science Manual*, current文档，访问于2026-11-05。[官方文档](https://neo4j.com/docs/graph-data-science/current/management-ops/graph-creation/graph-project/)。用于源图与内存计算图分离的机制与生命周期；未部署该产品。
5. PostGIS, “ST_3DIntersects,” *PostGIS Reference*，访问于2026-11-05。[官方文档](https://postgis.net/docs/ST_3DIntersects.html)。用于三维相交、支持的几何类型和候选空间过滤；实体及安全缓冲适配仍需用本模块反例验证。
6. PostGIS, “ST_3DDWithin,” *PostGIS Reference*，访问于2026-11-05。[官方文档](https://postgis.net/docs/ST_3DDWithin.html)。用于三维距离、共同SRID及单位条件；文档指出示例的Z没有垂直基准变换，接入时须单独处理。
7. PostgreSQL Global Development Group, “13.2 Transaction Isolation,” *PostgreSQL 18 Documentation*。[固定版本官方文档](https://www.postgresql.org/docs/18/transaction-iso.html)。用于只读多次查询的快照设计及与业务版本绑定的区别；本次未执行数据库事务实验。

课程依据：[课程要求全文](../../course-requirements.md)第2、3–6页对应的数据查询、技术论证、图数据管理、评估与路演要求。[共同约定](../../scenario-contract.md)规定空间、风险、版本与状态语义。
