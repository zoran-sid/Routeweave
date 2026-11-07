# ZC v2：面向规划的查询负载与性能

开工基线：`ca2bf58`（YHT PR #1、ZQO PR #4、LQ PR #6 已合入 `develop`）。分支 `zc/v2-query-workload`。第4棒；第6棒整合另行进行。

| 成果 | 内容 |
| --- | --- |
| [章节稿](section.md) | 第6章查询负载与技术选型、第8.1节实验汇总与监测指标、附录 A 算法对照 |
| [展示文字与讲稿](slides.md) | 第7–8页 |
| [参考文献](references.md) | IEEE 格式 |
| [统一模式 ZC 分节](../../../v2/schema/schema.sql) | `query_run`、`route_result`、`route_segment_source`、`route_graph_cache` 与触发器 |
| [操作 C 正式版](../../../v2/schema/op_c.sql) | 在正式结果表上追溯航线来源；任务窗口落在数据集窗口内即可 |
| [规划服务适配](experiments/planner_io.py) | 固定发布、解析物理 owner、四种取数路径、派生图构建与搜索、结果写入 |
| [取数路径实验](experiments/access_paths.py) → [结果](experiments/results/access_paths.json) | 固定 A*，200/2,400/10,000 栋，各 12 任务 |
| [缓存失效实验](experiments/invalidation.py) → [结果](experiments/results/invalidation.json) | 两次真实发布，24 张缓存图，全部重建 vs 按变更沿用/修补 |
| [LQ 审阅](experiments/review_lq.py) → [结果](experiments/results/lq-review.json) | 12 项独立探针 |
| [测试](experiments/test_query.py) | 9 项，经 `docs/v2/schema/test_query_v2.py` 进入 CI |

v1 规划器（[`../prototype/planner.py`](../prototype/planner.py)）未修改，作为固定算法被 v2 调用。

## 复现

在仓库根目录执行；输出写到新路径即可避免覆盖已交付结果：

```bash
python3 -B -m unittest discover -s docs/v2/schema -v
python3 -B -m unittest discover -s docs/modules/zc/v2/experiments -v
python3 -B docs/modules/zc/v2/experiments/access_paths.py --output /tmp/zc-access.json
python3 -B docs/modules/zc/v2/experiments/invalidation.py --output /tmp/zc-invalidation.json
python3 -B docs/modules/zc/v2/experiments/review_lq.py --output /tmp/zc-lq-review.json
```

取数实验约 17 秒，失效实验约 9 秒（Apple arm64）。计时随环境变化；正确性检查（输入摘要、结果一致、追溯完整、与全部重建一致）应全部为 0 处不一致。
