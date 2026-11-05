# LJ：运维保障与验收支持

状态：**模块可交付，实际部署接入待检查**。日期：2026-11-05。共同基线：`starter-v0`。

本模块把 Q1/Q2 查询、版本发布和异常恢复转化为可执行的运行保障规则。核心原则是：结果必须绑定完整版本；缺失、过期、版本混用、超预算或恢复校验失败时返回 `unknown` 或停止受影响操作，不能把异常显示成成功或无风险。

## 交付入口

| 成果 | 内容 |
| --- | --- |
| [运维与验收设计](design.md) | 运行状态、指标、日志、告警、恢复和权限边界 |
| [验收情境与结果](evaluation.md) | 正常、数据缺失、更新失败、恢复和预算情境 |
| [跨模块集成](integration.md) | 与 ZC、LQ、ZQO 的字段映射和接入判据 |
| [两页展示文字](slides/notes.md) | 对应第9–10页的可编辑讲稿内容 |
| [验收原型](prototype/acceptance.py) | 标准库实现的结果校验、更新失效和发布恢复检查 |
| [原型测试](prototype/test_acceptance.py) | 可复现的验收情境测试 |

## 复现

在仓库根目录执行：

```bash
python3 -m unittest discover -s docs/modules/lj/prototype -v
```

原型只验证运行规则和接口语义，不代表已经部署身份服务、数据库审计或生产监控。

`validate_result` 默认验收当前推荐；带有 ZQO `freshness=stale` 的结果只能显式使用
`purpose="history"` 查看，`freshness=unavailable` 始终失败。版本字段必须完整有效，
指标和耗时必须是有限、非负且非布尔数值。
