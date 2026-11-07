# SkyRoute v2 统一模式 ER 图

逻辑模型见 [YHT 数据字典](../../modules/yht/v2/data-dictionary.md)；可执行 DDL 见 [schema.sql](schema.sql)；设计取舍见 [decisions.md](decisions.md)。

```mermaid
erDiagram
    ACTOR ||--o{ RELEASE : publishes
    RELEASE ||--o| RELEASE : "base_release_id"
    RELEASE ||--|{ RELEASE_LAYER : "five layers"
    RELEASE ||--o{ COVERAGE_TILE : covers
    RELEASE ||--o{ FEATURE : contains
    RELEASE ||--o{ TERRAIN_SURFACE : publishes
    TERRAIN_SURFACE ||--o{ TERRAIN_POST : has
    FEATURE ||--o| BUILDING : "subtype"
    FEATURE ||--o| AIRSPACE_RESTRICTION : "subtype"
    FEATURE ||--o| EXPOSURE_ZONE : "subtype"
    FEATURE ||--o{ AIRSPACE_EVENT : "(release_id, restriction_id)"
    AIRSPACE_EVENT |o--o| AIRSPACE_EVENT : "previous_event_id"
    ACTOR ||--o{ AIRSPACE_EVENT : performs
    SOURCE ||--o{ FEATURE : provides
    SOURCE ||--o{ COVERAGE_TILE : provides
    SOURCE ||--o{ TERRAIN_SURFACE : provides
    RISK_MODEL ||--o{ EXPOSURE_ZONE : scores
    ACTOR |o--o{ RISK_MODEL : approves
    ACTOR ||--o{ AUDIT_EVENT : performs
    RELEASE |o--o{ AUDIT_EVENT : "bound release"
    RELEASE |o--o{ LINEAGE_EDGE : records

    RELEASE {
        text release_id PK
        text status "draft|published|superseded|retired"
        text base_release_id FK
        text valid_lo
        text valid_hi
        text published_at
        text content_hash
        json manifest
    }
    RELEASE_LAYER {
        text release_id PK, FK
        text layer PK "scene|terrain|airspace|exposure|sources"
        text layer_version
        text content_hash
        int complete
    }
    COVERAGE_TILE {
        text release_id PK, FK
        text layer PK
        text tile_id PK
        int complete
        text source_id FK
    }
    FEATURE {
        int rid PK
        text release_id FK "UNIQUE(release_id, feature_id)"
        text feature_id
        text layer
        text feature_type "building|airspace|exposure"
        text source_id FK
        text quality
        text sensitivity
        json attrs
    }
    BUILDING {
        int rid PK, FK
        text footprint_wkt
        text solid_wkt
        real base_z
        real top_z
        real height_m
        text height_source FK
    }
    AIRSPACE_RESTRICTION {
        int rid PK, FK
        text restriction_id "= feature_id"
        text kind "no_fly|height_limit"
        real floor_z
        real ceiling_m
        text effective_lo
        text effective_hi
        text state "fixed per release"
        real forbid_lo_z "generated"
        real forbid_hi_z "generated"
    }
    EXPOSURE_ZONE {
        int rid PK, FK
        text zone_id "= feature_id"
        real exposure_e
        real consequence_c
        real q "= E x C"
        text risk_model_id FK
    }
    TERRAIN_SURFACE {
        text release_id PK, FK
        text terrain_id PK
        text surface_type
        int flat
    }
    TERRAIN_POST {
        text release_id PK, FK
        text terrain_id PK, FK
        int ix PK
        int iy PK
        real z
    }
    AIRSPACE_EVENT {
        text event_id PK
        text release_id FK
        text restriction_id FK
        text action "publish|update|revoke|expire"
        text occurred_at "monotonic per restriction"
        text actor_id FK
    }
    SOURCE {
        text source_id PK
        text source_type
        text license
        text sensitivity
    }
    RISK_MODEL {
        text risk_model_id PK
        text status "draft|approved|retired"
        json params
        text approved_by FK
    }
    ACTOR {
        text actor_id PK
        text role
    }
    ACCESS_POLICY {
        text policy_id PK
        text role
        text resource
        text action
        text max_sensitivity
    }
    LINEAGE_EDGE {
        text edge_id PK
        text from_kind
        text from_id
        text to_kind
        text to_id
        text activity
    }
    AUDIT_EVENT {
        text event_id PK
        text at
        text actor_id FK
        text action
        text result
        text release_id FK
    }
```

## 表用途、时间字段与版本关系

