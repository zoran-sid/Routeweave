-- SkyRoute v2 统一数据库模式（SQLite 方言）
-- 逻辑模型：docs/modules/yht/v2/data-dictionary.md（16 个基础实体 + ZQO 第9节变更记录的7个发布实体）
-- 设计说明：decisions.md；ER 图：er.md；测试：test_schema.py
--
-- 方言约定
--   时刻    TEXT，UTC，格式 YYYY-MM-DDTHH:MM:SSZ（定长，字典序即时间序）
--   区间    <名>_lo / <名>_hi 两列，半开 [lo, hi)
--   枚举    TEXT + CHECK IN (...)
--   JSON    TEXT + CHECK (json_valid(...))
--   几何    WKT 文本（SRID 0，局部米制）+ 由发布质检写入的包围盒列
--   哈希    64 位小写十六进制
--   R*Tree  时间维以“距 2026-01-01T00:00:00Z 的秒数”存储（unixepoch - 1767225600）
-- PostgreSQL/PostGIS 对应写法见 decisions.md 第 3 节。
--
-- 表组负责人：源数据与空间 YHT；发布与版本 ZQO；风险派生、质量与访问 LQ；
-- 查询与结果追溯 ZC（预留）；运行与恢复 LJ（预留）。各组在自己的分节内细化。

PRAGMA foreign_keys = ON;

-- =====================================================================
-- 1 身份与来源（YHT 建立；actor 的角色与权限由 LQ 细化）
-- =====================================================================

CREATE TABLE actor (
    actor_id   TEXT PRIMARY KEY,
    role       TEXT NOT NULL CHECK (role IN ('dispatcher','operator','airspace_admin','system_admin','auditor')),
    org        TEXT NOT NULL,
    active     INTEGER NOT NULL CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z')
);

CREATE TABLE source (
    source_id          TEXT PRIMARY KEY,
    name               TEXT NOT NULL,
    source_type        TEXT NOT NULL CHECK (source_type IN ('gis','bim','lidar','authority_feed','census','derived','synthetic')),
    owner_org          TEXT NOT NULL,
    license            TEXT NOT NULL,
    acquisition_method TEXT NOT NULL,
    acquired_at        TEXT NOT NULL CHECK (acquired_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z'),
    update_frequency   TEXT NOT NULL CHECK (update_frequency IN ('event','hourly','daily','monthly','quarterly','annual','static')),
    accuracy_xy_m      REAL CHECK (accuracy_xy_m IS NULL OR accuracy_xy_m >= 0),
    accuracy_z_m       REAL CHECK (accuracy_z_m IS NULL OR accuracy_z_m >= 0),
    valid_lo           TEXT,
    valid_hi           TEXT,
    sensitivity        TEXT NOT NULL CHECK (sensitivity IN ('public','internal','restricted','sensitive')),
    contact_ref        TEXT,
    notes              TEXT,
    CHECK ((valid_lo IS NULL AND valid_hi IS NULL) OR (valid_lo IS NOT NULL AND valid_hi IS NOT NULL AND valid_lo < valid_hi))
);

-- =====================================================================
-- 2 发布与版本（YHT 按数据字典建立；ZQO 细化事务、当前指针、失败尝试、待发送事件）
-- =====================================================================

CREATE TABLE release (
    release_id      TEXT PRIMARY KEY,
    scene_id        TEXT NOT NULL,
    schema_version  TEXT NOT NULL,
    baseline        TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('draft','published','superseded','retired')),
    base_release_id TEXT REFERENCES release(release_id) ON DELETE RESTRICT,
    valid_lo        TEXT NOT NULL,
    valid_hi        TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    published_at    TEXT,
    retired_at      TEXT,
    actor_id        TEXT NOT NULL REFERENCES actor(actor_id),
    content_hash    TEXT NOT NULL CHECK (length(content_hash) = 64 AND content_hash NOT GLOB '*[^0-9a-f]*'),
    manifest        TEXT NOT NULL CHECK (json_valid(manifest)),
    notes           TEXT,
    CHECK (valid_lo < valid_hi),
    CHECK ((status = 'draft') = (published_at IS NULL)),
    CHECK (published_at IS NULL OR published_at >= created_at),
    CHECK (base_release_id IS NULL OR base_release_id <> release_id)
);

CREATE TABLE release_layer (
    release_id    TEXT NOT NULL REFERENCES release(release_id) ON DELETE RESTRICT,
    layer         TEXT NOT NULL CHECK (layer IN ('scene','terrain','airspace','exposure','sources')),
    layer_version TEXT NOT NULL,
    content_hash  TEXT NOT NULL CHECK (length(content_hash) = 64 AND content_hash NOT GLOB '*[^0-9a-f]*'),
    feature_count INTEGER NOT NULL CHECK (feature_count >= 0),
    generated_at  TEXT NOT NULL,
    complete      INTEGER NOT NULL CHECK (complete IN (0, 1)),
    PRIMARY KEY (release_id, layer)
);

-- 状态迁移：draft→published→superseded/retired，superseded→retired；发布时五层必须齐全。
CREATE TRIGGER release_status_transition
BEFORE UPDATE OF status ON release
WHEN NEW.status <> OLD.status AND NOT (
       (OLD.status = 'draft'      AND NEW.status = 'published')
    OR (OLD.status = 'published'  AND NEW.status IN ('superseded','retired'))
    OR (OLD.status = 'superseded' AND NEW.status = 'retired'))
BEGIN
    SELECT RAISE(ABORT, 'release: illegal status transition');
END;

CREATE TRIGGER release_publish_requires_layers
BEFORE UPDATE OF status ON release
WHEN OLD.status = 'draft' AND NEW.status = 'published'
 AND (SELECT count(*) FROM release_layer WHERE release_id = NEW.release_id) <> 5
BEGIN
    SELECT RAISE(ABORT, 'release: all five layers required before publish');
END;

-- 发布后只允许改 status 与 retired_at。
CREATE TRIGGER release_immutable_fields
BEFORE UPDATE ON release
WHEN OLD.status <> 'draft' AND (
       NEW.release_id IS NOT OLD.release_id OR NEW.scene_id IS NOT OLD.scene_id
    OR NEW.schema_version IS NOT OLD.schema_version OR NEW.baseline IS NOT OLD.baseline
    OR NEW.base_release_id IS NOT OLD.base_release_id
    OR NEW.valid_lo IS NOT OLD.valid_lo OR NEW.valid_hi IS NOT OLD.valid_hi
    OR NEW.created_at IS NOT OLD.created_at OR NEW.published_at IS NOT OLD.published_at
    OR NEW.actor_id IS NOT OLD.actor_id OR NEW.content_hash IS NOT OLD.content_hash
    OR NEW.manifest IS NOT OLD.manifest OR NEW.notes IS NOT OLD.notes)
BEGIN
    SELECT RAISE(ABORT, 'release: published release is immutable');
END;

CREATE TRIGGER release_no_delete
BEFORE DELETE ON release
WHEN OLD.status <> 'draft'
BEGIN
    SELECT RAISE(ABORT, 'release: published release cannot be deleted');
END;

CREATE TRIGGER release_layer_immutable_update
BEFORE UPDATE ON release_layer
WHEN (SELECT status FROM release WHERE release_id = OLD.release_id) <> 'draft'
BEGIN
    SELECT RAISE(ABORT, 'release_layer: published release is immutable');
END;

CREATE TRIGGER release_layer_immutable_delete
BEFORE DELETE ON release_layer
WHEN (SELECT status FROM release WHERE release_id = OLD.release_id) <> 'draft'
BEGIN
    SELECT RAISE(ABORT, 'release_layer: published release is immutable');
END;

CREATE TRIGGER release_layer_insert_draft_only
BEFORE INSERT ON release_layer
WHEN (SELECT status FROM release WHERE release_id = NEW.release_id) <> 'draft'
BEGIN
    SELECT RAISE(ABORT, 'release_layer: release is not draft');
END;

-- ZQO v2: physical owner rows stay in YHT tables; logical releases share components.
CREATE TABLE layer_component (
    component_id TEXT PRIMARY KEY,
    layer TEXT NOT NULL CHECK (layer IN ('scene','terrain','airspace','exposure','sources')),
    owner_release_id TEXT NOT NULL REFERENCES release(release_id),
    content_hash TEXT NOT NULL CHECK (length(content_hash)=64 AND content_hash NOT GLOB '*[^0-9a-f]*'),
    feature_count INTEGER NOT NULL CHECK (feature_count>=0),
    UNIQUE(component_id, layer),
    UNIQUE(owner_release_id, layer)
);
CREATE INDEX component_hash ON layer_component(layer, content_hash);
CREATE TABLE release_component (
    release_id TEXT NOT NULL,
    layer TEXT NOT NULL,
    component_id TEXT NOT NULL,
    PRIMARY KEY(release_id, layer),
    FOREIGN KEY(release_id, layer) REFERENCES release_layer(release_id, layer),
    FOREIGN KEY(component_id, layer) REFERENCES layer_component(component_id, layer)
);
CREATE INDEX component_dependents ON release_component(component_id, release_id);
CREATE TABLE component_source (
    component_id TEXT NOT NULL REFERENCES layer_component(component_id),
    source_id TEXT NOT NULL REFERENCES source(source_id),
    PRIMARY KEY(component_id, source_id)
);
CREATE TABLE current_release (
    scene_id TEXT PRIMARY KEY,
    release_id TEXT NOT NULL UNIQUE REFERENCES release(release_id)
);
CREATE TABLE publish_request (
    request_id TEXT PRIMARY KEY,
    request_hash TEXT NOT NULL CHECK (length(request_hash)=64),
    release_id TEXT NOT NULL UNIQUE REFERENCES release(release_id)
);
CREATE TABLE failed_attempt (
    attempt_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    candidate_hash TEXT NOT NULL,
    candidate_release_id TEXT NOT NULL, -- may never exist; deliberately not a foreign key
    expected_release_id TEXT,
    observed_release_id TEXT REFERENCES release(release_id),
    actor_ref TEXT NOT NULL, -- unknown/disabled caller must still be auditable
    at TEXT NOT NULL,
    reason TEXT NOT NULL
);
CREATE INDEX failed_request ON failed_attempt(request_id);
CREATE TABLE outbox (
    event_id TEXT PRIMARY KEY REFERENCES audit_event(event_id),
    release_id TEXT NOT NULL REFERENCES release(release_id),
    kind TEXT NOT NULL CHECK(kind IN ('publish','revoke')),
    created_at TEXT NOT NULL,
    delivered_at TEXT,
    attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts>=0)
);
CREATE INDEX outbox_pending ON outbox(delivered_at, created_at);

