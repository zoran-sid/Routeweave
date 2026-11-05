# YHT 模块：场景需求与三维数据建模

状态：**模块可交付；YHT-01/02/03 已修复并通过 owner 审计，待复核**
日期：2026-11-05（Asia/Shanghai）
基线：`starter-v0`
已检查提交：`42948c0f6d62a8746ba5ba30be2fb80130f0ca20`（最终集成复核记录）

本模块回答 SkyRoute 中"数据从哪来、怎样表示、怎样被查询、怎样证明可信"四个问题。交付内容包括：模拟城市片区的需求与数据模型、带版本和质量的合成场景、Q1 三维走廊与 Q2 航段状态查询、三维 R\*Tree 索引和全扫基线的对照实验，以及可直接交给 ZC 和 LQ 的跨模块快照/风险配置。所有场景均为合成数据，不代表真实城市、真实空域或真实人口。

## 交付入口

| 内容 | 路径 |
| --- | --- |
| 需求、数据模型与设计决策 | [design.md](design.md) |
| 存储、索引、分区与访问路径 | [storage.md](storage.md) |
| 数据治理、质量、安全与生命周期 | [governance.md](governance.md) |
| 已执行评估与结果 | [evaluation.md](evaluation.md) |
| 跨模块接口与接入检查 | [integration.md](integration.md) |
| 参考文献 | [references.md](references.md) |
| 两页 PPT | [slides/yht-data-model.pptx](slides/yht-data-model.pptx) |
| 讲稿与来源 | [slides/notes.md](slides/notes.md) |
| 原型代码 | [prototype/](prototype/) |
| 原生合成场景样例 | [results/scene.json](results/scene.json) |
| 原始结果 | [results/](results/) |

## 复现

要求 Python 3.10+，仅用标准库（`sqlite3`、`json`、`unittest`）。在原仓库根目录执行：

```bash
python3 -m unittest discover -s docs/modules/yht/prototype -v
python3 docs/modules/yht/prototype/evaluate.py
```

第一条运行 37 项单元测试，第二条重新生成 `results/` 下的场景样例、基准、缓存、质量、查询示例、更新示例、ZC 导出和 LQ 联合检查文件。基准在本机单进程运行，计时含 Python 几何复核，不含数据库服务端网络往返，不能当作生产延迟。

## 本次结论

- 数据模型把建筑、地形、地面暴露、空域限制、覆盖瓦片和来源元数据拆成可独立寻址的图层；五个内容版本加发布清单哈希，使"查询用了哪一版数据"可追溯。
- 三维 R\*Tree 只做候选过滤，命中与否仍由 Python 精确几何判定。2,400 栋建筑时 Q2 中位耗时从全扫 10.39 ms 降到 0.0793 ms，候选比例 0.58%；代价是构建三维索引约 37 ms、库文件 1.07 MB。
- Q1/Q2 在越界、版本不一致、数据未覆盖、建筑高度缺失时返回 `unknown` 而不是"安全"；禁飞、限高、建筑命中返回 `forbidden`/`blocked`。12 类注入数据缺陷全部被质量规则检出。
- 导出给 ZC 的快照通过其 `preflight`，A\* 得到 612.55 m、61.25 s 的可行航线；同一快照下直线航段被正确判为 `forbidden`（建筑 B-001），说明数据与规划器的空间口径一致。
- 6 个暴露分区以 `q=E×C` 转成 LQ profile 后，LQ 适配器仍得到同一条 612.55 m 航线、risk_proxy 4.2120；本场景 q 最大 0.82，未触发 LQ 的 0.9 硬阈值，验证的是字段与版本传递，不是风险结论。
- 查询缓存按五层版本整代失效，20 条查询的热命中小实验为 17.5 µs（冷 602.1 µs）；SQLite WAL 下读事务不被写事务阻塞。两项都是单机小实验，不是生产并发或 QPS 结论。
- 最终集成复核的 YHT-01/02/03 已修复：未知风险不再降级为背景，覆盖不完整/非平地被导出层拒绝，Q1 限高把垂直半径计入包络。`audit.py --owner YHT` 三项均通过，回归测试见 [evaluation.md](evaluation.md) 第 2.1 节。
- 未完成：真实数据接入、地形起伏对航线的完整影响、PostGIS 实库对照、生产级并发写入与跨进程缓存一致性；这些在 [evaluation.md](evaluation.md) 中列为后续评估，不与本次实测混淆。
