# SkyRoute 数据字典（v2）

状态：v2 跨模块数据契约草案，供 ZQO、LQ、ZC、LJ 对接。基线 `starter-v0`，日期 2026-11-06，负责人 YHT。

本文件定义 SkyRoute 数据管理平台中城市三维环境、动态空域、地面暴露与风险三类数据的逻辑实体、字段、单位、来源、更新频率、敏感级别和版本语义。它不规定最终部署产品，也不替代各模块自己的接口说明；字段含义变更必须记录影响范围和迁移方式。

## 1. 使用约定

### 1.1 范围与权威边界

- 本字典覆盖 YHT 主责的数据模型与存储层：对象标识、三维几何、坐标与高度基准、来源与质量、覆盖范围、有效期、版本、血缘、审计。
- 空域“是否允许发布”由 ZQO 的发布流程决定；风险公式与阈值由 LQ 决定；航线可行性由 ZC 决定；运行验收由 LJ 决定。本字典只定义这些模块交换数据时需要的公共字段，不替其他模块作安全结论。
- 所有示例、名称、机构、建筑和人口代理均为合成数据。真实数据接入时必须重新核对来源许可、坐标转换、精度和个人信息处理要求。

### 1.2 空间基准

| 项目 | 约定 |
| --- | --- |
| 坐标参考系 | 局部直角坐标 `x/y/z`，单位米；`x` 向东、`y` 向北、`z` 向上 |
| 原点与范围 | 合成片区原点在西南角地面；基线范围 `x∈[0,600]`、`y∈[0,600]`、`z∈[0,160]` |
| 垂直基准 | `z=0` 是片区共同参考平面；地形高度另用 `terrain_post.z` 表示；真实接入时记录高程基准与转换参数 |
| SRID | PostGIS 使用 `0` 表示无单位局部坐标；禁止把局部米制几何标成 WGS-84 的 `4326` |
| 精度 | 平面精度 `accuracy_xy_m`、垂直精度 `accuracy_z_m` 以米记录；未知时写 `NULL` 并将 `quality` 标为 `unknown` |
| 几何类型 | 建筑和空域用三维体 `PolyhedralSurfaceZ`；地面分区和建筑轮廓用二维面 `Polygon`；地形格网用点或 TIN |
| 边界语义 | 面边界包含在内；三维体表面视为实体边界；查询缓冲距离另加，不把“接触”自动当成安全 |

### 1.3 时间基准

| 项目 | 约定 |
| --- | --- |
| 时区 | 所有时刻用带时区的 ISO 8601，基线统一 UTC；数据库类型 `timestamptz` |
| 区间 | 有效期用 `tstzrange`，统一 `[start, end)`：起点包含、终点不包含 |
| 三类时间 | `valid` 是数据描述的现实有效期；`recorded_at` 是平台获知该数据的时间；`published_at` 是发布生效时间。三者不能混用 |
| 查询窗口 | Q1/Q2 必须给出规划时刻、出发时间和规划窗口；窗口未覆盖或数据过期时返回 `unknown`，不默认安全 |
| 精度 | 合成数据统一到秒；真实数据接入时记录源时间精度和时钟偏差 |
| 时钟 | `created_at`、`published_at` 由平台写入；`valid` 由数据提供方给出，平台只校验不改写 |

### 1.4 标识、空值与质量

- `release_id` 标识一次不可变发布；`feature_id` 是跨发布稳定的对象标识；`rid` 是发布内的代理键，便于空间表连接。
- `feature_id` 在同一图层内稳定；对象删除后用新发布表达，不原地删除历史发布中的行。
- `NULL` 表示“字段没有提供”；`quality='unknown'` 表示“提供方明确说不知道”。两者都不能当作安全值。
- `quality` 取值：`observed`（实测/直接采集）、`derived`（由其他数据计算）、`assumed`（合成或假设）、`unknown`（未知）。
- 任何依赖缺失高度、缺失风险、覆盖不完整或版本不一致的查询，结果必须是 `unknown` 或显式拒绝，不能回退到默认值。

### 1.5 敏感级别

本字典先定义四级，供 LQ 在治理章节细化和替换；级别按“最严格的输入”向上聚合。

| 级别 | 含义 | 典型数据 | 发布与访问 |
| --- | --- | --- | --- |
| `public` | 可公开的合成或已脱敏数据 | 发布清单、场景边界、合成示例 | 可公开引用 |
| `internal` | 组织内部运行使用 | 建筑轮廓与高度、地形、覆盖瓦片、来源元数据 | 仅查询与发布角色 |
| `restricted` | 可能影响空域安全或暴露隐私的聚合数据 | 空域限制、地面暴露分区、查询审计 | 按角色最小权限，禁止外传原始明细 |
| `sensitive` | 可识别个人、精确脆弱点或凭据 | 原始人口/轨迹、精确医院点位、账号密钥 | 不进入本平台共享层；单独审批与脱敏 |

规则：

- 对象敏感级别不得低于其来源、几何和属性中的最高级别。
- 聚合可以降低敏感级别，但必须记录聚合粒度、k 匿名或差分隐私参数；不能只改标签。
- 查询结果继承所读对象和风险模型的最高敏感级别；Q2 的来源与审计字段本身按 `restricted` 处理。

### 1.6 版本与发布

YHT 内容层固定为五类：`scene`、`terrain`、`airspace`、`exposure`、`sources`。每次发布为五层各生成一个内容版本，并写入发布清单；版本是内容身份，不是数字签名。

| 字典层 | 对应共同约定 | 说明 |
| --- | --- | --- |
| `scene` | `scene` | 建筑、障碍、场景边界和场景级元数据 |
| `terrain` | `scene` 的地形部分 | 单独版本化，便于地形更新不影响建筑版本 |
| `airspace` | `airspace` | 限制体、有效期、状态和发布事件 |
| `exposure` | `risk_data` | 地面暴露分区、E/C/q 和风险模型引用 |
| `sources` | 元数据 | 来源清单的密封版本，不含空间对象 |

