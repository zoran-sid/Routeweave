# SkyRoute v2 整合交付

整合日期：2026-11-07。整合方：ZC（第6棒）。v2 以数据库为中心重组，五名成员按串行顺序完成各自章节后在此整合；v1（算法方向）的报告、PPT 与证据保留在标签 `v1.0-algorithm-baseline`。

## 交付文件

| 文件 | 内容 |
| --- | --- |
| [SkyRoute-report.pdf](SkyRoute-report.pdf) | 21 页小组报告（XeLaTeX），7 张图、17 张表、26 条 IEEE 参考文献 |
| [report.md](report.md) | 报告的 Markdown 镜像，由 LaTeX 源自动生成，图、表与引用编号与 PDF 一致 |
| [SkyRoute-presentation.pptx](SkyRoute-presentation.pptx) | 12 页可编辑汇报稿，原生图表与表格，每页附讲稿与来源 |
| [slides.md](slides.md) | 逐页展示文字、表格、图表数值与讲稿，由 PPTX 自动提取 |
| [course-coverage.md](course-coverage.md) | 课程要求（PDF 页码）→ 报告章节与页码 → PPT 页 → 证据 |
| [contributions.md](contributions.md) | 成员实际成果依据与贡献表填写步骤 |
| [evidence/verification-v2.json](evidence/verification-v2.json) | 整合复核：20 组命令的命令行、退出码、日志尾部、环境与全部源码摘要 |
| [evidence/artifact-checks-v2.json](evidence/artifact-checks-v2.json) | 报告与 PPT 的构建、校验与文件摘要 |
| [source/](source/README.md) | 报告 LaTeX 源、PPT 构建脚本与提取脚本 |

报告正文（摘要至第 9 章，不含参考文献与附录）9,887 个汉字。PPT 共 12 页，按 ZQO（1–3、6）、YHT（4–5）、LQ（7–8）、ZC（9–10）、LJ（11–12）的顺序讲述；页数按课程公布的汇报时长再调整。

## 验证状态

| 检查 | 结果 |
| --- | --- |
| 整合复核（`docs/integration/v2_verify.py`） | 20/20 组命令符合预期，233 项测试通过；关闭 UTF-8 模式的 ASCII 语言环境下同样 20/20 |
| 统一模式测试（含 ZQO、LQ、ZC 回归） | 全部通过 |
| 五名成员 v2 实验与审阅脚本 | 全部重跑通过；逐棒审阅发现的 10 个问题均已修复 |
| v1 模块测试与集成脚本 | 全部通过 |
| PPTX 结构校验 | 通过；无多余 ZIP 目录项 |

逐棒审阅共发现 10 个问题，发布前全部修复并复核；其中 LQ-V2-02、ZQO-V2-01 由 ZC 在整合阶段按用户指示代修，记在原负责人名下并待其复核，详见[问题清单](../integration/issues.md)。

## 构建与复核

```bash
python3 -B docs/integration/v2_verify.py --output /tmp/verify.json
python3 docs/final/source/build_report.py
NODE_PATH=<pptxgenjs 所在 node_modules> node docs/final/source/build_slides.cjs
python3 docs/final/source/extract_slides.py
```

报告需要 TeX Live（ctex、xeCJK、TikZ、pgfplots，XeLaTeX）与 pandoc；PPT 需要 `pptxgenjs@3.12.0`。报告图表与 PPT 图表的数值都从成员结果文件读取，不手工抄写。

## 提交前由成员确认

- 封面姓名与学号：复制 `source/report/cover-info.example.tex` 为 `cover-info.tex` 填写后重新构建；该文件已被 `.gitignore` 排除，不进入公开仓库。
- 实际贡献比例（合计 100%）与《团队项目贡献度确认表》逐行签字。
- 正式提交负责人、截止时间、汇报时长、上传格式与 AI 使用声明格式（以 Moodle 或教师通知为准）。
- 本版本已发布到 `main`（标签 `v2.0-submission`）；正式提交前若有修改，从 `develop` 修订后再发布。
