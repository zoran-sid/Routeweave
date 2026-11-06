# SkyRoute 整合交付

整合日期：2026-11-06。技术与验证基线：`2850d89cea68221bbe6a8cf1161bd1d3ab220c2c`。本目录汇总五个成员的已提交成果，提供报告、汇报稿、课程覆盖关系和可追溯证据。

## 交付文件

| 文件 | 用途 |
| --- | --- |
| [SkyRoute-report.docx](SkyRoute-report.docx) | 13页整合报告，含架构图、数据关系图、评估、贡献说明及参考文献 |
| [report.md](report.md) | 报告正文源稿，供所有成员及 agent 直接读取和修订 |
| [SkyRoute-presentation.pptx](SkyRoute-presentation.pptx) | 10页可编辑汇报稿，包含原生表格、图表及每页讲稿 |
| [slides.md](slides.md) | 逐页展示文字、数据和讲稿，便于异步协作 |
| [course-coverage.md](course-coverage.md) | 课程要求、报告章节、PPT页码与证据的逐项映射 |
| [contributions.md](contributions.md) | 五名成员实际成果依据及正式贡献表填写准备 |
| [evidence/verification.json](evidence/verification.json) | 本轮测试命令、完整日志、环境、源代码摘要 |
| [source/README.md](source/README.md) | 文档、图和汇报稿的构建来源与排版检查说明 |

报告正文、摘要及贡献说明共计6,451个汉字（按 Unicode 汉字计数，不含参考文献和附录），覆盖课程建议的2,500中文字篇幅。10页及每人2页属于本组内部安排。

## 验证状态

| 检查组 | 本轮结果 | 原始证据 |
| --- | --- | --- |
| 五模块单元测试 | 131/131，YHT42、LQ19、ZC24、ZQO31、LJ15 | [verification.json](evidence/verification.json) |
| 原问题审查 | 7/7 | [audit.json](evidence/audit.json) |
| 五模块实际链路 | 11/11 | [five-module.json](evidence/five-module.json) |
| 风险专项 | 25/25，覆盖两个独立导出入口 | [risk-review.json](evidence/risk-review.json) |

空间索引与算法性能引用各模块保存的历史实验；本轮重新运行正确性与集成检查，不覆盖历史计时。原型验证范围是合成平地、固定任务窗口、有限三维网格及本地 SQLite。报告分别说明实际运行的功能和后续部署设计。

## 后续维护

每次修改先读取五名成员的最新交接、Git提交和[集成问题清单](../integration/issues.md)，再修改自己的模块及受影响的整合材料。修改结论时同步 Markdown、Word、PPT、讲稿和证据引用；原始实验结果保留其执行基线。

当前有一项成员文档待修：**YHT-05，PostGIS n维索引操作符类名称**。由 YHT 核对并修订原模块文档，整合稿采用已核实的技术范围，不复用有问题的SQL名称。其他成员原模块及个人交接未由本轮整合代改。

正式提交前由成员确认：姓名和学号、实际贡献比例合计100%、各行全体成员签字、正式提交负责人，以及 Moodle/教师通知中的截止时间、汇报时长、AI使用声明和提交格式。材料中的AI使用说明记录了本组实际工作方式；课程的具体声明要求仍以正式通知为准。

## 复核命令

在仓库根目录执行各模块 README 中的 unittest 命令，以及：

```bash
python3 -B docs/integration/audit.py --output /tmp/skyroute-audit.json
python3 -B docs/integration/five_module.py --output /tmp/skyroute-five-module.json
python3 -B docs/modules/lq/prototype/review_integration.py --output /tmp/skyroute-risk-review.json
```

输出使用临时路径，避免覆盖已归档证据。发布前检查新结果的版本、源码摘要、失败项和实际输入输出。