`risk_model` 是 LQ 的模型版本，不塞进上述五层；`exposure` 行通过 `risk_model_id` 引用它。Q1/Q2 结果同时返回五层版本和 `risk_model` 版本，任一不一致即视为不可比。

发布规则：

- 发布后行不可变；更新通过新 `release_id` 全量替换或增量复制，旧发布保留只读。
- `release_layer.content_hash` 是该层规范序列化的 SHA-256；`release.content_hash` 是五层版本的组合哈希。
- `release.status='published'` 后禁止原地修改；`retired` 只表示不再作为当前版本，不删除历史。
- 查询必须绑定一个 `release_id`；跨发布拼接对象属于版本混用，返回 `unknown`。

## 2. 实体总览

| 实体 | 作用 | 主要来源 | 更新频率 | 敏感级别 |
| --- | --- | --- | --- | --- |
| `release` | 一次不可变发布 | 平台发布流程 | 每次发布 | `internal` |
| `release_layer` | 五层内容版本与哈希 | 平台生成 | 每次发布 | `public` |
| `source` | 数据来源、许可、精度 | 采集登记 | 来源变更时 | `internal` |
| `coverage_tile` | 分层覆盖瓦片与完整性 | 质检/发布 | 每次发布 | `internal` |
| `feature` | 空间对象公共头 | 各数据源 | 随发布 | `internal` |
| `building` | 建筑三维体与高度 | 城市 GIS/BIM/LiDAR | 季度或年度 | `internal` |
| `terrain_surface` | 地形格网/TIN 元数据 | 测绘/LiDAR | 年度 | `internal` |
| `terrain_post` | 地形格网点 | 测绘/LiDAR | 年度 | `internal` |
| `airspace_restriction` | 禁飞/限高体 | 空域管理机构 | 事件驱动，分钟级 | `restricted` |
| `airspace_event` | 发布、变更、撤销事件 | 空域发布流程 | 事件驱动 | `restricted` |
| `exposure_zone` | 地面暴露分区与 E/C/q | 人口/POI/派生 | 月或季度 | `restricted` |
| `risk_model` | 风险模型版本与参数 | LQ | 模型评审时 | `restricted` |
| `actor` | 操作者与角色 | 身份系统 | 人员变更时 | `internal` |
| `access_policy` | 角色、资源、敏感级别规则 | LQ/平台 | 策略变更时 | `restricted` |
| `lineage_edge` | 对象级血缘边 | 采集/派生任务 | 每次生成 | `internal` |
| `audit_event` | 发布与查询审计 | 平台 | 每次操作 | `restricted` |

### 2.1 数据类与更新频率

| 数据类 | 主要实体 | 典型来源 | 基线规模 | 更新频率 | 三年假设 |
| --- | --- | --- | --- | --- | --- |
| 城市三维环境 | `building`、`terrain_surface`、`terrain_post` | 城市 GIS、BIM、LiDAR、测绘 | 25 栋、36 个覆盖瓦片、961 个地形点 | 建筑季度或年度；地形年度 | 10 个片区约 2,400 栋、9,610 个地形点 |
| 动态空域 | `airspace_restriction`、`airspace_event` | 空域管理机构接口、人工发布 | 3 个限制体 | 事件驱动，分钟级 | 每日 20 条事件，约 100 条活动限制 |
| 地面暴露与风险 | `exposure_zone`、`risk_model` | 人口、POI、土地利用、LQ 派生 | 6 个分区、1 个风险模型版本 | 月或季度；模型评审时 | 60 个分区、每月 1 版 |

表中的三年数字是规模假设，不是实测；估算方法见第 8 节。

## 3. 实体字段

### 3.1 `release`（发布）

来源：平台发布流程；更新：每次发布；敏感级别：`internal`；生命周期：`draft → published → superseded/retired`。

| 字段 | 类型 | 必填 | 单位/取值 | 说明 |
| --- | --- | --- | --- | --- |
| `release_id` | `text` | 是 | 例 `rel-district-0007` | 主键，全局唯一，发布后不变 |
| `scene_id` | `text` | 是 | 例 `yht-synthetic-district-v1` | 场景标识；同一场景可有多次发布 |
| `schema_version` | `text` | 是 | 例 `yht-scene-0.1` | 本字典与 JSON/表结构的版本 |
| `baseline` | `text` | 是 | 例 `starter-v0` | 共同约定基线 |
| `status` | `enum` | 是 | `draft`/`published`/`superseded`/`retired` | 只有 `published` 可被查询 |
| `base_release_id` | `text` | 否 | 引用 `release.release_id` | 增量发布的父版本；全量发布为 `NULL` |
| `valid` | `tstzrange` | 是 | UTC | 该发布所描述数据的有效窗口 |
| `created_at` | `timestamptz` | 是 | UTC | 平台创建时间 |
| `published_at` | `timestamptz` | 否 | UTC | 正式可查询时间；`draft` 时为空 |
| `retired_at` | `timestamptz` | 否 | UTC | 停止作为当前版本的时间 |
| `actor_id` | `text` | 是 | 引用 `actor.actor_id` | 发布操作者 |
| `content_hash` | `text` | 是 | 64 位十六进制 | 五层版本组合的 SHA-256 |
| `manifest` | `jsonb` | 是 | JSON | 层版本、要素计数、覆盖瓦片摘要、生成工具版本 |
| `notes` | `text` | 否 | 自由文本 | 变更原因、限制和回滚说明 |

约束：`published_at IS NULL` 仅允许 `status='draft'`；`valid` 非空且 `lower(valid) < upper(valid)`；`content_hash` 为 64 位小写十六进制。

### 3.2 `release_layer`（发布层）

来源：平台生成；更新：每次发布；敏感级别：`public`；生命周期：随发布保留。

