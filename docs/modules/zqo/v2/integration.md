# v2 对接说明

## v1 到统一数据库的映射

| v1 发布对象 | v2 权威表/接口 | 差异与下游影响 |
| --- | --- | --- |
| components | layer_component + YHT 空间实体表；component_source | 保存关系行，component_id 定位物理 owner；没有权威 JSON blob |
| releases | release + release_layer + release_component | 每个逻辑发布有五层；内容摘要不含物理 rid，因此共享与全量导出语义相同 |
| head | current_release(scene_id PK) | 每场景一个指针，发布时 CAS；读任务首先固定 release_id |
| audit | audit_event + airspace_event | 成功审计/空域变更与 head 同事务 |
| failed_attempts | failed_attempt | 回滚后独立追加；候选不存在也可记录；不能冒充已提交发布 |
| outbox | outbox | 持久事件指针引用成功 audit_event；允许更新投递次数/时间 |
| 幂等请求 | publish_request | 请求摘要包括 actor、expected、内容、来源和窗口；请求号不能换内容 |
| 源版本与查询版本 | release.manifest.provenance + release_layer | `source_versions` 是 YHT 上游版本；`layer_version` 是规范内容摘要，不能把二者当同一编号 |

新增7表和2视图；既有 YHT 实体字段不变。YHT 测试夹具可继续创建不带组件映射的发布，用于独立模式/索引实验；这些旧夹具不能直接设置 `current_release`，`snapshot()` 对未映射版本明确报错。重建 v2 实验库即可使用新模式；现有持久数据库需要另行迁移，不能把 CREATE 脚本当作在线迁移。

## 可执行接口

`experiments/catalog.py` 提供：

- `initialize(path)`：创建统一库、合成 actor/source/risk_model；生产接入需由治理入库流程提供这些行。
- `publish(conn, payload, request_id=..., release_id=..., expected=..., provenance=...)`：完整五层关系数据，默认共享；撤销用新空域行 `state=revoked`、`revoked_at`，不得删除旧限制来表达撤销。
- `snapshot(conn, release_id=None)`：单读事务校验哈希并返回五层数据、逻辑/物理映射、五层版本、源清单、风险窗口、当前/历史状态。不存在、漂移或未映射直接报错。
- `fixture()` / `changed()`：标准库合成数据，仅用于可复现实验。`source_versions=synthetic-v2-1` 与 `compiler_version=synthetic-fixture-1` 明确标识模拟来源。

示例：

```python
import catalog as cat
cat.initialize('/tmp/new-skyroute.db')
c = cat.connect('/tmp/new-skyroute.db')
p = cat.fixture()
cat.publish(c, p, request_id='request-1', release_id='R1', expected=None,
            provenance=cat.provenance())
cat.publish(c, cat.changed(p, revoke=True), request_id='request-2', release_id='R2',
            expected='R1', provenance=cat.provenance())
old = cat.snapshot(c, 'R1')
assert old['freshness'] == 'historical'
assert old['manifest']['provenance']['risk_model_id'] == 'lq-risk-v1'
c.close()
```

`provenance` 必须有 `source_versions`（五层上游版本）、`risk_window`（与发布 valid 窗口完全相等）、`risk_model_id`、`compiler_version`。源清单包含所有输入引用的 source_id。若要支持覆盖窗口包含关系，需同步改门禁和边界测试；本版采取完全匹配合同。

## 查询适配

```sql
-- 在同一个 BEGIN ... COMMIT 读事务内固定 :release。
SELECT query_release_id, owner_release_id, feature_id, rid, layer, source_id
FROM resolved_feature WHERE query_release_id=:release;
SELECT * FROM resolved_source WHERE query_release_id=:release;
-- 地形/覆盖同理，以 component 的 owner_release_id 连接原表。
SELECT tp.* FROM release_component rc JOIN layer_component lc USING(component_id)
JOIN terrain_post tp ON tp.release_id=lc.owner_release_id
WHERE rc.release_id=:release AND rc.layer='terrain';
```

原 `op_a.sql` 的 `:release_id` 是**物理 owner**，并非共享模式的逻辑发布编号；使用前通过 `snapshot()` 核验并从 `mappings` 取得 airspace 的 `owner_release_id`，在同一读事务执行原 SQL。查询结果记录逻辑 release_id，同时保留 component_id/owner_release_id/rid/feature_id。直接把新逻辑发布编号传给旧 SQL 可能遗漏共享图层。候选包围盒相交不替代航段几何验证；空结果不表示质量与覆盖已经合格。

## 后续成员任务

| 成员 | 可复用成果 | 仍需执行 |
| --- | --- | --- |
| YHT | 13项原模式测试保持通过、原索引实验六配置复跑；字典第9节映射补记 | 修复 YHT-V2-05 写入/迁移绕过和 YHT-V2-06 来源不可变性，补自己的回归；确认原索引结论仅适用测量范围 |
| LQ | 发布来源/模型/窗口、失败审计、resolved_source | 审阅本轮；治理质量/职责分离/权限；修复 LQ-V2-01；接真实风险编译输入；利用映射写血缘与追溯 SQL |
| ZC | resolved_feature、组件 owner 映射、可重建 JSON、outbox | 真实 v2 Q1/Q2、query_run.release_id 和缓存依赖；新事务复核 freshness；旧 op_a 绑定 owner |
| LJ | 5处回滚与提交后丢响应证据、failed_attempt、outbox | 进程崩溃/备份恢复、入口失败审计窗口、至少一次投递和消费者去重 |

v2 的这些新增接口由统一模式 CI 中 `test_publication_v2.py` 调用14项事务测试。v1 测试和完整链路独立执行，历史数据不覆写。已知外部缺陷在实验结果的 `known_other_owner_defects` 中保留 `pass=false`；不是事务成功用例，也没有为了通过检查吞掉这些错误。
