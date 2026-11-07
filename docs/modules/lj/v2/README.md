# LJ v2：运行保障与恢复验收

> **2026-11-07 数据更新（AI 按 ZC 指示完成，不计入 ZC 工作量）**：本模块实验已改用香港九龙开放数据重跑（[香港数据快照](../../../v2/data/hk/README.md)），最新数值以 `experiments/results/` 与最终报告为准；本目录 `section.md`、`slides.md` 中的数值来自原合成数据，保留为过程记录。

本模块负责统一 SQLite 模式的备份、恢复、一致性核验、保留策略和运行监测。实验数据全部为合成数据；恢复脚本不代表生产部署或云服务性能承诺。

| 成果 | 内容 |
| --- | --- |
| [章节稿](section.md) | 报告第3.3、8.2–8.3节 |
| [展示文字](slides.md) | 建议第9–10页 |
| [参考文献](references.md) | IEEE 格式 |
| [恢复实验](experiments/recovery.py) | SQLite 在线备份、故障注入、恢复后核验 |
| [实验结果](experiments/results/recovery.json) | 环境、源码摘要与实测结果 |

复现：

```text
python -X utf8 -B docs/modules/lj/v2/experiments/recovery.py --output docs/modules/lj/v2/experiments/results/recovery.json
```

Windows 使用 `-X utf8` 是为了让依赖 UTF-8 文档的既有实验在非 UTF-8 系统区域设置下可复现。