| 字段 | 类型 | 必填 | 单位/取值 | 说明 |
| --- | --- | --- | --- | --- |
| `release_id` | `text` | 是 | 引用 `release` | 联合主键之一 |
| `layer` | `enum` | 是 | `scene`/`terrain`/`airspace`/`exposure`/`sources` | 联合主键之一 |
| `layer_version` | `text` | 是 | 例 `mock-scene-a1b2c3d4e5f6` | 该层内容版本 |
| `content_hash` | `text` | 是 | 64 位十六进制 | 该层规范序列化哈希 |
| `feature_count` | `integer` | 是 | ≥0 | 该层对象数；`sources` 层为来源条数 |
| `generated_at` | `timestamptz` | 是 | UTC | 该层生成时间 |
| `complete` | `boolean` | 是 | 真/假 | 该层覆盖是否完整；假值使相关查询返回 `unknown` |

主键：`(release_id, layer)`。约束：五个层必须齐全；`feature_count` 与清单计数一致；`complete=false` 不得被查询解释为无限制。

### 3.3 `source`（来源）

来源：采集登记；更新：来源或许可变更时；敏感级别：`internal`；生命周期：长期，发布时引用；被非 draft 发布引用后不可原地修改。

| 字段 | 类型 | 必填 | 单位/取值 | 说明 |
| --- | --- | --- | --- | --- |
| `source_id` | `text` | 是 | 例 `SRC-FOOTPRINT` | 主键 |
| `name` | `text` | 是 | 自由文本 | 来源名称；合成数据标 `synthetic` |
| `source_type` | `enum` | 是 | `gis`/`bim`/`lidar`/`authority_feed`/`census`/`derived`/`synthetic` | 采集或生成方式 |
| `owner_org` | `text` | 是 | 机构/团队缩写 | 数据责任方 |
| `license` | `text` | 是 | SPDX 或自定义 | 使用许可；合成数据用 `CC0-1.0 (synthetic)` |
| `acquisition_method` | `text` | 是 | 自由文本 | 测绘、导出、接口、推算等 |
| `acquired_at` | `timestamptz` | 是 | UTC | 源数据获取时间 |
| `update_frequency` | `enum` | 是 | `event`/`hourly`/`daily`/`monthly`/`quarterly`/`annual`/`static` | 来源的典型更新节奏；实际发布仍以 `release.valid` 为准 |
| `accuracy_xy_m` | `double precision` | 否 | 米，≥0 | 平面精度；未知为 `NULL` |
| `accuracy_z_m` | `double precision` | 否 | 米，≥0 | 垂直精度；未知为 `NULL` |
| `valid` | `tstzrange` | 否 | UTC | 来源数据自身有效期 |
| `sensitivity` | `enum` | 是 | 四级 | 来源整体敏感级别 |
| `contact_ref` | `text` | 否 | 工单/接口编号 | 不存个人联系方式 |
| `notes` | `text` | 否 | 自由文本 | 许可限制、已知偏差 |

`source_id` 是来源的身份，不是可覆盖的配置行。被任一非 draft 发布（直接引用，或经 `component_source` 映射）引用后，`source` 行禁止 `UPDATE`/`DELETE`；许可、精度或联系方式变化时登记新的 `source_id`，由新发布引用。旧发布重开仍解析旧行，因此历史来源不会随维护操作漂移。实现见 [schema.sql](../../../v2/schema/schema.sql) 的 `source_immutable_update/delete` 与 `source_provenance_usage`，边界见 [决策 S-05/S-08](../../../v2/schema/decisions.md)。

### 3.4 `coverage_tile`（覆盖瓦片）

来源：发布质检；更新：每次发布；敏感级别：`internal`；生命周期：随发布保留。

| 字段 | 类型 | 必填 | 单位/取值 | 说明 |
| --- | --- | --- | --- | --- |
| `release_id` | `text` | 是 | 引用 `release` | 所属发布；联合主键之一 |
| `layer` | `enum` | 是 | `scene`/`terrain`/`airspace`/`exposure` | 覆盖所属层；联合主键之一 |
| `tile_id` | `text` | 是 | 例 `T-03-04` | 联合主键之一；编号在每次发布、每层重复出现 |
| `tile_x` | `integer` | 是 | ≥0 | 瓦片列号 |
| `tile_y` | `integer` | 是 | ≥0 | 瓦片行号 |
| `bounds` | `geometry(Polygon,0)` | 是 | 米 | 瓦片平面范围；基线 100 m × 100 m |
| `complete` | `boolean` | 是 | 真/假 | 该瓦片数据是否完整 |
| `quality` | `enum` | 是 | 四级质量 | 该瓦片整体质量 |
| `source_id` | `text` | 是 | 引用 `source` | 主要来源 |
| `valid` | `tstzrange` | 是 | UTC | 该瓦片覆盖的时间范围 |
| `checksum` | `text` | 是 | 64 位十六进制 | 瓦片内容哈希，用于发布核对 |

主键：`(release_id, layer, tile_id)`；`(release_id, layer, tile_x, tile_y)` 唯一。约束：同一发布、同一层的瓦片不可重叠；所有瓦片面积之和必须等于场景边界面积；`complete=false` 的瓦片必须能在发布清单中定位。

### 3.5 `feature`（空间对象公共头）

来源：各数据源；更新：随发布；敏感级别：`internal`；生命周期：随发布保留，新发布复制。

| 字段 | 类型 | 必填 | 单位/取值 | 说明 |
| --- | --- | --- | --- | --- |
| `rid` | `bigint` | 是 | 全局唯一 | 主键；空间表连接的代理键，每次发布的每个对象一个新值 |
| `release_id` | `text` | 是 | 引用 `release` | 所属发布 |
| `feature_id` | `text` | 是 | 例 `B-001`、`NF-001` | 跨发布稳定的对象标识 |
| `layer` | `enum` | 是 | 五层 | 对象所属层 |
| `feature_type` | `enum` | 是 | `building`/`airspace`/`exposure` | 子类型 |
| `name` | `text` | 否 | 自由文本 | 人类可读名称；合成数据可为空 |
| `source_id` | `text` | 是 | 引用 `source` | 主要来源 |
| `quality` | `enum` | 是 | 四级质量 | 对象整体质量 |
| `valid` | `tstzrange` | 是 | UTC | 对象有效期 |
| `recorded_at` | `timestamptz` | 是 | UTC | 该对象进入平台的时间 |
| `sensitivity` | `enum` | 是 | 四级 | 对象敏感级别 |
| `attrs` | `jsonb` | 否 | JSON | 子类型扩展字段；不得替代已定义的公共字段 |
| `geom_kind` | `text` | 是 | `polygon`/`polyhedral`/`point`/`tin` | 几何类型标记 |

