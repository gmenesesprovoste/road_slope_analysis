-- 02_create_segment_slopes_table.sql
-- this script creates a table with slope values for each road segment

DROP TABLE IF EXISTS road_segments_slope_%(name_area)s;

CREATE TABLE road_segments_slope_%(name_area)s AS
WITH
valid_points AS (
  -- Select only points with valid elevations
  SELECT
    p.fid,
    p.seq,
    p.geom_utm,
    p.elevation,
    (p.segmented_points - 1)::integer AS n_segments,
    COALESCE(p.bridge, 'no') AS bridge,
    COALESCE(p.tunnel, 'no') AS tunnel,
    p.highway
  FROM road_points_window_%(name_area)s p
  WHERE p.point_status = 'valid'  -- Only include points with valid elevation
  ORDER BY p.fid, p.seq  -- Ensure proper sequencing
),
consecutive_points AS (
  -- Create pairs of consecutive valid points
  SELECT 
    p1.fid,
    p1.seq AS seq_start,
    p2.seq AS seq_end,
    p1.elevation AS elev_start,
    p2.elevation AS elev_end,
    p1.geom_utm AS geom_start,
    p2.geom_utm AS geom_end,
    ST_MakeLine(p1.geom_utm, p2.geom_utm) AS segment_geom,
    ST_Distance(p1.geom_utm, p2.geom_utm) AS segment_length,
    p1.bridge,
    p1.tunnel,
    p1.highway
  FROM valid_points p1
  JOIN valid_points p2 
    ON p1.fid = p2.fid 
    AND p2.seq = p1.seq + 1  -- Connect to the next sequential point
)
SELECT 
  fid,
  ROW_NUMBER() OVER(PARTITION BY fid ORDER BY seq_start) AS segment_id,
  seq_start,
  seq_end,
  segment_length,
  elev_start,
  elev_end,
  ABS(elev_end - elev_start) AS elevation_change,
  CASE 
    WHEN bridge = 'yes' THEN NULL  -- Exclude bridges
    WHEN tunnel = 'yes' THEN NULL  -- Exclude tunnels
    WHEN segment_length = 0 THEN NULL  -- Avoid division by zero
    ELSE ABS(elev_end - elev_start) / segment_length * 100.0
  END AS slope_pct,
  CASE
    WHEN elev_end > elev_start THEN 'uphill_along_road_direction'
    WHEN elev_end < elev_start THEN 'downhill_along_road_direction'
    ELSE 'flat'
  END AS direction,
  segment_geom,
  bridge,
  tunnel,
  highway
FROM consecutive_points
WHERE segment_length > 0;  -- Exclude zero-length segments

-- Create spatial index
CREATE INDEX road_segments_slope_%(name_area)s_geom_idx ON road_segments_slope_%(name_area)s USING GIST(segment_geom);
