# 跨模块接口与检查

## 本轮实际检查

读取完整课程材料、共同约定、五人交接、ZC设计/评估/接口/原型/结果与PPT文字，基线为`be027dc9c94d2416836f2b8f24fe4e3fee81000c`。其他三模块此版本只有任务记录，不能记作已集成。

`compile_profiles(snapshot, query, profiles)`返回深拷贝的`(snapshot, query)`，保留ZC五类版本语义，使用其内容摘要绑定函数。风险数据附`profile_inputs`作为血缘，新增`risk_model.source`以区分LQ处理含义。失效版本检查继续由ZC执行。

输入profiles为非空区域列表，每个区域含唯一id、3D盒表达的水平范围、source和periods；每个period含带时区的半开valid区间、E与C。实际风险计算只用盒的x/y，z不影响地面包络。输入格式可参考`prototype/test_risk.py:region`。E或C为null产生unknown；无profiles或非法数值由`evaluate`返回unknown。

输出`risk_data.zones`仍使用ZC的`id/box/q`字段。时间覆盖完整的区域编译为最大已知q；缺口编译为已知q加独立unknown区，避免丢失已知硬危险。显式背景覆盖、来源、窗口与五类版本保留。当前合成默认参数不提供公开人口密度到E的映射。

| 负责人 | 可复用内容 | 映射/验收 |
| --- | --- | --- |
| ZC | `compile_profiles`与`assess_segment`，19项测试和三权重联合输出 | r仍为长度/100×q，非负可加，阈值及未知优先级与现有代码一致。21项原测试通过，无需修改搜索 |
| YHT | exposure_profile、risk_model、source_catalog、risk_assessment字段 | 换成真实几何时检查水平投影包络、单位、时间覆盖与索引候选完整性；真实源缺失不得套用合成背景 |
| ZQO | 版本编译、五类引用、不可变对象及发布规则 | 内容摘要不是事务发布；业务清单仍需原子切换，读取时校验数据/模型兼容。变化后重验路线 |
| LJ | 治理验收清单、unknown原因、策略模拟 | 实际角色鉴权、审计落库、故障恢复另行运行，不能把can_publish纯函数当作生产授权服务 |

新模型若改成累计风险硬预算、路径历史相关风险或负权收益，需扩展规划状态并重新证明搜索条件。保持现有可加代理时无需迁移现有ZC输入；LQ适配为新增入口，不覆盖ZC的原始场景和历史结果。