约束：`(release_id, feature_id)` 唯一；同一 `rid` 在 `building`、`airspace_restriction`、`exposure_zone` 中最多出现一次；`feature.layer` 必须与子类型一致。

### 3.6 `building`（建筑）

来源：城市 GIS/BIM/LiDAR；更新：季度或年度；敏感级别：`internal`；生命周期：随场景发布。

| 字段 | 类型 | 必填 | 单位/取值 | 说明 |
| --- | --- | --- | --- | --- |
| `rid` | `bigint` | 是 | 引用 `feature` | 主键兼外键 |
| `footprint` | `geometry(Polygon,0)` | 是 | 米 | 建筑底面轮廓；必须闭合、简单、面积大于 0 |
| `solid` | `geometry(PolyhedralSurfaceZ,0)` | 是 | 米 | 三维体；由底面和 `base_z`/`top_z` 拉伸得到 |
| `base_z` | `double precision` | 是 | 米 | 底面高程 |
| `top_z` | `double precision` | 是 | 米 | 顶面高程 |
| `height_m` | `double precision` | 是 | 米 | `top_z - base_z`，保留 0.1 m 精度 |
| `footprint_source` | `text` | 是 | 引用 `source` | 轮廓来源；可与高度来源不同 |
| `height_source` | `text` | 是 | 引用 `source` | 高度来源 |
| `height_method` | `enum` | 是 | `measured`/`derived`/`assumed`/`unknown` | 高度获取方式 |
| `roof_type` | `text` | 否 | 自由文本 | 平顶、坡顶等；不影响碰撞判定 |
| `is_landmark` | `boolean` | 是 | 真/假 | 仅用于展示，不改变查询语义 |

约束：`top_z > base_z`；`abs(height_m - (top_z-base_z)) <= 1e-6`；`ST_IsValid(footprint)` 且 `ST_IsValid(solid)`；`footprint` 必须落在场景边界内；`solid` 的二维投影必须与 `footprint` 一致（由发布质检检查）。

### 3.7 `terrain_surface`（地形面）

来源：测绘/LiDAR；更新：年度；敏感级别：`internal`；生命周期：随场景发布。

| 字段 | 类型 | 必填 | 单位/取值 | 说明 |
| --- | --- | --- | --- | --- |
| `release_id` | `text` | 是 | 引用 `release` | 所属发布；联合主键之一 |
| `terrain_id` | `text` | 是 | 例 `TER-001` | 联合主键之一；编号可在各发布中重复 |
| `surface_type` | `enum` | 是 | `grid`/`tin` | 规则格网或三角网 |
| `bounds` | `geometry(Polygon,0)` | 是 | 米 | 地形覆盖范围 |
| `post_spacing_m` | `double precision` | 否 | 米，>0 | 格网间距；TIN 为 `NULL` |
| `vertical_datum` | `text` | 是 | 例 `local-z0` | 垂直基准；真实接入记录 EGM/WGS84 转换 |
| `flat` | `boolean` | 是 | 真/假 | 是否全为 `z=0` 的平地；非平地需额外碰撞处理 |
| `min_z` | `double precision` | 是 | 米 | 最低点 |
| `max_z` | `double precision` | 是 | 米 | 最高点 |
| `geom` | `geometry` | 否 | `PolyhedralSurfaceZ`/`TIN` | TIN 或连续曲面；格网可只存点 |
| `source_id` | `text` | 是 | 引用 `source` | 地形来源 |
| `quality` | `enum` | 是 | 四级质量 | 整体质量 |
| `valid` | `tstzrange` | 是 | UTC | 地形有效期 |
| `checksum` | `text` | 是 | 64 位十六进制 | 点/面集合哈希 |

主键：`(release_id, terrain_id)`。约束：`max_z >= min_z`；`flat=true` 时 `min_z=max_z=0`；格网点必须覆盖 `bounds` 且不重复；非平地查询不得沿用平地快速路径。

### 3.8 `terrain_post`（地形格网点）

来源：测绘/LiDAR；更新：年度；敏感级别：`internal`；生命周期：随地形面保留。

| 字段 | 类型 | 必填 | 单位/取值 | 说明 |
| --- | --- | --- | --- | --- |
| `release_id` | `text` | 是 | 引用 `terrain_surface` | 联合主键 |
| `terrain_id` | `text` | 是 | 引用 `terrain_surface` | 联合主键 |
| `ix` | `integer` | 是 | ≥0 | 列号；联合主键 |
| `iy` | `integer` | 是 | ≥0 | 行号；联合主键 |
| `x` | `double precision` | 是 | 米 | 东向坐标 |
| `y` | `double precision` | 是 | 米 | 北向坐标 |
| `z` | `double precision` | 是 | 米 | 高程 |
| `quality` | `enum` | 是 | 四级质量 | 单点质量 |
| `source_id` | `text` | 是 | 引用 `source` | 单点来源 |

主键：`(release_id, terrain_id, ix, iy)`，外键 `(release_id, terrain_id) → terrain_surface`。约束：`x/y` 在父地形 `bounds` 内；同一地形内 `(x,y)` 不重复；`post_spacing_m` 与实际格网间距一致。

### 3.9 `airspace_restriction`（空域限制）

来源：空域管理机构/模拟发布；更新：事件驱动，分钟级；敏感级别：`restricted`；生命周期：发布 → 生效 → 过期/撤销。

