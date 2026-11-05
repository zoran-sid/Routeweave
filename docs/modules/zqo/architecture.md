# 总体架构与数据流

## 总体架构

SkyRoute以版本化输入连接数据管理与三维规划。源数据存储承接YHT的数据模型，发布目录控制哪些输入可以组合使用。LQ提供风险规则与治理条件，ZC在完整输入上生成航线，LJ观察服务状态与恢复过程。

```mermaid
flowchart LR
  A[三维场景/空域/暴露与源清单<br/>YHT scene + seal] --> B[质量门禁与导出<br/>YHT check_scene + adapters]
  B --> C[风险时段编译<br/>LQ compile_profiles]
  C --> D[窗口绑定与两组版本映射<br/>ZQO prepare_source]
  D --> E[原子发布目录<br/>完整来源 + 不可变快照 + 当前指针]
  E --> F[固定发布与任务窗口校验<br/>ZQO pin / query / status]
  F --> G[Q1规划 / Q2完整航段检查<br/>ZC plan / assess_segment]
  G --> H[当前推荐或历史查看验收<br/>LJ validate_result]
  E --> I[成功审计 + 待发送事件<br/>同一事务]
  E --> J[失败尝试记录<br/>回滚后独立写入]
  I --> K[运行记录与恢复检查]
  J --> K
  E --> L[历史重开与源清单核对]
```

图示链路已实际消费五个模块的输出，使用YHT完整零基面平地合成场景、固定任务窗口和SQLite目录。[本轮集成证据](../../integration/zqo-evidence.md)保存输入、版本映射和结果。生产源存储、身份认证、外部通知及监控服务另按部署设计实现。

## 数据发布与查询交错

```mermaid
sequenceDiagram
  participant U as 空域维护与评审
  participant D as 发布目录
  participant Q as 航线查询
  participant P as 规划与风险检查
  U->>D: 提交候选发布和预期基线v1
  Q->>D: 固定已提交发布v1
  D-->>Q: 五类不可变输入
  Q->>P: 按v1与任务窗计算
  U->>D: 事务写入v2 审计 待发送事件
  Note over D: 提交时原子切换当前指针
  P-->>Q: v1结果
  Q->>D: 用新读取核对当前发布
  D-->>Q: 当前为v2
  Note over Q: v1结果标记过时并保留历史
  Q->>P: 用v2复核并重新规划
  P-->>Q: v2结果和版本来源
```

发布在提交前失败时，目录继续指向v1，未提交对象、成功审计和通知一起回滚；随后在独立连接中保存失败请求、候选摘要与原因。失败审计写入也不可用时显式报错。数据库提交成功但响应丢失时，发布者使用同一请求编号查询或重试即可取得原结果。

## 与报告章节衔接

| 报告内容 | 可直接整合的材料 |
| --- | --- |
| 系统与数据架构 | 本页两张图及五个模块的组件职责 |
| 技术选型与一致性 | design第3至5节的候选比较、事务与查询流程 |
| 数据治理与恢复 | LQ治理章节加ZQO发布审计、LJ实际验收材料 |
| 评估与设计权衡 | evaluation中的历史情境与本轮五模块集成证据 |

图的可编辑源文件见 `figures/architecture.mmd` 与 `figures/publication-sequence.mmd`。
