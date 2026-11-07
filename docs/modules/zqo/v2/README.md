# ZQO v2：统一模式上的发布事务与历史版本

> **2026-11-07 数据更新（AI 按 ZC 指示完成，不计入 ZC 工作量）**：本模块实验已改用香港九龙开放数据重跑（[香港数据快照](../../../v2/data/hk/README.md)），最新数值以 `experiments/results/` 与最终报告为准；本目录 `section.md`、`slides.md` 中的数值来自原合成数据，保留为过程记录。

基线 `5ee1a19`，YHT PR #1 已通过 merge commit `f05459c` 合入 `develop`。本目录承接 [v2 第2棒](https://github.com/zoran-sid/Routeweave/blob/develop/docs/v2-prompts.md#2-zqo第2棒)；v1 原型、结果和最终材料保留。

| 材料 | 用途 |
| --- | --- |
| [section.md](section.md) | 摘要初稿、第1章、第3.1–3.2节、第5章 |
| [slides.md](slides.md) | 两页展示文字、图示、讲稿和引用，交 ZC 统一排版 |
| [architecture.md](architecture.md) | 事务边界、时序、版本/血缘技术决定 |
| [integration.md](integration.md) | 表映射、接口、迁移边界、成员对接与问题 |
| [references.md](references.md) | IEEE 引用与论点对应 |
| [experiments/catalog.py](experiments/catalog.py) | 使用统一 schema 的操作 B 服务和关系表导出 |
| [experiments/run.py](experiments/run.py) | 并发/回滚测试、历史存储对比、YHT 审阅复现 |
| [experiments/results/transactions-storage.json](experiments/results/transactions-storage.json) | 环境、工作树源码摘要、实测、已知问题原始结果 |
| [experiments/results/yht-index-review.json](experiments/results/yht-index-review.json) | 修改前复跑 YHT 六种访问路径的结果 |

```bash
python3 -B -m unittest discover -s docs/v2/schema -v
python3 -B docs/modules/zqo/v2/experiments/run.py --output /tmp/zqo-v2.json
python3 -B docs/integration/audit.py --owner ZQO
```

v2 实验不会覆盖 v1 基线。实验仅需 Python 标准库及支持 JSON/R*Tree 的 SQLite。数据库在临时目录中创建并清理，结果 JSON 留在指定位置。`--counts 10 100 1000` 为完整实验；快速开发检查可用 `--counts 10`，不得代替正式结果。

**已验证**：真实统一表上的发布、撤销、并发冲突、可见性、五处回滚、幂等、历史重开、全量/共享导出内容一致。**待接入**：LQ v2 质量审批与真实风险编译、ZC v2 查询结果及缓存、LJ v2 恢复与 outbox 消费。现有 v1 五模块检查通过不等于这些 v2 接口已经接通。
