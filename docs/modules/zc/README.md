# ZC：三维航线算法与评估

状态：**模块已交付，五模块整链路复核通过，最终材料已整合**。日期：2026-11-06（Asia/Hong_Kong）。共同起始基线：`starter-v0`；最新技术复核提交：`2850d89cea68221bbe6a8cf1161bd1d3ab220c2c`。

此前已修复 Q2 实际航段端点及非字符串时间校验，当前 24 项测试通过。本轮五模块131项回归、7项审查、11项整链路及25项风险专项均通过，报告与10页PPT见[最终交付](../../final/README.md)。首次交付的性能实验、21 项测试记录与 PPT 保留原始基线；本轮证据见 [集成复核](../../integration/README.md) 与 [ZC 交接](../../handoffs/zc.md)。

本模块采用有限三维网格与完整航段约束检查，以 Dijkstra 为对照、3D A* 为查询方案。一次查询固定场景、空域、风险数据、风险模型及规划配置版本；更新后重新校验旧路线并在新版本上搜索。D* Lite 保留为有明确适用条件的增量候选。

## 交付入口

| 成果 | 内容 |
| --- | --- |
| [算法与数据访问设计](design.md) | 可合入报告的正文、技术比较、风险模拟定义、启发式证明、伪代码与决策记录 |
| [评估结果与后续实验](evaluation.md) | 实际执行条件、12个情境、21项测试、风险权衡与重规划证据 |
| [接口与集成说明](integration.md) | Q1/Q2 字段、版本与缓存约定、四个模块的替换位置和验收条件 |
| [两页 PPT](slides/zc-routing-evaluation.pptx) | 对应小组第7–8页，可编辑文字、表格和图表，含讲稿与来源 |
| [展示文字与讲稿](slides/notes.md) | 可供其他 agent 直接读取、整合的两页内容 |
| [参考文献](references.md) | 论文与官方技术文档及各自支持的设计内容 |
| [原型](prototype/planner.py)、[合成场景](prototype/scenario.json) | 标准库 Python 实现及完整输入，全部为合成数据 |
| [原始评估](results/benchmark.json)、[汇总 CSV](results/summary.csv) | 每次计时样本、版本、路径、目标分量与源码 SHA-256 |
| [Q1 输入输出](results/query-examples.json)、[更新前后结果](results/update-example.json) | 可复核路线、完整航段和发布版本变化 |

## 复现

在仓库根目录执行，Python 3.10 或更高版本，无第三方运行依赖：

```bash
python3 -m unittest discover -s docs/modules/zc/prototype -v
python3 docs/modules/zc/prototype/evaluate.py
```

第二条命令重新生成 `results/` 下的 JSON 与 CSV，计时和执行时间戳随运行环境变化。已记录环境为 Python 3.15.0、Darwin、arm64。PPT 中的结果对应本次提交保存的评估数据。

## 本次结论

- 12个情境中，两种算法的状态一致，全部可行情境的最优目标代价在 `1e-9` 内一致。
- 无风险热点的建筑场景中，二者均得到116.57米路线；A* 扩展72个节点，Dijkstra 扩展699个节点。
- 在同一风险热点场景，A* 的风险权重从0调为8，路线由116.57米增至133.14米，模拟风险代理由0.5021降至0.0666。
- 禁飞墙返回限定网格内的 `infeasible`；数据缺失、版本混用与无法绕过的未知风险返回 `unknown`。

上述为首次交付时小型合成场景上的程序运行结果。风险数值是显式模拟代理；数据库性能、真实安全概率与 D* Lite 加速尚未测量。首次交付的替代输入、最新读取的实际成果和成员文档待修项见[集成说明](integration.md)。