CREATE TRIGGER release_insert_draft_only BEFORE INSERT ON release
WHEN NEW.status <> 'draft'
BEGIN SELECT RAISE(ABORT, 'release: insert as draft'); END;
CREATE TRIGGER release_layer_target_draft BEFORE UPDATE ON release_layer
WHEN (SELECT status FROM release WHERE release_id=NEW.release_id)<>'draft'
BEGIN SELECT RAISE(ABORT, 'release_layer: target is not draft'); END;
CREATE TRIGGER release_publish_complete BEFORE UPDATE OF status ON release
WHEN NEW.status='published' AND OLD.status='draft'
 AND EXISTS(SELECT 1 FROM release_layer WHERE release_id=NEW.release_id AND complete<>1)
BEGIN SELECT RAISE(ABORT, 'release: incomplete layer'); END;
CREATE TRIGGER component_insert_draft BEFORE INSERT ON layer_component
WHEN (SELECT status FROM release WHERE release_id=NEW.owner_release_id)<>'draft'
BEGIN SELECT RAISE(ABORT, 'component: owner is not draft'); END;
CREATE TRIGGER component_no_update BEFORE UPDATE ON layer_component
BEGIN SELECT RAISE(ABORT, 'component: immutable'); END;
CREATE TRIGGER component_no_delete BEFORE DELETE ON layer_component
BEGIN SELECT RAISE(ABORT, 'component: immutable'); END;
CREATE TRIGGER release_component_insert BEFORE INSERT ON release_component BEGIN
    SELECT CASE WHEN (SELECT status FROM release WHERE release_id=NEW.release_id)<>'draft'
      THEN RAISE(ABORT, 'release_component: release is not draft') END;
    SELECT CASE WHEN NOT EXISTS (
      SELECT 1 FROM layer_component c JOIN release_layer l
        ON l.release_id=NEW.release_id AND l.layer=NEW.layer
      JOIN release owner ON owner.release_id=c.owner_release_id
      JOIN release target ON target.release_id=NEW.release_id
      WHERE c.component_id=NEW.component_id AND c.content_hash=l.content_hash
        AND c.feature_count=l.feature_count AND owner.scene_id=target.scene_id
        AND (owner.release_id=target.release_id OR owner.status<>'draft'))
      THEN RAISE(ABORT, 'release_component: incompatible component') END;
END;
CREATE TRIGGER release_component_no_update BEFORE UPDATE ON release_component
BEGIN SELECT RAISE(ABORT, 'release_component: immutable'); END;
CREATE TRIGGER release_component_no_delete BEFORE DELETE ON release_component
BEGIN SELECT RAISE(ABORT, 'release_component: immutable'); END;
CREATE TRIGGER component_source_insert BEFORE INSERT ON component_source
WHEN NOT EXISTS(SELECT 1 FROM layer_component c JOIN release r ON r.release_id=c.owner_release_id
 WHERE c.component_id=NEW.component_id AND c.layer='sources' AND r.status='draft')
BEGIN SELECT RAISE(ABORT, 'component_source: draft sources owner required'); END;
CREATE TRIGGER component_source_no_update BEFORE UPDATE ON component_source
BEGIN SELECT RAISE(ABORT, 'component_source: immutable'); END;
CREATE TRIGGER component_source_no_delete BEFORE DELETE ON component_source
BEGIN SELECT RAISE(ABORT, 'component_source: immutable'); END;
CREATE TRIGGER head_insert_valid BEFORE INSERT ON current_release
WHEN NOT EXISTS(SELECT 1 FROM release r WHERE r.release_id=NEW.release_id
 AND r.scene_id=NEW.scene_id AND r.status='published'
 AND (SELECT count(*) FROM release_component WHERE release_id=r.release_id)=5)
BEGIN SELECT RAISE(ABORT, 'head: published mapped release required'); END;
CREATE TRIGGER head_update_valid BEFORE UPDATE ON current_release
WHEN NEW.scene_id<>OLD.scene_id OR NOT EXISTS(SELECT 1 FROM release r
 WHERE r.release_id=NEW.release_id AND r.scene_id=NEW.scene_id AND r.status='published'
 AND r.base_release_id=OLD.release_id
 AND (SELECT count(*) FROM release_component WHERE release_id=r.release_id)=5)
BEGIN SELECT RAISE(ABORT, 'head: successor required'); END;
CREATE TRIGGER head_no_delete BEFORE DELETE ON current_release
BEGIN SELECT RAISE(ABORT, 'head: cannot delete'); END;
CREATE TRIGGER request_no_update BEFORE UPDATE ON publish_request
BEGIN SELECT RAISE(ABORT, 'publish_request: immutable'); END;
CREATE TRIGGER request_no_delete BEFORE DELETE ON publish_request
BEGIN SELECT RAISE(ABORT, 'publish_request: immutable'); END;
CREATE TRIGGER failure_no_update BEFORE UPDATE ON failed_attempt
BEGIN SELECT RAISE(ABORT, 'failed_attempt: append-only'); END;
CREATE TRIGGER failure_no_delete BEFORE DELETE ON failed_attempt
BEGIN SELECT RAISE(ABORT, 'failed_attempt: append-only'); END;
CREATE TRIGGER outbox_identity_immutable BEFORE UPDATE ON outbox
WHEN NEW.event_id IS NOT OLD.event_id OR NEW.release_id IS NOT OLD.release_id
 OR NEW.kind IS NOT OLD.kind OR NEW.created_at IS NOT OLD.created_at
BEGIN SELECT RAISE(ABORT, 'outbox: identity immutable'); END;
CREATE TRIGGER outbox_no_delete BEFORE DELETE ON outbox
BEGIN SELECT RAISE(ABORT, 'outbox: retain delivery history'); END;

-- Query adapters must resolve the physical owner, rather than filter feature.release_id directly.
CREATE VIEW resolved_feature AS
SELECT rc.release_id AS query_release_id, c.owner_release_id, f.*
FROM release_component rc JOIN layer_component c USING(component_id)
JOIN feature f ON f.release_id=c.owner_release_id AND f.layer=c.layer;
CREATE VIEW resolved_source AS
SELECT rc.release_id AS query_release_id, c.component_id, s.*
FROM release_component rc JOIN layer_component c USING(component_id)
JOIN component_source cs USING(component_id) JOIN source s USING(source_id)
WHERE rc.layer='sources';

-- =====================================================================
-- 3 源数据与空间（YHT）
-- =====================================================================

-- 覆盖瓦片：瓦片编号在每次发布、每层重复出现，主键含 release_id 与 layer。
CREATE TABLE coverage_tile (
    release_id TEXT NOT NULL REFERENCES release(release_id) ON DELETE RESTRICT,
    layer      TEXT NOT NULL CHECK (layer IN ('scene','terrain','airspace','exposure')),
    tile_id    TEXT NOT NULL,
    tile_x     INTEGER NOT NULL CHECK (tile_x >= 0),
    tile_y     INTEGER NOT NULL CHECK (tile_y >= 0),
    bounds_wkt TEXT NOT NULL,
    complete   INTEGER NOT NULL CHECK (complete IN (0, 1)),
    quality    TEXT NOT NULL CHECK (quality IN ('observed','derived','assumed','unknown')),
    source_id  TEXT NOT NULL REFERENCES source(source_id),
    valid_lo   TEXT NOT NULL,
    valid_hi   TEXT NOT NULL,
    checksum   TEXT NOT NULL CHECK (length(checksum) = 64 AND checksum NOT GLOB '*[^0-9a-f]*'),
    PRIMARY KEY (release_id, layer, tile_id),
    UNIQUE (release_id, layer, tile_x, tile_y),
    CHECK (valid_lo < valid_hi)
);

-- 空间对象公共头。rid 是全局唯一代理键；feature_id 跨发布稳定。
CREATE TABLE feature (
    rid          INTEGER PRIMARY KEY,
    release_id   TEXT NOT NULL REFERENCES release(release_id) ON DELETE RESTRICT,
    feature_id   TEXT NOT NULL,
    layer        TEXT NOT NULL CHECK (layer IN ('scene','airspace','exposure')),
    feature_type TEXT NOT NULL CHECK (feature_type IN ('building','airspace','exposure')),
    name         TEXT,
    source_id    TEXT NOT NULL REFERENCES source(source_id),
    quality      TEXT NOT NULL CHECK (quality IN ('observed','derived','assumed','unknown')),
    valid_lo     TEXT NOT NULL,
    valid_hi     TEXT NOT NULL,
    recorded_at  TEXT NOT NULL,
    sensitivity  TEXT NOT NULL CHECK (sensitivity IN ('public','internal','restricted','sensitive')),
    attrs        TEXT CHECK (attrs IS NULL OR json_valid(attrs)),
    geom_kind    TEXT NOT NULL CHECK (geom_kind IN ('polygon','polyhedral','point','tin')),
    UNIQUE (release_id, feature_id),
    CHECK (valid_lo < valid_hi),
    CHECK ((feature_type = 'building' AND layer = 'scene')
        OR (feature_type = 'airspace' AND layer = 'airspace')
        OR (feature_type = 'exposure' AND layer = 'exposure'))
);

CREATE INDEX feature_release_type ON feature(release_id, layer, feature_type);

