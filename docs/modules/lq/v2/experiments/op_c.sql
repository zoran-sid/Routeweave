-- query_run / route_segment_source are TEMP fixtures shaped like ZC's production tables.
-- LQ-V2-02 (fixed by ZC on the user's instruction, 2026-11-07): the task window must lie
-- inside the dataset window; equality rejected every real 10-minute task.
SELECT q.query_id, seg.segment_no, r.release_id, rc.component_id,
       lc.owner_release_id, f.feature_id AS zone_id, src.source_id, src.name AS source_name,
       m.risk_model_id,m.model_version,dr.q_max,d.window_lo,d.window_hi,
       json_extract(r.manifest,'$.provenance.source_versions.exposure') AS upstream_exposure_version
FROM query_run q JOIN release r ON r.release_id=q.release_id
JOIN route_segment_source seg ON seg.query_id=q.query_id
JOIN release_component rc ON rc.release_id=r.release_id AND rc.layer='exposure' AND rc.component_id=seg.component_id
JOIN layer_component lc ON lc.component_id=rc.component_id
JOIN feature f ON f.rid=seg.zone_rid AND f.release_id=lc.owner_release_id
JOIN risk_dataset d ON d.dataset_id=seg.dataset_id AND d.release_id=q.release_id AND d.component_id=rc.component_id AND d.state='validated' AND d.window_lo<=q.window_lo AND q.window_hi<=d.window_hi
JOIN derived_risk dr ON dr.dataset_id=d.dataset_id AND dr.zone_rid=f.rid
JOIN risk_model m ON m.risk_model_id=d.risk_model_id
JOIN source src ON src.source_id=dr.source_id
JOIN release_component source_rc ON source_rc.release_id=q.release_id AND source_rc.layer='sources'
JOIN component_source cs ON cs.component_id=source_rc.component_id AND cs.source_id=src.source_id
WHERE q.query_id=:query_id
ORDER BY seg.segment_no,zone_id;