| 字段 | 类型 | 必填 | 单位/取值 | 说明 |
| --- | --- | --- | --- | --- |
| `rid` | `bigint` | 是 | 引用 `feature` | 主键兼外键 |
| `restriction_id` | `text` | 是 | 例 `NF-001`、`HL-001` | 发布内稳定标识 |
| `kind` | `enum` | 是 | `no_fly`/`height_limit` | 禁飞体或限高体 |
| `volume` | `geometry(PolyhedralSurfaceZ,0)` | 是 | 米 | 三维限制体；禁飞体为封闭体，限高体为柱体 |
| `floor_z` | `double precision` | 是 | 米 | 限制体底面 |
| `ceiling_m` | `double precision` | 否 | 米 | 限高体的绝对上限；`kind='height_limit'` 必填 |
| `effective` | `tstzrange` | 是 | UTC | 生效窗口；半开区间 |
| `state` | `enum` | 是 | `published`/`active`/`expired`/`revoked` | 该发布时刻的状态，随发布不可变；撤销写入新发布中的 `revoked` 行与一条 `airspace_event` |
| `authority` | `text` | 是 | 机构缩写 | 发布机构；模拟数据标 `synthetic` |
| `source_id` | `text` | 是 | 引用 `source` | 来源 |
| `published_at` | `timestamptz` | 是 | UTC | 对外发布时间 |
| `revoked_at` | `timestamptz` | 否 | UTC | 撤销时间；`revoked` 时必填 |
| `quality` | `enum` | 是 | 四级质量 | 数据质量 |
| `sensitivity` | `enum` | 是 | 四级 | 空域细节按 `restricted` |

约束：`kind='height_limit'` 时 `ceiling_m` 非空且 `ceiling_m > floor_z`；`kind='no_fly'` 时 `ceiling_m` 可为空，表示从 `floor_z` 向上封闭；`upper(volume)` 与 `ceiling_m` 的语义必须一致；`feature.valid` 与 `effective` 不同层，不能互相替代。禁止飞行的垂直范围：禁飞体为 `[floor_z, ceiling_m]`（`ceiling_m` 为空则向上封闭），限高体为 `ceiling_m` 以上；空间索引与候选复核必须使用禁止范围，不能用 `floor_z..ceiling_m` 代替限高体。

### 3.10 `airspace_event`（空域事件）

来源：空域发布流程；更新：事件驱动；敏感级别：`restricted`；生命周期：审计保留，不删除。

| 字段 | 类型 | 必填 | 单位/取值 | 说明 |
| --- | --- | --- | --- | --- |
| `event_id` | `text` | 是 | UUID/ULID | 主键 |
| `restriction_id` | `text` | 是 | 引用 `airspace_restriction` | 被操作的限制 |
| `release_id` | `text` | 是 | 引用 `release` | 事件所属发布 |
| `action` | `enum` | 是 | `publish`/`update`/`revoke`/`expire` | 动作 |
| `occurred_at` | `timestamptz` | 是 | UTC | 事件发生时间 |
| `effective_at` | `timestamptz` | 是 | UTC | 对查询生效的时间 |
| `actor_id` | `text` | 是 | 引用 `actor` | 操作者 |
| `source_id` | `text` | 是 | 引用 `source` | 事件来源 |
| `payload_hash` | `text` | 是 | 64 位十六进制 | 事件载荷哈希 |
| `reason` | `text` | 是 | 自由文本 | 发布/撤销原因 |
| `previous_event_id` | `text` | 否 | 引用本表 | 同一限制的上一条事件 |

约束：`effective_at >= occurred_at` 允许（预发布）；同一 `restriction_id` 的事件按 `occurred_at` 单调；撤销后不得在同一有效窗口内复用该 `restriction_id`。

### 3.11 `exposure_zone`（地面暴露分区）

来源：人口/POI/土地利用派生；更新：月或季度；敏感级别：`restricted`；生命周期：随风险发布。

| 字段 | 类型 | 必填 | 单位/取值 | 说明 |
| --- | --- | --- | --- | --- |
| `rid` | `bigint` | 是 | 引用 `feature` | 主键兼外键 |
| `zone_id` | `text` | 是 | 例 `GZ-001` | 发布内稳定标识 |
| `class` | `enum` | 是 | `residential`/`commercial`/`school`/`hospital`/`transport`/`park`/`mixed`/`other` | 暴露类别 |
| `footprint` | `geometry(Polygon,0)` | 是 | 米 | 分区平面范围；必须闭合、简单 |
| `floor_z` | `double precision` | 是 | 米 | 分区垂直起点，通常为 0 |
| `top_z` | `double precision` | 是 | 米 | 分区垂直终点；用于航段高度筛选 |
| `exposure_e` | `double precision` | 是 | [0,1] | 暴露因子 E；LQ 定义含义 |
| `consequence_c` | `double precision` | 是 | [0,1] | 后果因子 C；LQ 定义含义 |
| `q` | `double precision` | 是 | [0,1] | `q = E × C`；生成或校验列 |
| `risk_model_id` | `text` | 是 | 引用 `risk_model` | 计算 q 的模型版本 |
| `source_id` | `text` | 是 | 引用 `source` | 暴露数据来源 |
| `quality` | `enum` | 是 | 四级质量 | 分区质量 |
| `uncertainty` | `jsonb` | 否 | JSON | 置信区间、样本量或定性说明 |
| `valid` | `tstzrange` | 是 | UTC | 该分区有效期 |
| `sensitivity` | `enum` | 是 | 四级 | 聚合后按 `restricted`；原始明细更严 |

约束：`0 <= E,C,q <= 1`；`abs(q - E*C) <= 1e-9`；`top_z > floor_z`；同一发布、同一类别的分区不得重叠；所有分区必须恰好覆盖场景一次；缺 E/C/q 的分区不得被下游当作背景值。

### 3.12 `risk_model`（风险模型）

来源：LQ；更新：模型评审时；敏感级别：`restricted`；生命周期：随发布引用保留。

