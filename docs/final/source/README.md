# 整合材料构建来源

正文以[report.md](../report.md)为准；汇报内容和讲稿以[build_slides.mjs](build_slides.mjs)为构建源，同时提供[slides.md](../slides.md)供所有 agent 直接阅读。

## 构建

- `render_assets.mjs`：使用 Node.js 与 `sharp` 生成架构及数据关系图的 SVG/PNG。SVG保留在 `../assets/`。
- `build_report.py`：使用 Python、`python-docx` 和 Pillow，将 Markdown、表格和图转换为 `../SkyRoute-report.docx`。
- `build_slides.mjs`：在 Artifact Session 的 `presentation` 回调中调用 `buildDeck(presentation)`；或传入 `@oai/artifact-tool` 的 `Presentation.create({slideSize:{width:1280,height:720}})`。完成后显式对原生图表设置 `Heiti SC` 字体，再导出 PPTX。

在安装相应依赖的环境中，从仓库根目录构建图和报告：

```bash
node docs/final/source/render_assets.mjs
python3 docs/final/source/build_report.py
```

Word使用 Arial/Songti SC/Heiti SC，PPT使用 Heiti SC。其他系统应安装支持中文的字体或统一替换后重新渲染检查。Linux或无桌面环境通过LibreOffice转PDF时，需让fontconfig能够发现所用中文字库。

`extract_slides.py` 从最终PPTX提取展示文字、表格、图表数值及备注到 `../slides.md`，只依赖Python标准库。

```bash
python3 docs/final/source/extract_slides.py
```

## 本次检查

Word经过实际渲染与13页逐页目视检查，确认中文字形、分页、表格和图可读。PPT经过10页逐页渲染检查、OOXML关系和版面检查，以及导出文件重新导入验证。第8页为原生可编辑柱状图，包含与缓存数值一致的内嵌工作簿；7张表为原生表格。发布的PPT含10页讲稿。

构建、结构和渲染检查摘要及交付文件SHA-256见[文档检查记录](../evidence/artifact-checks.json)。渲染预览、字体缓存和临时工作簿处理文件留在构建临时目录，不作为项目成果提交。

修改后同步四项：正文与图、Word、PPT、逐页讲稿。涉及实验数值时从原始JSON读取，注明原始基线；仅调整排版无需重新运行性能实验。