| 表 | 用途 | 时间字段 | 版本关系 | 负责人 |
| --- | --- | --- | --- | --- |
| `release` | 一次不可变发布 | `valid_lo/hi`、`created_at`、`published_at`、`retired_at` | 版本根；`base_release_id` 指向父发布 | ZQO 细化 |
| `release_layer` | 五层内容版本与哈希 | `generated_at` | 发布前五层必须齐全 | ZQO 细化 |
| `coverage_tile` | 每层覆盖完整性 | `valid_lo/hi` | 随发布；主键含 `release_id`、`layer` | YHT |
| `feature` | 建筑、空域、暴露的公共头 | `valid_lo/hi`、`recorded_at` | 随发布；`feature_id` 跨发布稳定 | YHT |
| `building` | 建筑三维体 | — | 随 `feature` | YHT |
| `terrain_surface`、`terrain_post` | 地形面与格网点 | `valid_lo/hi` | 随发布；主键含 `release_id` | YHT |
| `airspace_restriction` | 禁飞或限高体 | `effective_lo/hi`、`published_at`、`revoked_at` | 状态随发布固定；撤销写新发布 | YHT，ZQO 细化事务 |
| `airspace_event` | 发布、更新、撤销、到期事件 | `occurred_at`、`effective_at` | 只追加；指向所属发布中的限制 | ZQO 细化 |
| `exposure_zone` | 地面暴露分区与 E/C/q | `valid_lo/hi` | 随发布；引用风险模型版本 | YHT，LQ 细化 |
| `risk_model` | 风险模型版本 | `valid_lo/hi` | 独立于五层；只有 `approved` 可用 | LQ |
| `source` | 来源、许可、精度 | `acquired_at`、`valid_lo/hi` | 长期；被发布引用 | YHT |
| `actor`、`access_policy` | 操作者与访问策略 | `created_at` | 策略按状态版本化 | LQ |
| `lineage_edge` | 对象级血缘 | `at` | 可绑定发布 | LQ |
| `audit_event` | 操作与查询审计 | `at` | 只追加；可绑定发布 | LQ |

R*Tree 虚表（`rtree_building`、`rtree_airspace`、`rtree_exposure`）是派生索引，由触发器维护，可以从基表重建，不出现在 ER 图中。

## ZQO 发布扩展（v2 第2棒）

```mermaid
erDiagram
    release ||--o{ release_layer : has
    release_layer ||--o| release_component : resolves
    layer_component ||--o{ release_component : reused_by
    release ||--o{ layer_component : physically_owns
    layer_component ||--o{ component_source : lists
    source ||--o{ component_source : referenced_by
    release ||--o| current_release : current_in_scene
    release ||--o| publish_request : committed_request
    release ||--o{ audit_event : audited
    audit_event ||--o| outbox : delivered
    release ||--o{ failed_attempt : observed_head
```

`failed_attempt.observed_release_id` 可空；候选编号仅为文本，可指向从未提交的发布。历史发布与组件不得删除。完整字段见 schema.sql 第2节；逻辑发布和物理 owner 的查询区别见 [ZQO 接口](../../modules/zqo/v2/integration.md)。

## LQ 治理扩展（v2 第3棒）

```mermaid
erDiagram
    release ||--o{ risk_dataset : compiled_for
    layer_component ||--o{ risk_dataset : exposure_input
    risk_model ||--o{ risk_dataset : evaluates
    risk_model ||--o| risk_model_control : activated_separately
    risk_dataset ||--o{ risk_input_period : preserves
    risk_dataset ||--o{ derived_risk : produces
    risk_dataset ||--o{ quality_check : checked
    exposure_zone ||--o{ derived_risk : spatial_scope
    source ||--o{ derived_risk : provenance
    actor ||--o{ governance_request : authors
    governance_request ||--o| governance_approval : reviewed
    actor ||--o{ governance_approval : independent_reviewer
```

`risk_dataset`的window_lo/hi必须等于绑定release窗口，component_id必须解析到同次逻辑发布的exposure层；zone_rid引用物理owner行。时段输入及结果按dataset_id留存，封存后不可变。`risk_model_control`保存enabled/操作者/时间/原因，不改历史模型语义。`quality_check`按checked_at追加。

`governance_request`保存作者和候选内容摘要；审批保存reviewer/decision/at。数据库拒绝作者自审，发布网关核对已批准摘要后调用ZQO事务。lineage_edge新增component/dataset端点，存在性和dataset依赖由触发器校验。现有23实体加7个LQ实体共30个；ZC 正式查询表见下节。

## ZC 查询与结果追溯（v2 第4棒）

```mermaid
erDiagram
    release ||--o{ query_run : pinned_by
    actor ||--o{ query_run : submits
    route_graph_cache |o--o{ query_run : served
    query_run ||--o| route_result : feasible_route
    route_result ||--o{ route_segment_source : segment_risk
    layer_component ||--o{ route_segment_source : exposure_component
    exposure_zone ||--o{ route_segment_source : zone
    risk_dataset ||--o{ route_segment_source : values_from
    release ||--o{ route_graph_cache : keyed_by
    risk_dataset ||--o{ route_graph_cache : risk_input
    route_graph_cache |o--o{ route_graph_cache : carried_or_patched_from
```

| 表 | 用途 | 时间字段 | 版本关系 | 负责人 |
| --- | --- | --- | --- | --- |
| `query_run` | 一次 Q1：发布、提交者、任务窗口、起终点、配置、取数路径、状态 | `requested_at`、`window_lo/hi` | 绑定逻辑发布；`freshness` 由触发器按当前指针判定 | ZC |
| `route_result` | 可行航线的度量与航点 | — | 随 `query_run`，只追加 | ZC |
| `route_segment_source` | 航段的风险来源（LQ 操作 C 合同） | — | 组件、分区、数据集须属于查询发布，数据集窗口覆盖任务窗口 | ZC |
| `route_graph_cache` | 派生图元数据：发布、数据集、搜索域、窗口、配置、内容摘要、来源方式 | `window_lo/hi`、`created_at` | 按发布记账；`carried`/`patched` 指向上一发布同键图 | ZC |

现有30个实体加4个 ZC 实体共34个；`test_schema` 实体清单同步更新。图本体保存在规划服务内存，以 `payload_hash` 索引，可由发布重建。