CREATE TABLE building (
    rid              INTEGER PRIMARY KEY REFERENCES feature(rid) ON DELETE RESTRICT,
    footprint_wkt    TEXT NOT NULL,
    solid_wkt        TEXT NOT NULL,
    bbox_min_x       REAL NOT NULL,
    bbox_min_y       REAL NOT NULL,
    bbox_max_x       REAL NOT NULL,
    bbox_max_y       REAL NOT NULL,
    base_z           REAL NOT NULL,
    top_z            REAL NOT NULL,
    height_m         REAL NOT NULL,
    footprint_source TEXT NOT NULL REFERENCES source(source_id),
    height_source    TEXT NOT NULL REFERENCES source(source_id),
    height_method    TEXT NOT NULL CHECK (height_method IN ('measured','derived','assumed','unknown')),
    roof_type        TEXT,
    is_landmark      INTEGER NOT NULL CHECK (is_landmark IN (0, 1)),
    CHECK (top_z > base_z),
    CHECK (abs(height_m - (top_z - base_z)) <= 1e-6),
    CHECK (bbox_min_x < bbox_max_x AND bbox_min_y < bbox_max_y)
);

CREATE TABLE terrain_surface (
    release_id     TEXT NOT NULL REFERENCES release(release_id) ON DELETE RESTRICT,
    terrain_id     TEXT NOT NULL,
    surface_type   TEXT NOT NULL CHECK (surface_type IN ('grid','tin')),
    bounds_wkt     TEXT NOT NULL,
    post_spacing_m REAL CHECK (post_spacing_m IS NULL OR post_spacing_m > 0),
    vertical_datum TEXT NOT NULL,
    flat           INTEGER NOT NULL CHECK (flat IN (0, 1)),
    min_z          REAL NOT NULL,
    max_z          REAL NOT NULL,
    geom_wkt       TEXT,
    source_id      TEXT NOT NULL REFERENCES source(source_id),
    quality        TEXT NOT NULL CHECK (quality IN ('observed','derived','assumed','unknown')),
    valid_lo       TEXT NOT NULL,
    valid_hi       TEXT NOT NULL,
    checksum       TEXT NOT NULL CHECK (length(checksum) = 64 AND checksum NOT GLOB '*[^0-9a-f]*'),
    PRIMARY KEY (release_id, terrain_id),
    CHECK (max_z >= min_z),
    CHECK (flat = 0 OR (min_z = 0 AND max_z = 0)),
    CHECK ((surface_type = 'grid') = (post_spacing_m IS NOT NULL)),
    CHECK (valid_lo < valid_hi)
);

CREATE TABLE terrain_post (
    release_id TEXT NOT NULL,
    terrain_id TEXT NOT NULL,
    ix         INTEGER NOT NULL CHECK (ix >= 0),
    iy         INTEGER NOT NULL CHECK (iy >= 0),
    x          REAL NOT NULL,
    y          REAL NOT NULL,
    z          REAL NOT NULL,
    quality    TEXT NOT NULL CHECK (quality IN ('observed','derived','assumed','unknown')),
    source_id  TEXT NOT NULL REFERENCES source(source_id),
    PRIMARY KEY (release_id, terrain_id, ix, iy),
    UNIQUE (release_id, terrain_id, x, y),
    FOREIGN KEY (release_id, terrain_id) REFERENCES terrain_surface(release_id, terrain_id) ON DELETE RESTRICT
);

-- 空域限制。state 记录该发布时刻的状态，随发布不可变；撤销通过新发布 + airspace_event 表达。
CREATE TABLE airspace_restriction (
    rid            INTEGER PRIMARY KEY REFERENCES feature(rid) ON DELETE RESTRICT,
    restriction_id TEXT NOT NULL,
    kind           TEXT NOT NULL CHECK (kind IN ('no_fly','height_limit')),
    volume_wkt     TEXT NOT NULL,
    bbox_min_x     REAL NOT NULL,
    bbox_min_y     REAL NOT NULL,
    bbox_max_x     REAL NOT NULL,
    bbox_max_y     REAL NOT NULL,
    floor_z        REAL NOT NULL,
    ceiling_m      REAL,
    effective_lo   TEXT NOT NULL,
    effective_hi   TEXT NOT NULL,
    state          TEXT NOT NULL CHECK (state IN ('published','active','expired','revoked')),
    authority      TEXT NOT NULL,
    source_id      TEXT NOT NULL REFERENCES source(source_id),
    published_at   TEXT NOT NULL,
    revoked_at     TEXT,
    quality        TEXT NOT NULL CHECK (quality IN ('observed','derived','assumed','unknown')),
    sensitivity    TEXT NOT NULL CHECK (sensitivity IN ('public','internal','restricted','sensitive')),
    -- 禁止飞行的垂直范围：禁飞体为 [floor_z, ceiling_m 或向上封闭]；限高体为 ceiling_m 以上。
    forbid_lo_z    REAL GENERATED ALWAYS AS (CASE kind WHEN 'height_limit' THEN ceiling_m ELSE floor_z END) VIRTUAL,
    forbid_hi_z    REAL GENERATED ALWAYS AS (CASE kind WHEN 'height_limit' THEN 1.0e6 ELSE coalesce(ceiling_m, 1.0e6) END) VIRTUAL,
    CHECK (kind <> 'height_limit' OR (ceiling_m IS NOT NULL AND ceiling_m > floor_z)),
    CHECK (ceiling_m IS NULL OR ceiling_m > floor_z),
    CHECK ((state = 'revoked') = (revoked_at IS NOT NULL)),
    CHECK (effective_lo < effective_hi),
    CHECK (bbox_min_x < bbox_max_x AND bbox_min_y < bbox_max_y)
);

CREATE TABLE exposure_zone (
    rid           INTEGER PRIMARY KEY REFERENCES feature(rid) ON DELETE RESTRICT,
    zone_id       TEXT NOT NULL,
    class         TEXT NOT NULL CHECK (class IN ('residential','commercial','school','hospital','transport','park','mixed','other')),
    footprint_wkt TEXT NOT NULL,
    bbox_min_x    REAL NOT NULL,
    bbox_min_y    REAL NOT NULL,
    bbox_max_x    REAL NOT NULL,
    bbox_max_y    REAL NOT NULL,
    floor_z       REAL NOT NULL,
    top_z         REAL NOT NULL,
    exposure_e    REAL NOT NULL CHECK (exposure_e BETWEEN 0 AND 1),
    consequence_c REAL NOT NULL CHECK (consequence_c BETWEEN 0 AND 1),
    q             REAL NOT NULL CHECK (q BETWEEN 0 AND 1),
    risk_model_id TEXT NOT NULL REFERENCES risk_model(risk_model_id),
    source_id     TEXT NOT NULL REFERENCES source(source_id),
    quality       TEXT NOT NULL CHECK (quality IN ('observed','derived','assumed','unknown')),
    uncertainty   TEXT CHECK (uncertainty IS NULL OR json_valid(uncertainty)),
    valid_lo      TEXT NOT NULL,
    valid_hi      TEXT NOT NULL,
    sensitivity   TEXT NOT NULL CHECK (sensitivity IN ('public','internal','restricted','sensitive')),
    CHECK (abs(q - exposure_e * consequence_c) <= 1e-9),
    CHECK (top_z > floor_z),
    CHECK (valid_lo < valid_hi),
    CHECK (bbox_min_x < bbox_max_x AND bbox_min_y < bbox_max_y)
);

-- 子类型必须与 feature.feature_type 一致；限制与分区的稳定标识等于 feature_id。
CREATE TRIGGER building_subtype_check BEFORE INSERT ON building
WHEN (SELECT feature_type FROM feature WHERE rid = NEW.rid) IS NOT 'building'
BEGIN SELECT RAISE(ABORT, 'building: feature_type must be building'); END;

CREATE TRIGGER airspace_subtype_check BEFORE INSERT ON airspace_restriction
WHEN (SELECT feature_type FROM feature WHERE rid = NEW.rid) IS NOT 'airspace'
  OR (SELECT feature_id FROM feature WHERE rid = NEW.rid) IS NOT NEW.restriction_id
BEGIN SELECT RAISE(ABORT, 'airspace_restriction: feature_type must be airspace and restriction_id = feature_id'); END;

CREATE TRIGGER exposure_subtype_check BEFORE INSERT ON exposure_zone
WHEN (SELECT feature_type FROM feature WHERE rid = NEW.rid) IS NOT 'exposure'
  OR (SELECT feature_id FROM feature WHERE rid = NEW.rid) IS NOT NEW.zone_id
BEGIN SELECT RAISE(ABORT, 'exposure_zone: feature_type must be exposure and zone_id = feature_id'); END;

-- 发布后内容不可变：只允许向 draft 发布写入、修改或删除。
CREATE TRIGGER feature_insert_draft_only BEFORE INSERT ON feature
WHEN (SELECT status FROM release WHERE release_id = NEW.release_id) <> 'draft'
BEGIN SELECT RAISE(ABORT, 'feature: release is not draft'); END;

CREATE TRIGGER feature_immutable_update BEFORE UPDATE ON feature
WHEN (SELECT status FROM release WHERE release_id = OLD.release_id) <> 'draft'
  OR (SELECT status FROM release WHERE release_id = NEW.release_id) <> 'draft'
BEGIN SELECT RAISE(ABORT, 'feature: published release is immutable'); END;

CREATE TRIGGER feature_immutable_delete BEFORE DELETE ON feature
WHEN (SELECT status FROM release WHERE release_id = OLD.release_id) <> 'draft'
BEGIN SELECT RAISE(ABORT, 'feature: published release is immutable'); END;

CREATE TRIGGER building_immutable_update BEFORE UPDATE ON building
WHEN (SELECT r.status FROM feature f JOIN release r ON r.release_id = f.release_id WHERE f.rid = OLD.rid) <> 'draft'
BEGIN SELECT RAISE(ABORT, 'building: published release is immutable'); END;

CREATE TRIGGER building_immutable_delete BEFORE DELETE ON building
WHEN (SELECT r.status FROM feature f JOIN release r ON r.release_id = f.release_id WHERE f.rid = OLD.rid) <> 'draft'
BEGIN SELECT RAISE(ABORT, 'building: published release is immutable'); END;

