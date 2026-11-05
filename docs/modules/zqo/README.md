# ZQO 空域更新与架构整合

状态：模块可交付。已在 `de2033a` 基线上完成与LQ/ZC的实际接入和回归。YHT、LJ尚无技术成果，保留模拟输入及明确接入条件。

| 成果 | 内容 |
| --- | --- |
| [设计章节](design.md) | 生命周期、候选比较、五类版本、原子发布、查询新鲜度和恢复取舍 |
| [总体架构与数据流](architecture.md) | 两张可编辑Mermaid图及模块衔接 |
| [评估证据](evaluation.md) | 20项发布测试、40项现有回归、禁飞与撤销联合场景 |
| [集成说明](integration.md) | 实际接入、风险时间窗约束、Q1/Q2与运行验收 |
| [原型](prototype/publication.py)与[测试](prototype/test_publication.py) | SQLite事务目录与真实LQ/ZC调用，Python标准库 |
| [原始结果](results/evaluation.json) | 测试日志、版本、完整路线与源码摘要 |
| [第1–2页PPT](slides/zqo-publication-architecture.pptx)与[讲稿](slides/notes.md) | 与团队现有展示衔接 |
| [参考资料](references.md) | 官方文档、课程要求与项目来源 |

复现：从仓库根目录运行 `python3 docs/modules/zqo/prototype/evaluate.py`。程序只重写本模块的结果文件。PPT内容对应当前保存的测试结果；两页PPT的文字、表格和架构图均可编辑。

报告可直接整合design、architecture和evaluation中的对应章节。个人贡献依据上述实际成果填写，姓名、学号和签名在课程提交文件中处理。