| 字段 | 类型 | 必填 | 单位/取值 | 说明 |
| --- | --- | --- | --- | --- |
| `risk_model_id` | `text` | 是 | 例 `lq-risk-v1` | 主键 |
| `model_version` | `text` | 是 | 语义版本 | 公式或参数变更时递增 |
| `name` | `text` | 是 | 自由文本 | 模型名称 |
| `formula` | `text` | 是 | 数学表达式 | 例 `q = E * C`；必须与参数含义一致 |
| `params` | `jsonb` | 是 | JSON | 阈值、聚合、包络等参数 |
| `valid` | `tstzrange` | 是 | UTC | 模型适用窗口 |
| `source_id` | `text` | 是 | 引用 `source` | 模型文档来源 |
| `status` | `enum` | 是 | `draft`/`approved`/`retired` | 只有 `approved` 可用于发布 |
| `approved_by` | `text` | 否 | 引用 `actor` | 审批人；模拟数据可为空 |
| `notes` | `text` | 否 | 自由文本 | 假设、非概率声明、替换条件 |

约束：`status='approved'` 时 `approved_by` 非空（模拟发布可豁免并记录）；`q=E×C` 的模型必须与 `exposure_zone` 校验规则一致。

### 3.13 `actor`（操作者）

来源：身份系统；更新：人员变更时；敏感级别：`internal`；生命周期：审计保留。

| 字段 | 类型 | 必填 | 单位/取值 | 说明 |
| --- | --- | --- | --- | --- |
| `actor_id` | `text` | 是 | 不透明 ID | 主键；不存姓名、手机号 |
| `role` | `enum` | 是 | `dispatcher`/`operator`/`airspace_admin`/`system_admin`/`auditor` | 最小角色集 |
| `org` | `text` | 是 | 机构缩写 | 责任机构 |
| `active` | `boolean` | 是 | 真/假 | 是否可操作 |
| `created_at` | `timestamptz` | 是 | UTC | 创建时间 |

### 3.14 `access_policy`（访问策略）

来源：LQ/平台；更新：策略变更时；敏感级别：`restricted`；生命周期：版本化保留。

| 字段 | 类型 | 必填 | 单位/取值 | 说明 |
| --- | --- | --- | --- | --- |
| `policy_id` | `text` | 是 | 主键 | 策略标识 |
| `role` | `enum` | 是 | 同 `actor.role` | 适用角色 |
| `resource` | `text` | 是 | 表/字段/操作 | 受控资源 |
| `action` | `enum` | 是 | `read`/`write`/`publish`/`export` | 动作 |
| `max_sensitivity` | `enum` | 是 | 四级 | 允许的最高敏感级别 |
| `condition` | `jsonb` | 否 | JSON | 时间、机构、用途等条件 |
| `status` | `enum` | 是 | `active`/`retired` | 策略状态 |

本表是字段级钩子，不是最终权限系统；LQ 的治理章节负责角色分离、审批和审计要求。

### 3.15 `lineage_edge`（血缘边）

来源：采集/派生任务；更新：每次生成；敏感级别：`internal`；生命周期：与对象同寿命。

| 字段 | 类型 | 必填 | 单位/取值 | 说明 |
| --- | --- | --- | --- | --- |
| `edge_id` | `text` | 是 | UUID/ULID | 主键 |
| `from_kind` | `enum` | 是 | `source`/`feature`/`release`/`model` | 起点类型 |
| `from_id` | `text` | 是 | 对应实体 ID | 起点 |
| `to_kind` | `enum` | 是 | 同上 | 终点类型 |
| `to_id` | `text` | 是 | 对应实体 ID | 终点 |
| `activity` | `enum` | 是 | `derived_from`/`compiled_from`/`validated_by`/`published_as` | 关系 |
| `tool_version` | `text` | 是 | 工具/脚本版本 | 可复现 |
| `at` | `timestamptz` | 是 | UTC | 生成时间 |
| `release_id` | `text` | 否 | 引用 `release` | 该边所属发布 |
| `evidence` | `jsonb` | 否 | JSON | 参数、哈希、命令或日志摘要 |

约束：`from_kind/from_id` 与 `to_kind/to_id` 不能相同；不允许自环；`derived_from` 边必须能追到至少一个 `source` 或上游 `feature`。

### 3.16 `audit_event`（审计事件）

来源：平台；更新：每次操作；敏感级别：`restricted`；生命周期：只追加，按保留策略归档。

| 字段 | 类型 | 必填 | 单位/取值 | 说明 |
| --- | --- | --- | --- | --- |
| `event_id` | `text` | 是 | UUID/ULID | 主键 |
| `at` | `timestamptz` | 是 | UTC | 事件时间 |
| `actor_id` | `text` | 是 | 引用 `actor` | 操作者 |
| `action` | `enum` | 是 | `publish`/`revoke`/`query`/`export`/`deny` | 动作 |
| `object_kind` | `text` | 是 | 表/实体名 | 被操作对象 |
| `object_id` | `text` | 是 | 对象 ID | 被操作对象标识 |
| `release_id` | `text` | 否 | 引用 `release` | 绑定发布 |
| `result` | `enum` | 是 | `success`/`denied`/`error` | 结果 |
| `reason` | `text` | 否 | 自由文本 | 拒绝/失败原因 |
| `request_id` | `text` | 否 | 请求追踪 ID | 关联 Q1/Q2 调用 |
| `detail` | `jsonb` | 否 | JSON | 参数摘要；不得存完整敏感轨迹 |

约束：只允许插入；不得原地更新或删除；审计查询按 `at` 分区或 BRIN，保留期限由治理策略决定。

## 4. 关系与基数

```text
release 1 ── N release_layer
release 1 ── N coverage_tile
release 1 ── N feature
feature 1 ── 0..1 building
feature 1 ── 0..1 airspace_restriction
feature 1 ── 0..1 exposure_zone
terrain_surface 1 ── N terrain_post
source 1 ── N feature
source 1 ── N coverage_tile
risk_model 1 ── N exposure_zone
actor 1 ── N release
actor 1 ── N airspace_event
actor 1 ── N audit_event
release 1 ── N lineage_edge
airspace_restriction 1 ── N airspace_event
```