CREATE TRIGGER airspace_immutable_update BEFORE UPDATE ON airspace_restriction
WHEN (SELECT r.status FROM feature f JOIN release r ON r.release_id = f.release_id WHERE f.rid = OLD.rid) <> 'draft'
BEGIN SELECT RAISE(ABORT, 'airspace_restriction: published release is immutable'); END;

CREATE TRIGGER airspace_immutable_delete BEFORE DELETE ON airspace_restriction
WHEN (SELECT r.status FROM feature f JOIN release r ON r.release_id = f.release_id WHERE f.rid = OLD.rid) <> 'draft'
BEGIN SELECT RAISE(ABORT, 'airspace_restriction: published release is immutable'); END;

CREATE TRIGGER exposure_immutable_update BEFORE UPDATE ON exposure_zone
WHEN (SELECT r.status FROM feature f JOIN release r ON r.release_id = f.release_id WHERE f.rid = OLD.rid) <> 'draft'
BEGIN SELECT RAISE(ABORT, 'exposure_zone: published release is immutable'); END;

CREATE TRIGGER exposure_immutable_delete BEFORE DELETE ON exposure_zone
WHEN (SELECT r.status FROM feature f JOIN release r ON r.release_id = f.release_id WHERE f.rid = OLD.rid) <> 'draft'
BEGIN SELECT RAISE(ABORT, 'exposure_zone: published release is immutable'); END;

CREATE TRIGGER coverage_immutable_update BEFORE UPDATE ON coverage_tile
WHEN (SELECT status FROM release WHERE release_id = OLD.release_id) <> 'draft'
BEGIN SELECT RAISE(ABORT, 'coverage_tile: published release is immutable'); END;

CREATE TRIGGER coverage_immutable_delete BEFORE DELETE ON coverage_tile
WHEN (SELECT status FROM release WHERE release_id = OLD.release_id) <> 'draft'
BEGIN SELECT RAISE(ABORT, 'coverage_tile: published release is immutable'); END;

CREATE TRIGGER terrain_immutable_update BEFORE UPDATE ON terrain_surface
WHEN (SELECT status FROM release WHERE release_id = OLD.release_id) <> 'draft'
BEGIN SELECT RAISE(ABORT, 'terrain_surface: published release is immutable'); END;

CREATE TRIGGER terrain_immutable_delete BEFORE DELETE ON terrain_surface
WHEN (SELECT status FROM release WHERE release_id = OLD.release_id) <> 'draft'
BEGIN SELECT RAISE(ABORT, 'terrain_surface: published release is immutable'); END;

CREATE TRIGGER terrain_post_immutable_update BEFORE UPDATE ON terrain_post
WHEN (SELECT status FROM release WHERE release_id = OLD.release_id) <> 'draft'
BEGIN SELECT RAISE(ABORT, 'terrain_post: published release is immutable'); END;

CREATE TRIGGER terrain_post_immutable_delete BEFORE DELETE ON terrain_post
WHEN (SELECT status FROM release WHERE release_id = OLD.release_id) <> 'draft'
BEGIN SELECT RAISE(ABORT, 'terrain_post: published release is immutable'); END;

-- 子表写入也必须检查所属发布状态；只在 feature 头表拦截会留下后补子类型的旁路。
CREATE TRIGGER building_insert_draft_only BEFORE INSERT ON building
WHEN (SELECT r.status FROM feature f JOIN release r ON r.release_id = f.release_id
      WHERE f.rid = NEW.rid) <> 'draft'
BEGIN SELECT RAISE(ABORT, 'building: published release is immutable'); END;

CREATE TRIGGER airspace_insert_draft_only BEFORE INSERT ON airspace_restriction
WHEN (SELECT r.status FROM feature f JOIN release r ON r.release_id = f.release_id
      WHERE f.rid = NEW.rid) <> 'draft'
BEGIN SELECT RAISE(ABORT, 'airspace_restriction: published release is immutable'); END;

CREATE TRIGGER exposure_insert_draft_only BEFORE INSERT ON exposure_zone
WHEN (SELECT r.status FROM feature f JOIN release r ON r.release_id = f.release_id
      WHERE f.rid = NEW.rid) <> 'draft'
BEGIN SELECT RAISE(ABORT, 'exposure_zone: published release is immutable'); END;

CREATE TRIGGER coverage_insert_draft_only BEFORE INSERT ON coverage_tile
WHEN (SELECT status FROM release WHERE release_id = NEW.release_id) <> 'draft'
BEGIN SELECT RAISE(ABORT, 'coverage_tile: published release is immutable'); END;

CREATE TRIGGER terrain_insert_draft_only BEFORE INSERT ON terrain_surface
WHEN (SELECT status FROM release WHERE release_id = NEW.release_id) <> 'draft'
BEGIN SELECT RAISE(ABORT, 'terrain_surface: published release is immutable'); END;

CREATE TRIGGER terrain_post_insert_draft_only BEFORE INSERT ON terrain_post
WHEN (SELECT status FROM release WHERE release_id = NEW.release_id) <> 'draft'
BEGIN SELECT RAISE(ABORT, 'terrain_post: published release is immutable'); END;

-- R*Tree 候选索引：只做过滤，精确判定在基表列上复核（R*Tree 以 32 位浮点向外取整）。
CREATE VIRTUAL TABLE rtree_building USING rtree(
    rid, min_x, max_x, min_y, max_y, min_z, max_z
);

-- 空域采用时空四维 R*Tree（x, y, z, t），依据见 docs/modules/yht/v2/experiments/。
CREATE VIRTUAL TABLE rtree_airspace USING rtree(
    rid, min_x, max_x, min_y, max_y, min_z, max_z, min_t, max_t
);

CREATE VIRTUAL TABLE rtree_exposure USING rtree(
    rid, min_x, max_x, min_y, max_y
);

CREATE TRIGGER building_rtree_insert AFTER INSERT ON building BEGIN
    INSERT INTO rtree_building VALUES (NEW.rid, NEW.bbox_min_x, NEW.bbox_max_x,
        NEW.bbox_min_y, NEW.bbox_max_y, NEW.base_z, NEW.top_z);
END;
CREATE TRIGGER building_rtree_update AFTER UPDATE ON building BEGIN
    UPDATE rtree_building SET min_x = NEW.bbox_min_x, max_x = NEW.bbox_max_x,
        min_y = NEW.bbox_min_y, max_y = NEW.bbox_max_y, min_z = NEW.base_z, max_z = NEW.top_z
    WHERE rid = NEW.rid;
END;
CREATE TRIGGER building_rtree_delete AFTER DELETE ON building BEGIN
    DELETE FROM rtree_building WHERE rid = OLD.rid;
END;

-- 空域 R*Tree 的 z 维存禁止飞行的垂直范围（forbid_lo_z/forbid_hi_z），1.0e6 m 表示向上封闭。
CREATE TRIGGER airspace_rtree_insert AFTER INSERT ON airspace_restriction BEGIN
    INSERT INTO rtree_airspace VALUES (NEW.rid, NEW.bbox_min_x, NEW.bbox_max_x,
        NEW.bbox_min_y, NEW.bbox_max_y, NEW.forbid_lo_z, NEW.forbid_hi_z,
        unixepoch(NEW.effective_lo) - 1767225600, unixepoch(NEW.effective_hi) - 1767225600);
END;
CREATE TRIGGER airspace_rtree_update AFTER UPDATE ON airspace_restriction BEGIN
    UPDATE rtree_airspace SET min_x = NEW.bbox_min_x, max_x = NEW.bbox_max_x,
        min_y = NEW.bbox_min_y, max_y = NEW.bbox_max_y,
        min_z = NEW.forbid_lo_z, max_z = NEW.forbid_hi_z,
        min_t = unixepoch(NEW.effective_lo) - 1767225600,
        max_t = unixepoch(NEW.effective_hi) - 1767225600
    WHERE rid = NEW.rid;
END;
CREATE TRIGGER airspace_rtree_delete AFTER DELETE ON airspace_restriction BEGIN
    DELETE FROM rtree_airspace WHERE rid = OLD.rid;
END;

CREATE TRIGGER exposure_rtree_insert AFTER INSERT ON exposure_zone BEGIN
    INSERT INTO rtree_exposure VALUES (NEW.rid, NEW.bbox_min_x, NEW.bbox_max_x,
        NEW.bbox_min_y, NEW.bbox_max_y);
END;
CREATE TRIGGER exposure_rtree_update AFTER UPDATE ON exposure_zone BEGIN
    UPDATE rtree_exposure SET min_x = NEW.bbox_min_x, max_x = NEW.bbox_max_x,
        min_y = NEW.bbox_min_y, max_y = NEW.bbox_max_y
    WHERE rid = NEW.rid;
END;
CREATE TRIGGER exposure_rtree_delete AFTER DELETE ON exposure_zone BEGIN
    DELETE FROM rtree_exposure WHERE rid = OLD.rid;
END;

-- =====================================================================
-- 4 空域事件（YHT 按数据字典建立；ZQO 细化发布/撤销事务）
-- =====================================================================

CREATE TABLE airspace_event (
    event_id          TEXT PRIMARY KEY,
    release_id        TEXT NOT NULL REFERENCES release(release_id) ON DELETE RESTRICT,
    restriction_id    TEXT NOT NULL,
    action            TEXT NOT NULL CHECK (action IN ('publish','update','revoke','expire')),
    occurred_at       TEXT NOT NULL,
    effective_at      TEXT NOT NULL,
    actor_id          TEXT NOT NULL REFERENCES actor(actor_id),
    source_id         TEXT NOT NULL REFERENCES source(source_id),
    payload_hash      TEXT NOT NULL CHECK (length(payload_hash) = 64 AND payload_hash NOT GLOB '*[^0-9a-f]*'),
    reason            TEXT NOT NULL,
    previous_event_id TEXT REFERENCES airspace_event(event_id),
    FOREIGN KEY (release_id, restriction_id) REFERENCES feature(release_id, feature_id),
    CHECK (previous_event_id IS NULL OR previous_event_id <> event_id)
);

CREATE INDEX airspace_event_sequence ON airspace_event(restriction_id, occurred_at);

