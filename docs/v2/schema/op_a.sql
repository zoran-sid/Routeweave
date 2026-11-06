-- 操作 A：查询任务窗口内、三维走廊内的有效空域限制（绑定一个发布）
-- 参数：:release_id；:win_lo、:win_hi（ISO UTC，半开区间）；
--       :x0, :x1, :y0, :y1, :z0, :z1（走廊包围盒，米，含边界）
-- 访问路径：四维 R*Tree（x, y, z, t）产生候选 → 基表列精确复核发布、状态、时间与空间。
-- CROSS JOIN 固定连接顺序：SQLite 规划器自选时会改由发布或时间 B-tree 驱动，
-- R*Tree 退化为逐行查找，实测更慢（docs/modules/yht/v2/experiments/）。
-- 结果为空时，服务层仍须检查 release_layer.complete 与覆盖瓦片，空结果不等于“安全”。
SELECT f.feature_id, ar.kind, ar.floor_z, ar.ceiling_m,
       ar.effective_lo, ar.effective_hi, ar.state, f.source_id, f.quality
FROM rtree_airspace AS r
CROSS JOIN airspace_restriction AS ar ON ar.rid = r.rid
CROSS JOIN feature AS f ON f.rid = ar.rid
WHERE r.max_x >= :x0 AND r.min_x <= :x1
  AND r.max_y >= :y0 AND r.min_y <= :y1
  AND r.max_z >= :z0 AND r.min_z <= :z1
  AND r.max_t >= unixepoch(:win_lo) - 1767225600
  AND r.min_t <= unixepoch(:win_hi) - 1767225600
  AND f.release_id = :release_id
  AND ar.state IN ('published', 'active')
  AND ar.effective_lo < :win_hi AND ar.effective_hi > :win_lo
  AND ar.bbox_max_x >= :x0 AND ar.bbox_min_x <= :x1
  AND ar.bbox_max_y >= :y0 AND ar.bbox_min_y <= :y1
  AND ar.forbid_hi_z >= :z0 AND ar.forbid_lo_z <= :z1
ORDER BY f.feature_id;