- `release.base_release_id` 自引用，允许全量发布为空、增量发布指向前一版。
- `feature` 是公共头；`building`、`airspace_restriction`、`exposure_zone` 是互斥子类型。一个 `rid` 只能属于一个子类型。
- `terrain_surface` 通过 `release_id` 归属发布，不经过 `feature`；地块点通过 `terrain_id` 归属地形面。
- 子类型表的 `rid` 同时是主键和外键，删除父行受 `ON DELETE RESTRICT` 限制。
- `lineage_edge` 是多态边，数据库不强制跨类型外键；由发布质检校验端点存在性。

## 5. 枚举与取值

| 枚举 | 取值 | 说明 |
| --- | --- | --- |
| `layer` | `scene`、`terrain`、`airspace`、`exposure`、`sources` | 五层内容版本 |
| `quality` | `observed`、`derived`、`assumed`、`unknown` | 质量来源 |
| `sensitivity` | `public`、`internal`、`restricted`、`sensitive` | 敏感级别 |
| `release.status` | `draft`、`published`、`superseded`、`retired` | 发布状态 |
| `airspace_restriction.kind` | `no_fly`、`height_limit` | 限制类型 |
| `airspace_restriction.state` | `published`、`active`、`expired`、`revoked` | 当前状态 |
| `airspace_event.action` | `publish`、`update`、`revoke`、`expire` | 事件动作 |
| `exposure_zone.class` | `residential`、`commercial`、`school`、`hospital`、`transport`、`park`、`mixed`、`other` | 暴露类别 |
| `actor.role` | `dispatcher`、`operator`、`airspace_admin`、`system_admin`、`auditor` | 最小角色集 |
| `audit_event.result` | `success`、`denied`、`error` | 操作结果 |

## 6. 完整性约束

### 6.1 发布与版本

- 五层必须齐全；每层 `content_hash` 与内容重算一致；`release.content_hash` 由五层版本和清单生成。
- `status='published'` 后，`release` 及其对象只读；任何更新写新发布。
- `coverage_tile.complete=false` 或 `release_layer.complete=false` 时，相关查询返回 `unknown`，不得当作无限制。
- 查询绑定 `release_id`；Q1/Q2 返回的五层版本和 `risk_model_id` 必须与读取时一致。

### 6.2 几何与空间

- 所有几何 `SRID=0`；`ST_IsValid` 必须为真；三维体必须是封闭、简单、非自交的 `PolyhedralSurfaceZ`。
- 建筑和暴露分区必须落在场景边界内；地形点必须落在地形边界内。
- 建筑 `top_z > base_z`；`height_m` 与 `top_z-base_z` 一致；`solid` 的二维投影与 `footprint` 一致。
- 空域体的 `floor_z`、`ceiling_m`、`effective` 三者共同定义可飞行判断；仅检查二维范围不充分。
- 暴露分区是场景的一个划分：互不重叠、恰好覆盖一次；缺 E/C/q 的分区不能被背景值替代。

### 6.3 时间与有效性

- `valid`、`effective` 必须非空且 `lower < upper`；时间统一 UTC。
- `recorded_at` 不得晚于平台发布时刻；`published_at` 不得早于 `created_at`。
- 查询窗口必须完全落在发布 `valid` 和有覆盖的瓦片 `valid` 内；否则 `unknown`。
- 空域事件按 `occurred_at` 单调；撤销后同一有效窗口不得复用标识。

### 6.4 质量与敏感级别

- `quality='unknown'` 的对象不得参与“安全/允许”结论；只能返回 `unknown` 或显式拒绝。
- `q=E×C` 必须在容差内；E/C/q 缺失时导出层必须拒绝，不能回退到背景。
- 敏感级别按最高输入聚合；导出、查询和审计都必须检查 `access_policy`。
- 发布清单记录对象数、瓦片数、哈希和工具版本，供复核。

## 7. 物理映射与索引

### 7.1 PostgreSQL/PostGIS 映射

| 逻辑类型 | 物理类型 | 说明 |
| --- | --- | --- |
| `text` | `text` | 标识、名称、哈希 |
| `enum` | `text` + `CHECK` 或原生 `ENUM` | 为迁移方便，首版用 `text + CHECK` |
| `timestamptz` | `timestamptz` | UTC |
| `tstzrange` | `tstzrange` | 半开区间 |
| `double precision` | `double precision` | 米或无量纲 |
| `jsonb` | `jsonb` | 清单、参数、扩展属性 |
| `geometry(Polygon,0)` | `geometry(Polygon,0)` | 局部米制 |
| `geometry(PolyhedralSurfaceZ,0)` | `geometry(PolyhedralSurfaceZ,0)` | 三维体 |
| `geometry(TIN,0)` | `geometry(TIN,0)` | 地形三角网 |

### 7.2 索引选择

| 表 | 索引 | 目的 |
| --- | --- | --- |
| `building` | GiST `(solid gist_geometry_ops_nd)` | 三维候选过滤；精确判定仍用 `ST_3DIntersects`/`ST_3DDWithin` |
| `building` | GiST `(footprint)` | 二维落区、覆盖和地面距离 |
| `airspace_restriction` | GiST `(volume gist_geometry_ops_nd)` | 三维空域候选 |
| `airspace_restriction` | GiST `(effective)` | 时间窗相交 |
| `exposure_zone` | GiST `(footprint)` | 地面分区候选 |
| `exposure_zone` | B-tree `(release_id, class)` | 按发布和类别聚合 |
| `feature` | B-tree `(release_id, feature_id)` | 对象定位 |
| `feature` | B-tree `(release_id, layer, feature_type)` | 分层统计 |
| `coverage_tile` | B-tree `(release_id, layer, tile_x, tile_y)` | 覆盖检查 |
| `terrain_post` | B-tree `(release_id, terrain_id, ix, iy)` | 格网点读取 |
| `airspace_event` | B-tree `(restriction_id, occurred_at)` | 事件序列 |
| `audit_event` | BRIN `(at)` | 追加型审计的范围扫描 |