CREATE TRIGGER airspace_event_monotonic BEFORE INSERT ON airspace_event
WHEN EXISTS (SELECT 1 FROM airspace_event e
             WHERE e.restriction_id = NEW.restriction_id AND e.occurred_at > NEW.occurred_at)
BEGIN SELECT RAISE(ABORT, 'airspace_event: occurred_at must be monotonic per restriction'); END;

CREATE TRIGGER airspace_event_no_update BEFORE UPDATE ON airspace_event
BEGIN SELECT RAISE(ABORT, 'airspace_event: append-only'); END;

CREATE TRIGGER airspace_event_no_delete BEFORE DELETE ON airspace_event
BEGIN SELECT RAISE(ABORT, 'airspace_event: append-only'); END;

-- =====================================================================
-- 5 风险派生、质量与访问（YHT 按数据字典建立字段钩子；LQ 细化）
-- =====================================================================

CREATE TABLE risk_model (
    risk_model_id TEXT PRIMARY KEY,
    model_version TEXT NOT NULL,
    name          TEXT NOT NULL,
    formula       TEXT NOT NULL,
    params        TEXT NOT NULL CHECK (json_valid(params)),
    valid_lo      TEXT NOT NULL,
    valid_hi      TEXT NOT NULL,
    source_id     TEXT NOT NULL REFERENCES source(source_id),
    status        TEXT NOT NULL CHECK (status IN ('draft','approved','retired')),
    approved_by   TEXT REFERENCES actor(actor_id),
    notes         TEXT,
    CHECK (valid_lo < valid_hi),
    CHECK (status <> 'approved' OR approved_by IS NOT NULL)
);

CREATE INDEX exposure_zone_model ON exposure_zone(risk_model_id);

CREATE TABLE access_policy (
    policy_id       TEXT PRIMARY KEY,
    role            TEXT NOT NULL CHECK (role IN ('dispatcher','operator','airspace_admin','system_admin','auditor')),
    resource        TEXT NOT NULL,
    action          TEXT NOT NULL CHECK (action IN ('read','write','publish','approve','export')),
    max_sensitivity TEXT NOT NULL CHECK (max_sensitivity IN ('public','internal','restricted','sensitive')),
    condition       TEXT CHECK (condition IS NULL OR json_valid(condition)),
    status          TEXT NOT NULL CHECK (status IN ('active','retired'))
);

-- 多态血缘边：端点存在性由发布质检校验，数据库只保证不自环与取值合法。
CREATE TABLE lineage_edge (
    edge_id      TEXT PRIMARY KEY,
    from_kind    TEXT NOT NULL CHECK (from_kind IN ('source','feature','release','model','component','dataset')),
    from_id      TEXT NOT NULL,
    to_kind      TEXT NOT NULL CHECK (to_kind IN ('source','feature','release','model','component','dataset')),
    to_id        TEXT NOT NULL,
    activity     TEXT NOT NULL CHECK (activity IN ('derived_from','compiled_from','validated_by','published_as')),
    tool_version TEXT NOT NULL,
    at           TEXT NOT NULL,
    release_id   TEXT REFERENCES release(release_id),
    evidence     TEXT CHECK (evidence IS NULL OR json_valid(evidence)),
    CHECK (NOT (from_kind = to_kind AND from_id = to_id))
);

CREATE INDEX lineage_to ON lineage_edge(to_kind, to_id);
CREATE INDEX lineage_from ON lineage_edge(from_kind, from_id);

CREATE TABLE audit_event (
    event_id    TEXT PRIMARY KEY,
    at          TEXT NOT NULL,
    actor_id    TEXT NOT NULL REFERENCES actor(actor_id),
    action      TEXT NOT NULL CHECK (action IN ('publish','revoke','query','export','deny','approve','quality','model_control')),
    object_kind TEXT NOT NULL,
    object_id   TEXT NOT NULL,
    release_id  TEXT REFERENCES release(release_id),
    result      TEXT NOT NULL CHECK (result IN ('success','denied','error')),
    reason      TEXT,
    request_id  TEXT,
    detail      TEXT CHECK (detail IS NULL OR json_valid(detail))
);

CREATE INDEX audit_event_at ON audit_event(at);

CREATE TRIGGER audit_event_no_update BEFORE UPDATE ON audit_event
BEGIN SELECT RAISE(ABORT, 'audit_event: append-only'); END;

CREATE TRIGGER audit_event_no_delete BEFORE DELETE ON audit_event
BEGIN SELECT RAISE(ABORT, 'audit_event: append-only'); END;

-- LQ v2 extension: immutable model identities, validated derivations, access and approvals.
CREATE TRIGGER risk_model_identity_update BEFORE UPDATE ON risk_model
WHEN OLD.status IN ('approved','retired') OR EXISTS(SELECT 1 FROM exposure_zone WHERE risk_model_id=OLD.risk_model_id)
BEGIN SELECT RAISE(ABORT,'risk_model: immutable version; register a new model id'); END;
CREATE TRIGGER risk_model_identity_delete BEFORE DELETE ON risk_model
WHEN OLD.status IN ('approved','retired') OR EXISTS(SELECT 1 FROM exposure_zone WHERE risk_model_id=OLD.risk_model_id)
BEGIN SELECT RAISE(ABORT,'risk_model: retained version'); END;
-- Activation/retirement is separate from the immutable formula/version payload.
CREATE TABLE risk_model_control (
 risk_model_id TEXT PRIMARY KEY REFERENCES risk_model(risk_model_id),
 enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
 changed_by TEXT NOT NULL REFERENCES actor(actor_id), at TEXT NOT NULL, reason TEXT NOT NULL
);
CREATE TRIGGER model_control_role_insert BEFORE INSERT ON risk_model_control
WHEN NOT EXISTS(SELECT 1 FROM actor WHERE actor_id=NEW.changed_by AND active=1 AND role='airspace_admin')
BEGIN SELECT RAISE(ABORT,'risk_model_control: safety administrator required'); END;
CREATE TRIGGER model_control_role_update BEFORE UPDATE ON risk_model_control
WHEN NEW.risk_model_id<>OLD.risk_model_id OR NOT EXISTS(SELECT 1 FROM actor WHERE actor_id=NEW.changed_by AND active=1 AND role='airspace_admin')
BEGIN SELECT RAISE(ABORT,'risk_model_control: safety administrator required'); END;
CREATE TRIGGER exposure_model_coverage BEFORE INSERT ON exposure_zone
WHEN NOT EXISTS(SELECT 1 FROM risk_model m WHERE m.risk_model_id=NEW.risk_model_id AND m.status='approved'
 AND m.valid_lo<=NEW.valid_lo AND NEW.valid_hi<=m.valid_hi)
BEGIN SELECT RAISE(ABORT,'exposure_zone: approved model must cover input period'); END;

CREATE TRIGGER exposure_model_coverage_update BEFORE UPDATE ON exposure_zone
WHEN NOT EXISTS(SELECT 1 FROM risk_model m WHERE m.risk_model_id=NEW.risk_model_id AND m.status='approved'
 AND m.valid_lo<=NEW.valid_lo AND NEW.valid_hi<=m.valid_hi)
BEGIN SELECT RAISE(ABORT,'exposure_zone: approved model must cover input period'); END;

CREATE TABLE risk_dataset (
 dataset_id TEXT PRIMARY KEY,
 release_id TEXT NOT NULL REFERENCES release(release_id),
 component_id TEXT NOT NULL REFERENCES layer_component(component_id),
 risk_model_id TEXT NOT NULL REFERENCES risk_model(risk_model_id),
 window_lo TEXT NOT NULL, window_hi TEXT NOT NULL,
 compiler_version TEXT NOT NULL CHECK(length(trim(compiler_version))>0), created_by TEXT NOT NULL REFERENCES actor(actor_id),
 created_at TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'draft' CHECK(state IN ('draft','validated')),
 CHECK(window_lo<window_hi)
);
CREATE INDEX risk_dataset_release ON risk_dataset(release_id, risk_model_id);
CREATE TRIGGER risk_dataset_scope BEFORE INSERT ON risk_dataset BEGIN
 SELECT CASE WHEN NEW.state<>'draft' OR NOT EXISTS(
 SELECT 1 FROM release r JOIN release_component rc USING(release_id)
 JOIN risk_model m ON m.risk_model_id=NEW.risk_model_id
 WHERE r.release_id=NEW.release_id AND r.status<>'draft' AND rc.layer='exposure'
 AND rc.component_id=NEW.component_id AND r.valid_lo=NEW.window_lo AND r.valid_hi=NEW.window_hi
 AND m.status='approved' AND m.valid_lo<=NEW.window_lo AND NEW.window_hi<=m.valid_hi)
 THEN RAISE(ABORT,'risk_dataset: matching published component/model/window required') END;
END;
CREATE TRIGGER risk_dataset_identity BEFORE UPDATE ON risk_dataset
WHEN OLD.state='validated' OR NEW.dataset_id<>OLD.dataset_id OR NEW.release_id<>OLD.release_id
 OR NEW.component_id<>OLD.component_id OR NEW.risk_model_id<>OLD.risk_model_id
 OR NEW.window_lo<>OLD.window_lo OR NEW.window_hi<>OLD.window_hi
 OR NEW.compiler_version<>OLD.compiler_version OR NEW.created_by<>OLD.created_by OR NEW.created_at<>OLD.created_at
