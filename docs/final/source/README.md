# v2 整合材料构建来源

| 文件 | 用途 |
| --- | --- |
| [report/report.tex](report/report.tex) | 报告唯一源稿（ctexart，XeLaTeX）；7 张图为 TikZ / pgfplots |
| [build_report.py](build_report.py) | 从成员结果 JSON 生成图表数据（`report/data/*.dat`），编译 PDF，生成 Markdown 镜像，统计正文汉字 |
| [build_slides.cjs](build_slides.cjs) | 用 pptxgenjs 3.12 构建 12 页 PPTX；图表数值从成员结果 JSON 读取，每页写入讲稿 |
| [extract_slides.py](extract_slides.py) | 从 PPTX 提取文字、表格、图表数值与讲稿到 `../slides.md`，只依赖 Python 标准库 |

## 构建

在仓库根目录执行：

```bash
python3 docs/final/source/build_report.py
```

需要 TeX Live 2024 及以上（ctex、xeCJK、TikZ、pgfplots、latexmk）与 pandoc；页数统计使用 Ghostscript。字体由 ctex 按操作系统自动选择。

```bash
npm install --prefix /tmp/pptx pptxgenjs@3.12.0
NODE_PATH=/tmp/pptx/node_modules node docs/final/source/build_slides.cjs
python3 docs/final/source/extract_slides.py
```

PPT 使用 Microsoft YaHei，Windows 与 Office for Mac 均自带。

## 修改规则

- 改报告：编辑 `report/report.tex`，运行 `build_report.py`；PDF、`report.md` 与图表数据同时更新。不要直接编辑 `report.md`。
- 改 PPT：编辑 `build_slides.cjs`，重新构建并运行 `extract_slides.py`；不要手工编辑 `slides.md`。
- 涉及实验数值时，从成员结果 JSON 读取，注明原实验条件；只调整排版无需重跑实验。

## 本次检查

报告经 XeLaTeX 编译无错误、无溢出盒；逐页渲染检查图、表与分页。PPT 通过 OOXML 结构校验（pptx 技能 `validate.py`），逐页渲染检查版面与文字溢出；三张原生图表的系列与数值从文件读回核对，对数轴设置正确。检查记录与文件摘要见 [artifact-checks-v2.json](../evidence/artifact-checks-v2.json)。