`gist_geometry_ops_nd` 是 PostGIS 官方 n 维 GiST 操作符类，适用于带 Z 值的数据；默认 GiST 只按二维包围盒处理，不能替代三维精确判定。索引只负责候选过滤，最终相交/距离由精确谓词决定。

### 7.3 分区与冷热分层

- `feature`、`building`、`airspace_restriction`、`exposure_zone` 按 `release_id` 的哈希分区（首版 16 个分区），避免单表随历史版本无限增长；查询始终带 `release_id`，可分区裁剪。
- `audit_event`、`airspace_event` 按月份范围分区；热分区保留 90 天，冷分区转 Parquet/对象存储，元数据留在 `release` 和 `lineage_edge`。
- 当前发布在热库；`superseded`/`retired` 发布可转冷存储，保留 `release_layer` 和哈希用于追溯。
- 空间瓦片用于覆盖检查与并行加载，不替代数据库分区；瓦片是数据完整性单位，分区是物理存储单位。

## 8. 数据规模与三年增长假设

以下为设计估算，不是实测；基线来自 v1 合成场景，三年增长是假设，需在报告中标注。

| 数据 | 基线 | 三年假设 | 估算 |
| --- | --- | --- | --- |
| 建筑 | 25 栋，34 个要素，紧凑 JSON 约 52 KB | 覆盖 10 个同等片区，约 2,400 栋 | 单版约 884 KB；每日 1 版、3 年约 1,095 版，原始 JSON 约 0.97 GB；加索引和历史约 2 GB |
| 地形 | 31×31 点（961 点） | 10 个片区，约 9,610 点；每年 1 版 | 单版约 0.3 MB；3 年约 1 MB；索引与历史可忽略 |
| 空域 | 3 个限制体 | 每日 20 条事件，约 7,300 条/年 | 3 年约 21,900 条事件，按 1 KB/条约 22 MB；活动限制约 100 条 |
| 地面暴露 | 6 个分区 | 每片区 6 区，10 个片区 60 区；每月 1 版 | 36 版约 2,160 行，按 1 KB/行约 2 MB |
| 查询审计 | 未计 | 每日 1 万次查询 | 3 年约 1,095 万条，按 1 KB/条约 11 GB；热库只留 90 天 |

假设：对象数增长来自片区扩张，不来自真实城市全量；每日发布次数、查询量和保留期是待确认参数。真实几何复杂度、并发和网络往返未计入，不能把表中容量当作生产容量承诺。

## 9. 待对接与变更记录

- LQ 可在 `governance.md` 中细化敏感级别、保留期、角色和审批规则；本字典的四级分类是字段钩子，不是最终合规结论。
- ZQO 的发布目录需要 `release_id`、五层版本、`content_hash`、`published_at` 和 `airspace_event`；字段映射见后续 `integration` 或 `section.md`。
- ZC 的 Q1/Q2 适配需要 `feature_id`、`solid`/`volume`/`footprint`、`valid`、`effective`、`source_id`、`quality` 和版本元组。
- LJ 的验收需要 `audit_event`、`release` 状态和失败原因；本字典只定义审计字段，不定义验收判据。
- 变更记录：2026-11-06 初稿，建立三类数据、发布五层、E/C/q、三维/时间索引和敏感级别字段。
- 变更记录：2026-11-06（ZC 按用户指示修订）生成可执行模式 [`docs/v2/schema/`](../../../v2/schema/schema.sql)。修正 `coverage_tile`、`terrain_surface`、`terrain_post` 主键（编号每次发布重复，原单列主键会在第二次发布冲突）；`rid` 改述为全局代理键；`airspace_restriction.state` 改为随发布固定；补充限高体禁止范围在 `ceiling_m` 以上。逐项理由见 [decisions.md](../../../v2/schema/decisions.md) S-01—S-03。

- 变更记录：2026-11-06（ZQO，第2棒，基线 `5ee1a19`）：发布与版本分节新增 `layer_component`（物理图层及内容摘要）、`release_component`（逻辑发布五层映射）、`component_source`（来源成员清单）、`current_release`（每场景当前指针）、`publish_request`（幂等成功凭据）、`failed_attempt`（回滚后失败尝试）、`outbox`（事务内待发送事件），共7表；完整字段/外键见 [schema.sql](../../../v2/schema/schema.sql) 第2节。
- 同轮映射约定：`release_layer.layer_version` 是规范化关系行的 SHA-256；上游五层版本另存 `release.manifest.provenance.source_versions`，同时保存风险模型、编译器和窗口。`feature.release_id`、地形与覆盖行的 `release_id` 表示物理所有者；查询的逻辑发布通过 `release_component → layer_component.owner_release_id` 解析，新增 `resolved_feature` / `resolved_source` 视图。现有实体列不变；YHT 原独立索引夹具仍可运行。
- 同轮生命周期：当前指针只接受已发布且五层映射完整的版本；撤销写新空域组件和 `airspace_event`，历史内容保留；`superseded` / `retired` 也可显式历史读取。来源被非 draft 发布引用后禁止原地修改，修订登记新 `source_id`；模型冻结仍由 LQ-V2-01 跟进。技术决定与受影响查询见 [ZQO 对接说明](../../zqo/v2/integration.md)。

## 10. 参考

- [共同场景与查询约定](../../../scenario-contract.md)
- [YHT v1 数据模型与质量规则](../design.md)
- [YHT v1 存储与索引](../storage.md)
- [YHT v1 集成说明](../integration.md)
- [PostGIS 3.5 Spatial Indexes](https://postgis.net/docs/manual-3.5/using_postgis_dbmanagement.html#build-indexes)
- [PostGIS ST_3DIntersects](https://postgis.net/docs/ST_3DIntersects.html)
- [PostGIS geometry_overlaps_nd（`&&&`）](https://postgis.net/docs/geometry_overlaps_nd.html)
- [PostGIS ST_3DDWithin](https://postgis.net/docs/ST_3DDWithin.html)