BEGIN SELECT RAISE(ABORT,'risk_dataset: immutable identity or validated result'); END;
CREATE TRIGGER risk_dataset_retain BEFORE DELETE ON risk_dataset
BEGIN SELECT RAISE(ABORT,'risk_dataset: retain derivation evidence'); END;
CREATE TABLE risk_input_period (
 dataset_id TEXT NOT NULL REFERENCES risk_dataset(dataset_id),
 zone_rid INTEGER NOT NULL REFERENCES exposure_zone(rid),
 valid_lo TEXT NOT NULL, valid_hi TEXT NOT NULL,
 exposure_e REAL NOT NULL CHECK(exposure_e BETWEEN 0 AND 1),
 consequence_c REAL NOT NULL CHECK(consequence_c BETWEEN 0 AND 1),
 PRIMARY KEY(dataset_id,zone_rid,valid_lo), CHECK(valid_lo<valid_hi),
 CHECK(unixepoch(valid_lo) IS NOT NULL AND unixepoch(valid_hi) IS NOT NULL
 AND strftime('%Y-%m-%dT%H:%M:%SZ',valid_lo)=valid_lo AND strftime('%Y-%m-%dT%H:%M:%SZ',valid_hi)=valid_hi)
);
CREATE TABLE derived_risk (
 dataset_id TEXT NOT NULL REFERENCES risk_dataset(dataset_id),
 zone_rid INTEGER NOT NULL REFERENCES exposure_zone(rid),
 q_max REAL NOT NULL CHECK(q_max BETWEEN 0 AND 1),
 source_id TEXT NOT NULL REFERENCES source(source_id),
 PRIMARY KEY(dataset_id,zone_rid)
);
CREATE TABLE quality_check (
 check_id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL REFERENCES risk_dataset(dataset_id),
 rule TEXT NOT NULL, result TEXT NOT NULL CHECK(result IN ('pass','fail')),
 checked_at TEXT NOT NULL, actor_id TEXT NOT NULL REFERENCES actor(actor_id),
 detail TEXT NOT NULL CHECK(json_valid(detail))
);
CREATE INDEX quality_dataset ON quality_check(dataset_id,rule,result);
CREATE TRIGGER period_scope BEFORE INSERT ON risk_input_period BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM risk_dataset d JOIN layer_component lc USING(component_id)
 JOIN feature f ON f.release_id=lc.owner_release_id JOIN exposure_zone e USING(rid)
 WHERE d.dataset_id=NEW.dataset_id AND d.state='draft' AND e.rid=NEW.zone_rid AND e.risk_model_id=d.risk_model_id
 AND d.window_lo<=NEW.valid_lo AND NEW.valid_hi<=d.window_hi
 AND e.quality<>'unknown' AND f.quality<>'unknown'
 AND e.valid_lo<=NEW.valid_lo AND NEW.valid_hi<=e.valid_hi)
 THEN RAISE(ABORT,'risk_input_period: invalid component/window/state') END;
 SELECT CASE WHEN EXISTS(SELECT 1 FROM risk_input_period p WHERE p.dataset_id=NEW.dataset_id
 AND p.zone_rid=NEW.zone_rid AND p.valid_lo<NEW.valid_hi AND NEW.valid_lo<p.valid_hi)
 THEN RAISE(ABORT,'risk_input_period: overlap') END;
END;
CREATE TRIGGER period_no_update BEFORE UPDATE ON risk_input_period
BEGIN SELECT RAISE(ABORT,'risk_input_period: append-only'); END;
CREATE TRIGGER period_no_delete BEFORE DELETE ON risk_input_period
BEGIN SELECT RAISE(ABORT,'risk_input_period: append-only'); END;
CREATE TRIGGER derived_scope BEFORE INSERT ON derived_risk
WHEN NOT EXISTS(SELECT 1 FROM risk_dataset d JOIN layer_component lc USING(component_id)
 JOIN feature f ON f.release_id=lc.owner_release_id JOIN exposure_zone e USING(rid)
 WHERE d.dataset_id=NEW.dataset_id AND d.state='draft' AND e.rid=NEW.zone_rid
 AND e.risk_model_id=d.risk_model_id AND e.source_id=NEW.source_id)
BEGIN SELECT RAISE(ABORT,'derived_risk: source/component mismatch or sealed dataset'); END;
CREATE TRIGGER derived_no_update BEFORE UPDATE ON derived_risk
BEGIN SELECT RAISE(ABORT,'derived_risk: append-only'); END;
CREATE TRIGGER derived_no_delete BEFORE DELETE ON derived_risk
BEGIN SELECT RAISE(ABORT,'derived_risk: append-only'); END;
CREATE TRIGGER quality_no_update BEFORE UPDATE ON quality_check
BEGIN SELECT RAISE(ABORT,'quality_check: append-only'); END;
CREATE TRIGGER quality_no_delete BEFORE DELETE ON quality_check
BEGIN SELECT RAISE(ABORT,'quality_check: append-only'); END;
CREATE TRIGGER dataset_validate BEFORE UPDATE OF state ON risk_dataset
WHEN NEW.state='validated' BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM quality_check WHERE dataset_id=NEW.dataset_id
 AND rule='coverage_and_max' AND result='pass') THEN RAISE(ABORT,'risk_dataset: quality evidence required') END;
 SELECT CASE WHEN EXISTS(
 SELECT 1 FROM layer_component lc JOIN feature f ON f.release_id=lc.owner_release_id
 JOIN exposure_zone e USING(rid) WHERE lc.component_id=NEW.component_id AND (
 NOT EXISTS(SELECT 1 FROM derived_risk dr WHERE dr.dataset_id=NEW.dataset_id AND dr.zone_rid=e.rid)
 OR (SELECT coalesce(sum(unixepoch(p.valid_hi)-unixepoch(p.valid_lo)),0) FROM risk_input_period p
 WHERE p.dataset_id=NEW.dataset_id AND p.zone_rid=e.rid)<>unixepoch(NEW.window_hi)-unixepoch(NEW.window_lo)
 OR abs((SELECT dr.q_max FROM derived_risk dr WHERE dr.dataset_id=NEW.dataset_id AND dr.zone_rid=e.rid)
 -(SELECT max(p.exposure_e*p.consequence_c) FROM risk_input_period p WHERE p.dataset_id=NEW.dataset_id AND p.zone_rid=e.rid))>1e-9))
 THEN RAISE(ABORT,'risk_dataset: gap/missing result/incorrect maximum') END;
END;

CREATE TABLE governance_request (
 request_id TEXT PRIMARY KEY,
 object_kind TEXT NOT NULL CHECK(object_kind IN ('release','model','dataset')),
 object_id TEXT NOT NULL, author_id TEXT NOT NULL REFERENCES actor(actor_id),
 payload_hash TEXT NOT NULL CHECK(length(payload_hash)=64 AND payload_hash NOT GLOB '*[^0-9a-f]*'),
 created_at TEXT NOT NULL, UNIQUE(object_kind,object_id)
);
CREATE TABLE governance_approval (
 request_id TEXT PRIMARY KEY REFERENCES governance_request(request_id),
 reviewer_id TEXT NOT NULL REFERENCES actor(actor_id),
 decision TEXT NOT NULL CHECK(decision IN ('approved','rejected')),
 at TEXT NOT NULL, reason TEXT NOT NULL CHECK(length(reason)>0)
);
CREATE TRIGGER request_author BEFORE INSERT ON governance_request
WHEN NOT EXISTS(SELECT 1 FROM actor WHERE actor_id=NEW.author_id AND active=1 AND role='airspace_admin')
BEGIN SELECT RAISE(ABORT,'governance_request: active author required'); END;
CREATE TRIGGER approval_separation BEFORE INSERT ON governance_approval
WHEN NOT EXISTS(SELECT 1 FROM governance_request r JOIN actor author ON author.actor_id=r.author_id
 JOIN actor reviewer ON reviewer.actor_id=NEW.reviewer_id
 WHERE r.request_id=NEW.request_id AND author.active=1 AND reviewer.active=1
 AND reviewer.org=author.org AND reviewer.role='airspace_admin' AND reviewer.actor_id<>r.author_id)
BEGIN SELECT RAISE(ABORT,'governance_approval: independent active safety reviewer required'); END;
CREATE TRIGGER governance_request_no_update BEFORE UPDATE ON governance_request
BEGIN SELECT RAISE(ABORT,'governance_request: immutable'); END;
CREATE TRIGGER governance_request_no_delete BEFORE DELETE ON governance_request
BEGIN SELECT RAISE(ABORT,'governance_request: retained'); END;
CREATE TRIGGER approval_no_update BEFORE UPDATE ON governance_approval
BEGIN SELECT RAISE(ABORT,'governance_approval: immutable decision'); END;
CREATE TRIGGER approval_no_delete BEFORE DELETE ON governance_approval
BEGIN SELECT RAISE(ABORT,'governance_approval: retained'); END;

-- Service connection registers current_actor(); no client-supplied role parameter.
CREATE VIEW v_exposure_summary AS
SELECT rf.query_release_id AS release_id,
 CAST(e.bbox_min_x/200 AS INTEGER)*200 AS cell_x,
 CAST(e.bbox_min_y/200 AS INTEGER)*200 AS cell_y,
 count(*) AS zone_count, round(max(e.q),1) AS display_proxy
FROM resolved_feature rf JOIN exposure_zone e USING(rid) JOIN source s ON s.source_id=e.source_id
JOIN actor a ON a.actor_id=current_actor() AND a.active=1 AND a.org=s.owner_org
WHERE EXISTS(SELECT 1 FROM access_policy p WHERE p.role=a.role AND p.resource='v_exposure_summary'
 AND p.action='read' AND p.status='active'
 AND (CASE e.sensitivity WHEN 'public' THEN 0 WHEN 'internal' THEN 1 WHEN 'restricted' THEN 2 ELSE 3 END)
 <= (CASE p.max_sensitivity WHEN 'public' THEN 0 WHEN 'internal' THEN 1 WHEN 'restricted' THEN 2 ELSE 3 END)
 AND (CASE s.sensitivity WHEN 'public' THEN 0 WHEN 'internal' THEN 1 WHEN 'restricted' THEN 2 ELSE 3 END)
 <= (CASE p.max_sensitivity WHEN 'public' THEN 0 WHEN 'internal' THEN 1 WHEN 'restricted' THEN 2 ELSE 3 END))
