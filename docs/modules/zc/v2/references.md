# ZC v2 参考文献（IEEE）

访问日期均为 2026-11-07。仓库内文档按 Routeweave 相对路径引用；课程要求按《作业要求.pdf》页码引用。

[1] 香港教育大学, “INT6164课程大作业：面向真实场景的新一代数据管理系统设计,” 《作业要求.pdf》, pp. 2, 4–6, 课程提供材料. 仓库[逐页转写](../../../course-requirements.md)。

[2] ZQO, “SkyRoute v2 对接说明：组件共享与查询适配,” Routeweave repository, `docs/modules/zqo/v2/integration.md`, 2026.

[3] LQ, “SkyRoute v2 第7章：数据治理、安全、隐私与伦理,” Routeweave repository, `docs/modules/lq/v2/section.md`, 2026.

[4] SQLite, “The SQLite R*Tree Module.” [Online]. Available: https://www.sqlite.org/rtree.html. [Accessed: Nov. 7, 2026].

[5] PostGIS Project, “Spatial Indexes,” *PostGIS 3.5 Manual*. [Online]. Available: https://postgis.net/docs/manual-3.5/using_postgis_dbmanagement.html#build-indexes. [Accessed: Nov. 7, 2026].

[6] Neo4j, “Native projection,” *Graph Data Science Manual*. [Online]. Available: https://neo4j.com/docs/graph-data-science/current/management-ops/graph-creation/graph-project/. [Accessed: Nov. 7, 2026].

[7] pgRouting Contributors, “pgr_aStar,” *pgRouting Manual*. [Online]. Available: https://docs.pgrouting.org/latest/en/pgr_aStar.html. [Accessed: Nov. 7, 2026].

[8] E. W. Dijkstra, “A note on two problems in connexion with graphs,” *Numerische Mathematik*, vol. 1, pp. 269–271, 1959, doi: 10.1007/BF01386390.

[9] P. E. Hart, N. J. Nilsson, and B. Raphael, “A formal basis for the heuristic determination of minimum cost paths,” *IEEE Trans. Syst. Sci. Cybern.*, vol. 4, no. 2, pp. 100–107, 1968, doi: 10.1109/TSSC.1968.300136.

[10] S. Koenig and M. Likhachev, “D* Lite,” in *Proc. AAAI-02*, 2002, pp. 476–483.

[11] SQLite, “The SQLite Query Optimizer Overview,” Sec. “Manual Control Of Query Plans Using CROSS JOIN.” [Online]. Available: https://www.sqlite.org/optoverview.html. [Accessed: Nov. 7, 2026].

## 使用说明

- 第6.1节查询负载引用 [2]、[3]；第6.2–6.4节实验为本章可复核实验，结果文件见 `experiments/results/`；空间索引语义引用 [4]、[11]。
- 第6.5节技术比较：SQLite R*Tree [4]，PostGIS 索引 [5]，图投影 [6]，库内路径搜索 [7]；后三者为设计依据，未在本项目部署实测。
- 附录 A 的算法基础引用 [8]–[10]。
