# 参考文献（IEEE）

访问日期均为2026-11-06。官方文档用于机制与选型依据；数值结论来自本目录实验，未引用网络性能宣传值。

[1] SQLite, “Isolation in SQLite.” [Online]. Available: https://www.sqlite.org/isolation.html. [Accessed: Nov. 6, 2026].

[2] SQLite, “Transaction.” [Online]. Available: https://www.sqlite.org/lang_transaction.html. [Accessed: Nov. 6, 2026].

[3] Apache Software Foundation, “Reliability,” *Apache Iceberg documentation*. [Online]. Available: https://iceberg.apache.org/docs/latest/reliability/. [Accessed: Nov. 6, 2026].

[4] Apache Software Foundation, “Queries—Time travel,” *Apache Iceberg documentation*. [Online]. Available: https://iceberg.apache.org/docs/latest/spark-queries/. [Accessed: Nov. 6, 2026].

[5] PostgreSQL Global Development Group, “CREATE TABLE,” *PostgreSQL 18 Documentation*. [Online]. Available: https://www.postgresql.org/docs/18/sql-createtable.html. [Accessed: Nov. 6, 2026].

[6] PostgreSQL Global Development Group, “41.10. Trigger functions,” *PostgreSQL 18 Documentation*. [Online]. Available: https://www.postgresql.org/docs/18/plpgsql-trigger.html. [Accessed: Nov. 6, 2026].

[7] 香港教育大学, “INT6164课程大作业：面向真实场景的新一代数据管理系统设计,” 《作业要求.pdf》, pp. 1–7, 课程提供材料. 仓库[逐页转写](../../../course-requirements.md)。未获得原件出版日期，不补造年份。

## 证据对应

| 论点 | 依据及范围 |
| --- | --- |
| 单写者、读提交快照、WAL 旧读事务 | [1], [2]；本地两个连接与五处回滚测试 |
| Iceberg 快照复用、原子元数据替换及时间旅行 | [3], [4]；技术比较，没有部署 Iceberg |
| PostgreSQL 有效时间约束与历史表实现工具 | [5] 的 WITHOUT OVERLAPS/PERIOD；[6] 的数据变更与审计触发器示例；历史表双时态是本项目提出的组合设计，不称为自动原生系统版本表 |
| 存储开销、历史导出、并发行为 | [run.py](experiments/run.py)、[test_catalog.py](experiments/test_catalog.py)、[results](experiments/results/transactions-storage.json) |
| YHT 索引可复现性 | [独立复跑](experiments/results/yht-index-review.json)，6配置×6路径，查询差异数0 |
| 课程覆盖 | [7] pp.1–2问题与架构，p.4元数据/血缘，pp.4–5报告，p.6评价 |
