# 参考资料与用途

检索日期：2026-11-05。正式报告可统一合并为同一种引用格式。

1. PostgreSQL Global Development Group. PostgreSQL 18 Documentation: Transaction Isolation. https://www.postgresql.org/docs/18/transaction-iso.html 。用于说明数据库读快照与业务版本绑定的区别，支持只读可重复读装载候选。
2. PostgreSQL Global Development Group. PostgreSQL 18 Documentation: Explicit Locking. https://www.postgresql.org/docs/18/explicit-locking.html 。用于发布目录当前指针的行锁与并发发布设计。
3. Amazon Web Services. Transactional outbox pattern. https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html 。用于业务变更与待发送事件同事务、重复事件处理。
4. SQLite. Transaction. https://www.sqlite.org/lang_transaction.html 。用于原型的显式提交、回滚与单写者语义。
5. SQLite. Write-Ahead Logging. https://www.sqlite.org/wal.html 。用于同机读写连接交错验证及WAL适用范围。
6. SkyRoute团队. [共同场景](../../scenario-contract.md)、[ZC接口](../zc/integration.md)、[ZC设计](../zc/design.md)、[LQ接口](../lq/integration.md)、[LQ治理](../lq/governance.md)。读取基线 `de2033a0b13296dcadd991e101a3bee3c1df4596`。用于项目约束、合成输入及模块接口。
7. INT6164课程大作业. [课程要求](../../course-requirements.md)，原PDF第2、4至7页。用于总体架构、技术比较、治理、评估和设计权衡覆盖。

本模块20项测试和联合情境是本地执行证据，见 [evaluation.md](evaluation.md) 与原始结果。模拟数值来自ZC/LQ夹具；保留期来自LQ课程模拟策略。