GROUP BY rf.query_release_id,cell_x,cell_y HAVING count(*)>=2;
CREATE VIEW v_exposure_detail AS
SELECT rf.query_release_id AS release_id,e.* FROM resolved_feature rf JOIN exposure_zone e USING(rid)
JOIN source s ON s.source_id=e.source_id JOIN actor a ON a.actor_id=current_actor() AND a.active=1 AND a.org=s.owner_org
WHERE a.role='airspace_admin' AND EXISTS(SELECT 1 FROM access_policy p WHERE p.role=a.role
 AND p.resource='v_exposure_detail' AND p.action='read' AND p.status='active'
 AND (CASE e.sensitivity WHEN 'public' THEN 0 WHEN 'internal' THEN 1 WHEN 'restricted' THEN 2 ELSE 3 END)
 <= (CASE p.max_sensitivity WHEN 'public' THEN 0 WHEN 'internal' THEN 1 WHEN 'restricted' THEN 2 ELSE 3 END)
 AND (CASE s.sensitivity WHEN 'public' THEN 0 WHEN 'internal' THEN 1 WHEN 'restricted' THEN 2 ELSE 3 END)
 <= (CASE p.max_sensitivity WHEN 'public' THEN 0 WHEN 'internal' THEN 1 WHEN 'restricted' THEN 2 ELSE 3 END));

CREATE TRIGGER lineage_from_exists BEFORE INSERT ON lineage_edge
WHEN NOT ((NEW.from_kind='source' AND EXISTS(SELECT 1 FROM source WHERE CAST(source_id AS TEXT)=NEW.from_id)) OR (NEW.from_kind='feature' AND EXISTS(SELECT 1 FROM feature WHERE CAST(rid AS TEXT)=NEW.from_id)) OR (NEW.from_kind='release' AND EXISTS(SELECT 1 FROM release WHERE CAST(release_id AS TEXT)=NEW.from_id)) OR (NEW.from_kind='model' AND EXISTS(SELECT 1 FROM risk_model WHERE CAST(risk_model_id AS TEXT)=NEW.from_id)) OR (NEW.from_kind='component' AND EXISTS(SELECT 1 FROM layer_component WHERE CAST(component_id AS TEXT)=NEW.from_id)) OR (NEW.from_kind='dataset' AND EXISTS(SELECT 1 FROM risk_dataset WHERE CAST(dataset_id AS TEXT)=NEW.from_id)))
BEGIN SELECT RAISE(ABORT,'lineage_edge: missing from endpoint'); END;
CREATE TRIGGER lineage_to_exists BEFORE INSERT ON lineage_edge
WHEN NOT ((NEW.to_kind='source' AND EXISTS(SELECT 1 FROM source WHERE CAST(source_id AS TEXT)=NEW.to_id)) OR (NEW.to_kind='feature' AND EXISTS(SELECT 1 FROM feature WHERE CAST(rid AS TEXT)=NEW.to_id)) OR (NEW.to_kind='release' AND EXISTS(SELECT 1 FROM release WHERE CAST(release_id AS TEXT)=NEW.to_id)) OR (NEW.to_kind='model' AND EXISTS(SELECT 1 FROM risk_model WHERE CAST(risk_model_id AS TEXT)=NEW.to_id)) OR (NEW.to_kind='component' AND EXISTS(SELECT 1 FROM layer_component WHERE CAST(component_id AS TEXT)=NEW.to_id)) OR (NEW.to_kind='dataset' AND EXISTS(SELECT 1 FROM risk_dataset WHERE CAST(dataset_id AS TEXT)=NEW.to_id)))
BEGIN SELECT RAISE(ABORT,'lineage_edge: missing to endpoint'); END;
CREATE TRIGGER lineage_dataset_dependency BEFORE INSERT ON lineage_edge
WHEN NEW.to_kind='dataset' AND NOT EXISTS(SELECT 1 FROM risk_dataset d WHERE d.dataset_id=NEW.to_id
 AND NEW.release_id=d.release_id AND (
 (NEW.from_kind='model' AND NEW.from_id=d.risk_model_id) OR
 (NEW.from_kind='component' AND NEW.from_id=d.component_id) OR
 (NEW.from_kind='source' AND EXISTS(SELECT 1 FROM derived_risk r WHERE r.dataset_id=d.dataset_id AND r.source_id=NEW.from_id))))
BEGIN SELECT RAISE(ABORT,'lineage_edge: dataset dependency mismatch'); END;
CREATE TRIGGER lineage_no_update BEFORE UPDATE ON lineage_edge
BEGIN SELECT RAISE(ABORT,'lineage_edge: immutable evidence'); END;
CREATE TRIGGER lineage_no_delete BEFORE DELETE ON lineage_edge
BEGIN SELECT RAISE(ABORT,'lineage_edge: retained evidence'); END;
CREATE TRIGGER approval_audit AFTER INSERT ON governance_approval BEGIN
 INSERT INTO audit_event(event_id,at,actor_id,action,object_kind,object_id,result,reason,request_id)
 VALUES('approval:'||NEW.request_id,NEW.at,NEW.reviewer_id,'approve','governance_request',NEW.request_id,
 CASE WHEN NEW.decision='approved' THEN 'success' ELSE 'denied' END,NEW.reason,NEW.request_id);
END;
CREATE TRIGGER model_control_audit_insert AFTER INSERT ON risk_model_control BEGIN
 INSERT INTO audit_event(event_id,at,actor_id,action,object_kind,object_id,result,reason)
 VALUES('model-control:'||lower(hex(randomblob(16))),NEW.at,NEW.changed_by,'model_control','model',NEW.risk_model_id,'success',NEW.reason);
END;
CREATE TRIGGER model_control_audit_update AFTER UPDATE ON risk_model_control BEGIN
 INSERT INTO audit_event(event_id,at,actor_id,action,object_kind,object_id,result,reason)
 VALUES('model-control:'||lower(hex(randomblob(16))),NEW.at,NEW.changed_by,'model_control','model',NEW.risk_model_id,'success',NEW.reason);
END;

-- 来源身份即版本身份：一旦被非 draft 发布引用，source 行不得 UPDATE/DELETE；
-- 许可或精度修订必须登记新的 source_id，旧发布仍解析到旧行。
CREATE VIEW source_provenance_usage AS
SELECT f.source_id AS source_id
FROM feature f JOIN release r ON r.release_id = f.release_id
WHERE r.status <> 'draft'
UNION
SELECT b.footprint_source FROM building b
JOIN feature f ON f.rid = b.rid JOIN release r ON r.release_id = f.release_id
WHERE r.status <> 'draft'
UNION
SELECT b.height_source FROM building b
JOIN feature f ON f.rid = b.rid JOIN release r ON r.release_id = f.release_id
WHERE r.status <> 'draft'
UNION
SELECT a.source_id FROM airspace_restriction a
JOIN feature f ON f.rid = a.rid JOIN release r ON r.release_id = f.release_id
WHERE r.status <> 'draft'
UNION
SELECT e.source_id FROM exposure_zone e
JOIN feature f ON f.rid = e.rid JOIN release r ON r.release_id = f.release_id
WHERE r.status <> 'draft'
UNION
SELECT t.source_id FROM terrain_surface t JOIN release r ON r.release_id = t.release_id
WHERE r.status <> 'draft'
UNION
SELECT p.source_id FROM terrain_post p JOIN release r ON r.release_id = p.release_id
WHERE r.status <> 'draft'
UNION
SELECT c.source_id FROM coverage_tile c JOIN release r ON r.release_id = c.release_id
WHERE r.status <> 'draft'
UNION
SELECT ev.source_id FROM airspace_event ev JOIN release r ON r.release_id = ev.release_id
WHERE r.status <> 'draft'
UNION
SELECT rm.source_id FROM risk_model rm
JOIN exposure_zone e ON e.risk_model_id = rm.risk_model_id
JOIN feature f ON f.rid = e.rid JOIN release r ON r.release_id = f.release_id
WHERE r.status <> 'draft'
UNION
SELECT cs.source_id FROM component_source cs
JOIN layer_component c ON c.component_id = cs.component_id
JOIN release r ON r.release_id = c.owner_release_id
WHERE r.status <> 'draft'
UNION
SELECT cs.source_id FROM component_source cs
JOIN release_component rc ON rc.component_id = cs.component_id
JOIN release r ON r.release_id = rc.release_id
WHERE r.status <> 'draft';

CREATE TRIGGER source_immutable_update BEFORE UPDATE ON source
WHEN EXISTS (SELECT 1 FROM source_provenance_usage u WHERE u.source_id = OLD.source_id)
BEGIN SELECT RAISE(ABORT, 'source: referenced source is immutable; register a new source_id'); END;

CREATE TRIGGER source_immutable_delete BEFORE DELETE ON source
WHEN EXISTS (SELECT 1 FROM source_provenance_usage u WHERE u.source_id = OLD.source_id)
BEGIN SELECT RAISE(ABORT, 'source: referenced source is immutable; register a new source_id'); END;

-- =====================================================================
-- 6 查询与结果追溯（ZC）
-- 一次规划查询绑定一个逻辑发布与任务窗口；结果、航段来源与派生图缓存都随该发布不可变。
-- 缓存按发布记账：旧发布的缓存对旧发布永久有效，新发布只能“沿用（carried）/修补（patched）/新建（built）”。
-- =====================================================================

CREATE TABLE route_graph_cache (
    graph_id        TEXT PRIMARY KEY,
    release_id      TEXT NOT NULL REFERENCES release(release_id),
    dataset_id      TEXT NOT NULL REFERENCES risk_dataset(dataset_id),
    min_x REAL NOT NULL, min_y REAL NOT NULL, min_z REAL NOT NULL,
    max_x REAL NOT NULL, max_y REAL NOT NULL, max_z REAL NOT NULL,
    window_lo       TEXT NOT NULL,
    window_hi       TEXT NOT NULL,
    config_hash     TEXT NOT NULL CHECK (length(config_hash) = 64 AND config_hash NOT GLOB '*[^0-9a-f]*'),
    payload_hash    TEXT NOT NULL CHECK (length(payload_hash) = 64 AND payload_hash NOT GLOB '*[^0-9a-f]*'),
    node_count      INTEGER NOT NULL CHECK (node_count > 0),
    edge_count      INTEGER NOT NULL CHECK (edge_count >= 0),
    origin          TEXT NOT NULL CHECK (origin IN ('built','carried','patched')),
    parent_graph_id TEXT REFERENCES route_graph_cache(graph_id),
    created_at      TEXT NOT NULL,
    build_ms        REAL NOT NULL CHECK (build_ms >= 0),
    UNIQUE (release_id, min_x, min_y, min_z, max_x, max_y, max_z, window_lo, window_hi, config_hash),
    CHECK (min_x < max_x AND min_y < max_y AND min_z < max_z),
    CHECK (window_lo < window_hi),
    CHECK ((origin = 'built') = (parent_graph_id IS NULL))
);

