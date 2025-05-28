-- 01_extract_points_window.sql
-- This script creates a table of road points within a given window.

-- We expect 6 parameters: minx, miny, maxx, maxy, crs, name_area

DROP TABLE IF EXISTS spatial_window_%(name_area)s;
DROP TABLE IF EXISTS road_points_window_%(name_area)s;
DROP TABLE IF EXISTS dtm_window_%(name_area)s;
DROP TABLE IF EXISTS filtered_roads_%(name_area)s;

-- 1) Make a rectangular window
CREATE TEMPORARY TABLE spatial_window_%(name_area)s AS
SELECT ST_MakeEnvelope(
    %(minx)s, %(miny)s, %(maxx)s, %(maxy)s,
    %(crs)s
) AS geom;

-- 2) Create bounded DTM layer
CREATE TABLE dtm_window_%(name_area)s AS
SELECT 
    ST_Clip(d.rast, w.geom) as rast
FROM dtm d, spatial_window_%(name_area)s w
WHERE ST_Intersects(d.rast, w.geom);

-- Add raster constraints
SELECT AddRasterConstraints('public'::name, 'dtm_window_%(name_area)s'::name, 'rast'::name);

-- Create spatial index on the raster
CREATE INDEX dtm_window_%(name_area)s_rast_idx ON dtm_window_%(name_area)s USING gist(ST_ConvexHull(rast));

-- 3) Create a table of clipped roads to the spatial window
CREATE TABLE filtered_roads_%(name_area)s AS
SELECT 
    r.*,
    CASE 
        WHEN r.bridge = 'yes' THEN 'yes'
        WHEN r.other_tags LIKE '%%"bridge"=>"yes"%%' THEN 'yes'
        WHEN r.other_tags LIKE '%%"bridge"=>"viaduct"%%' THEN 'yes'
        WHEN r.other_tags LIKE '%%"bridge"=>"aqueduct"%%' THEN 'yes'
        ELSE 'no'
    END AS bridge_combined,
    CASE 
        WHEN r.tunnel = 'yes' THEN 'yes'
        WHEN r.other_tags LIKE '%%"tunnel"=>"yes"%%' THEN 'yes'
        WHEN r.other_tags LIKE '%%"tunnel"=>"building_passage"%%' THEN 'yes'
        WHEN r.other_tags LIKE '%%"tunnel"=>"passage"%%' THEN 'yes'
        ELSE 'no'
    END AS tunnel_combined
FROM roads r, spatial_window_%(name_area)s w
WHERE ST_Intersects(r.geom, w.geom)
AND r.highway IS NOT NULL;

-- 4) Create final table with segmented roads (inserting information at the end)
CREATE TABLE road_points_window_%(name_area)s (
  fid integer,
  seq integer,
  geom_utm geometry(Point, %(crs)s),
  point_status text,
  elevation double precision,
  segmented_points integer,
  bridge text,
  tunnel text,
  highway text
);

WITH 
-- 5) Create table with road lengths and segmentation distances in meters
road_lengths_table AS (
SELECT 
  fid, 
  geom,
  ST_Length(geom) AS length_m,
  CASE 
    WHEN ST_Length(geom) < 50 THEN 5
    WHEN ST_Length(geom) < 100 THEN 10
    ELSE 25
  END AS seg_distance,
  bridge_combined as bridge,
  tunnel_combined as tunnel,
  highway
FROM filtered_roads_%(name_area)s
),
-- 6) Create table with segmented roads (lenght is divided by seg_distance)
segmented_roads_table AS (
SELECT
  fid,
  ST_Segmentize(
      geom,
      seg_distance
  ) AS geom_segmented,
  seg_distance,
  ST_NPoints(
    ST_Segmentize(
      geom,
      seg_distance
    )
  ) AS segmented_points,
  bridge,
  tunnel,
  highway
FROM road_lengths_table
),
-- 7) Create table for each point product of segmented roads. CROSS JOIN LATERAL is used to create a row for each point in the segmented road.
pts_table AS (
SELECT
  sr.fid,
  (dp).path[2] AS seq,
  (dp).geom AS geom_utm,
  sr.seg_distance,
  sr.segmented_points,
  sr.bridge,
  sr.tunnel,
  sr.highway
FROM segmented_roads_table sr
CROSS JOIN LATERAL ST_DumpPoints(sr.geom_segmented) AS dp
)
-- 8) Create the final road_points_window table
INSERT INTO road_points_window_%(name_area)s
SELECT 
  p.fid,
  p.seq,
  p.geom_utm,
  CASE 
    WHEN ST_Value(dtm_window_%(name_area)s.rast, p.geom_utm) IS NULL THEN 'null_elevation'
    ELSE 'valid'
  END AS point_status,
  ST_Value(dtm_window_%(name_area)s.rast, p.geom_utm)::double precision AS elevation,
  p.segmented_points,
  p.bridge,
  p.tunnel,
  p.highway
FROM pts_table p
JOIN spatial_window_%(name_area)s w ON ST_Intersects(p.geom_utm, w.geom)
LEFT JOIN dtm_window_%(name_area)s ON ST_Intersects(p.geom_utm, dtm_window_%(name_area)s.rast);

-- Create spatial index on the debug table
CREATE INDEX road_points_window_%(name_area)s_geom_idx ON road_points_window_%(name_area)s USING GIST(geom_utm);

