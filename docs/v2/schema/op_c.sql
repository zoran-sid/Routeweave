-- 操作 C：追溯一次航线查询所用的数据来源（正式表版本，ZC）
-- 参数：:query_id
-- 链路：query_run → 逻辑发布 → exposure 组件 → 物理 owner 下的分区 → 已封存风险数据集 → 派生值 → 来源 → 发布来源清单 → 模型版本。
-- 与 LQ 临时夹具版（docs/modules/lq/v2/experiments/op_c.sql）的差异：任务窗口只需落在数据集窗口内，
-- 不要求两者相等——规划任务通常是10分钟窗口，而风险数据集按发布有效期编译。
-- route_segment_source 的插入触发器已在写入时校验组件、分区、数据集与窗口，这里再次连接以便独立复核。
-- 内部追溯 SQL：对外入口须先核验认证身份、机构与权限（LQ 第7.3节），不能直接开放给客户端。
SELECT q.query_id, q.window_lo AS task_window_lo, q.window_hi AS task_window_hi,
       seg.segment_no, r.release_id, rc.component_id, lc.owner_release_id,
       f.feature_id AS zone_id, src.source_id, src.name AS source_name,
       m.risk_model_id, m.model_version, dr.q_max,
       d.dataset_id, d.window_lo AS dataset_window_lo, d.window_hi AS dataset_window_hi,
       json_extract(r.manifest, '$.provenance.source_versions.exposure') AS upstream_exposure_version
FROM query_run AS q
JOIN release AS r ON r.release_id = q.release_id
JOIN route_segment_source AS seg ON seg.query_id = q.query_id
JOIN release_component AS rc ON rc.release_id = r.release_id AND rc.layer = 'exposure'
                            AND rc.component_id = seg.component_id
JOIN layer_component AS lc ON lc.component_id = rc.component_id
JOIN feature AS f ON f.rid = seg.zone_rid AND f.release_id = lc.owner_release_id
JOIN risk_dataset AS d ON d.dataset_id = seg.dataset_id AND d.release_id = q.release_id
                      AND d.component_id = rc.component_id AND d.state = 'validated'
                      AND d.window_lo <= q.window_lo AND q.window_hi <= d.window_hi
JOIN derived_risk AS dr ON dr.dataset_id = d.dataset_id AND dr.zone_rid = f.rid
JOIN risk_model AS m ON m.risk_model_id = d.risk_model_id
JOIN source AS src ON src.source_id = dr.source_id
JOIN release_component AS source_rc ON source_rc.release_id = q.release_id AND source_rc.layer = 'sources'
JOIN component_source AS cs ON cs.component_id = source_rc.component_id AND cs.source_id = src.source_id
WHERE q.query_id = :query_id
ORDER BY seg.segment_no, zone_id;