CREATE INDEX route_graph_release ON route_graph_cache(release_id, window_lo, window_hi);

CREATE TABLE query_run (
    query_id     TEXT PRIMARY KEY,
    release_id   TEXT NOT NULL REFERENCES release(release_id),
    actor_id     TEXT NOT NULL REFERENCES actor(actor_id),
    requested_at TEXT NOT NULL,
    window_lo    TEXT NOT NULL,
    window_hi    TEXT NOT NULL,
    start_x REAL NOT NULL, start_y REAL NOT NULL, start_z REAL NOT NULL,
    goal_x  REAL NOT NULL, goal_y  REAL NOT NULL, goal_z  REAL NOT NULL,
    planner_config TEXT NOT NULL CHECK (json_valid(planner_config)),
    config_hash  TEXT NOT NULL CHECK (length(config_hash) = 64 AND config_hash NOT GLOB '*[^0-9a-f]*'),
    algorithm    TEXT NOT NULL CHECK (algorithm IN ('astar','dijkstra')),
    access_path  TEXT NOT NULL CHECK (access_path IN ('json_snapshot','sql_full','sql_rtree','graph_cache')),
    status       TEXT NOT NULL CHECK (status IN ('feasible','infeasible','unknown')),
    reason       TEXT NOT NULL,
    freshness    TEXT NOT NULL CHECK (freshness IN ('current','historical')),
    graph_id     TEXT REFERENCES route_graph_cache(graph_id),
    CHECK (window_lo < window_hi),
    CHECK ((access_path = 'graph_cache') = (graph_id IS NOT NULL))
);

CREATE INDEX query_run_release ON query_run(release_id, requested_at);

CREATE TABLE route_result (
    query_id   TEXT PRIMARY KEY REFERENCES query_run(query_id),
    length_m   REAL NOT NULL CHECK (length_m >= 0),
    time_s     REAL NOT NULL CHECK (time_s >= 0),
    risk_proxy REAL NOT NULL CHECK (risk_proxy >= 0),
    cost       REAL NOT NULL CHECK (cost >= 0),
    waypoints  TEXT NOT NULL CHECK (json_valid(waypoints) AND json_array_length(waypoints) >= 2)
);

-- 航段的风险来源（满足 LQ 操作 C 合同）：一个航段可有多个分区来源。
CREATE TABLE route_segment_source (
    query_id     TEXT NOT NULL REFERENCES route_result(query_id),
    segment_no   INTEGER NOT NULL CHECK (segment_no >= 1),
    component_id TEXT NOT NULL REFERENCES layer_component(component_id),
    zone_rid     INTEGER NOT NULL REFERENCES exposure_zone(rid),
    dataset_id   TEXT NOT NULL REFERENCES risk_dataset(dataset_id),
    PRIMARY KEY (query_id, segment_no, zone_rid)
);

CREATE INDEX route_segment_source_zone ON route_segment_source(zone_rid);

-- 查询只能绑定已发布且五层映射完整的发布；任务窗口必须落在发布有效期内；
-- freshness 由数据库按当前指针判定；只有业务角色可提交查询。
CREATE TRIGGER query_run_scope BEFORE INSERT ON query_run BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM release r WHERE r.release_id = NEW.release_id AND r.status <> 'draft'
          AND r.valid_lo <= NEW.window_lo AND NEW.window_hi <= r.valid_hi
          AND (SELECT count(*) FROM release_component rc WHERE rc.release_id = r.release_id) = 5)
    THEN RAISE(ABORT, 'query_run: published mapped release covering the window required') END;
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM actor a WHERE a.actor_id = NEW.actor_id AND a.active = 1
          AND a.role IN ('dispatcher','operator','airspace_admin'))
    THEN RAISE(ABORT, 'query_run: active business actor required') END;
    SELECT CASE WHEN NEW.freshness IS NOT (
        CASE WHEN EXISTS (SELECT 1 FROM current_release h JOIN release r ON r.scene_id = h.scene_id
                          WHERE r.release_id = NEW.release_id AND h.release_id = NEW.release_id)
             THEN 'current' ELSE 'historical' END)
    THEN RAISE(ABORT, 'query_run: freshness must match the current release pointer') END;
    SELECT CASE WHEN NEW.graph_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM route_graph_cache g WHERE g.graph_id = NEW.graph_id
          AND g.release_id = NEW.release_id AND g.config_hash = NEW.config_hash
          AND g.window_lo = NEW.window_lo AND g.window_hi = NEW.window_hi
          AND NEW.start_x BETWEEN g.min_x AND g.max_x AND NEW.start_y BETWEEN g.min_y AND g.max_y
          AND NEW.start_z BETWEEN g.min_z AND g.max_z AND NEW.goal_x BETWEEN g.min_x AND g.max_x
          AND NEW.goal_y BETWEEN g.min_y AND g.max_y AND NEW.goal_z BETWEEN g.min_z AND g.max_z)
    THEN RAISE(ABORT, 'query_run: graph must match release, window, config and endpoints') END;
END;

CREATE TRIGGER route_result_feasible BEFORE INSERT ON route_result
WHEN (SELECT status FROM query_run WHERE query_id = NEW.query_id) IS NOT 'feasible'
BEGIN SELECT RAISE(ABORT, 'route_result: only feasible queries have a route'); END;

-- 来源必须是该查询发布的暴露组件、该组件物理 owner 下的分区，以及覆盖任务窗口的已封存风险数据集。
CREATE TRIGGER route_segment_source_scope BEFORE INSERT ON route_segment_source BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM query_run q
        JOIN release_component rc ON rc.release_id = q.release_id AND rc.layer = 'exposure'
                                 AND rc.component_id = NEW.component_id
        JOIN layer_component lc ON lc.component_id = rc.component_id
        JOIN feature f ON f.rid = NEW.zone_rid AND f.release_id = lc.owner_release_id
                      AND f.feature_type = 'exposure'
        JOIN risk_dataset d ON d.dataset_id = NEW.dataset_id AND d.release_id = q.release_id
                           AND d.component_id = rc.component_id AND d.state = 'validated'
                           AND d.window_lo <= q.window_lo AND q.window_hi <= d.window_hi
        WHERE q.query_id = NEW.query_id)
    THEN RAISE(ABORT, 'route_segment_source: component/zone/dataset must match the query release and window') END;
    SELECT CASE WHEN NEW.segment_no > (
        SELECT json_array_length(waypoints) - 1 FROM route_result WHERE query_id = NEW.query_id)
    THEN RAISE(ABORT, 'route_segment_source: segment_no beyond route') END;
END;

-- 缓存行绑定已发布版本、匹配的风险数据集；沿用/修补必须继承同一域、窗口与配置。
CREATE TRIGGER route_graph_cache_scope BEFORE INSERT ON route_graph_cache BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM release r JOIN risk_dataset d ON d.dataset_id = NEW.dataset_id
        JOIN release_component rc ON rc.release_id = r.release_id AND rc.layer = 'exposure'
                                 AND rc.component_id = d.component_id
        WHERE r.release_id = NEW.release_id AND r.status <> 'draft' AND d.release_id = r.release_id
          AND d.state = 'validated' AND d.window_lo <= NEW.window_lo AND NEW.window_hi <= d.window_hi
          AND r.valid_lo <= NEW.window_lo AND NEW.window_hi <= r.valid_hi)
    THEN RAISE(ABORT, 'route_graph_cache: published release and covering validated dataset required') END;
    SELECT CASE WHEN NEW.parent_graph_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM route_graph_cache p WHERE p.graph_id = NEW.parent_graph_id
          AND p.release_id <> NEW.release_id
          AND p.min_x = NEW.min_x AND p.min_y = NEW.min_y AND p.min_z = NEW.min_z
          AND p.max_x = NEW.max_x AND p.max_y = NEW.max_y AND p.max_z = NEW.max_z
          AND p.window_lo = NEW.window_lo AND p.window_hi = NEW.window_hi
          AND p.config_hash = NEW.config_hash
          AND (NEW.origin <> 'carried' OR p.payload_hash = NEW.payload_hash))
    THEN RAISE(ABORT, 'route_graph_cache: parent must share domain, window and config') END;
END;

CREATE TRIGGER route_graph_cache_no_update BEFORE UPDATE ON route_graph_cache
BEGIN SELECT RAISE(ABORT, 'route_graph_cache: append-only'); END;
CREATE TRIGGER route_graph_cache_no_delete BEFORE DELETE ON route_graph_cache
BEGIN SELECT RAISE(ABORT, 'route_graph_cache: append-only'); END;
CREATE TRIGGER query_run_no_update BEFORE UPDATE ON query_run
BEGIN SELECT RAISE(ABORT, 'query_run: append-only'); END;
CREATE TRIGGER query_run_no_delete BEFORE DELETE ON query_run
BEGIN SELECT RAISE(ABORT, 'query_run: append-only'); END;
CREATE TRIGGER route_result_no_update BEFORE UPDATE ON route_result
BEGIN SELECT RAISE(ABORT, 'route_result: append-only'); END;
CREATE TRIGGER route_result_no_delete BEFORE DELETE ON route_result
BEGIN SELECT RAISE(ABORT, 'route_result: append-only'); END;
CREATE TRIGGER route_segment_source_no_update BEFORE UPDATE ON route_segment_source
BEGIN SELECT RAISE(ABORT, 'route_segment_source: append-only'); END;
CREATE TRIGGER route_segment_source_no_delete BEFORE DELETE ON route_segment_source
BEGIN SELECT RAISE(ABORT, 'route_segment_source: append-only'); END;

-- =====================================================================
-- 7 运行与恢复（LJ 预留：备份记录、恢复核验结果）
-- =====================================================================
