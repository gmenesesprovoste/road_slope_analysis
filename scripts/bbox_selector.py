#!/usr/bin/env python3

import streamlit as st
from streamlit_folium import st_folium
import folium
from folium.plugins import Draw
import geopandas as gpd
import psycopg2
from psycopg2.extras import RealDictCursor
import pyproj
from shapely.geometry import box
import json
import sys
from os.path import dirname, abspath
import traceback

# Add the project root directory to Python path
project_root = dirname(dirname(abspath(__file__)))
sys.path.insert(0, project_root)

from config import CONFIG

# Maximum allowed area in square kilometers
MAX_AREA_KM2 = 50.0  # Adjust this value based on your needs

def get_db_connection():
    """Create and return a database connection with error handling."""
    try:
        conn = psycopg2.connect(
            dbname=CONFIG["database"],
            **CONFIG["db_connection"]
        )
        return conn
    except psycopg2.Error as e:
        st.error(f"Failed to connect to database: {str(e)}")
        return None

def get_dtm_extent(database=CONFIG["database"]):
    """Get the extent of the DTM from the database in UTM Zone 32N coordinates."""
    conn = get_db_connection()
    if not conn:
        return None
    
    try:
        query = """
        SELECT ST_Extent(ST_Envelope(rast)) as extent
        FROM dtm;
        """
        
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query)
                result = cur.fetchone()
                
        if not result or not result['extent']:
            st.warning("No DTM data found in the database.")
            return None
                
        # Parse the extent string 'BOX(minx maxy, maxx maxy)'
        extent_str = result['extent']
        extent_str = extent_str.replace('BOX(', '').replace(')', '')
        try:
            (minx, miny), (maxx, maxy) = [
                map(float, point.split()) 
                for point in extent_str.split(',')
            ]
            return box(minx, miny, maxx, maxy)
        except (ValueError, IndexError) as e:
            st.error(f"Failed to parse DTM extent: {str(e)}")
            return None
    except psycopg2.Error as e:
        st.error(f"Database error while fetching DTM extent: {str(e)}")
        return None
    finally:
        conn.close()

def get_dtm_coverage():
    """Get DTM coverage from database and transform to WGS84 for map display."""
    conn = get_db_connection()
    if not conn:
        return None
    
    try:
        query = f"""
        WITH valid_areas AS (
            SELECT ST_Transform(ST_Union(ST_Envelope(rast)), {CONFIG['map_crs'].split(':')[1]}) as geom
            FROM dtm
            WHERE NOT ST_BandIsNoData(rast)
        )
        SELECT ST_AsGeoJSON(geom) as geojson FROM valid_areas;
        """
        
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query)
                result = cur.fetchone()
                
        if result and result['geojson']:
            return json.loads(result['geojson'])
        st.warning("No valid DTM coverage found.")
        return None
    except psycopg2.Error as e:
        st.error(f"Database error while fetching DTM coverage: {str(e)}")
        return None
    except json.JSONDecodeError as e:
        st.error(f"Failed to parse DTM coverage GeoJSON: {str(e)}")
        return None
    finally:
        conn.close()

def transform_coordinates(coords, from_crs, to_crs):
    """Transform coordinates between CRS with error handling."""
    try:
        transformer = pyproj.Transformer.from_crs(from_crs, to_crs, always_xy=True)
        return transformer.transform(*coords)
    except Exception as e:
        st.error(f"Coordinate transformation error: {str(e)}")
        return None

def calculate_area_km2(minx, miny, maxx, maxy):
    """Calculate area in square kilometers."""
    try:
        width_m = maxx - minx
        height_m = maxy - miny
        area_m2 = width_m * height_m
        return area_m2 / 1_000_000  # Convert to km²
    except Exception as e:
        st.error(f"Error calculating area: {str(e)}")
        return None

def main():
    st.set_page_config(page_title="Area Selector", layout="wide")
    
    st.title("Area Selector")
    st.write("Draw a rectangle to select your area of interest.")
    st.write(f"⚠️ Maximum allowed area: {MAX_AREA_KM2:.1f} km²")
    st.write(f"ℹ️ The purple shaded area shows where DTM data is available")
    
    # Get DTM extent in UTM coordinates
    dtm_extent = get_dtm_extent()
    if dtm_extent is None:
        st.error("Could not load DTM extent. Please check database connection and try again.")
        return
        
    city_bounds = gpd.GeoDataFrame(
        geometry=[dtm_extent],
        crs=CONFIG['dtm_crs']
    )
    
    # Convert to WGS84 only for web map display
    try:
        city_bounds_wgs84 = city_bounds.to_crs(CONFIG['map_crs'])
    except Exception as e:
        st.error(f"Failed to transform city bounds to WGS84: {str(e)}")
        return
    
    # Calculate center coordinates in UTM first
    center_utm_y = city_bounds.geometry.centroid.y.mean()
    center_utm_x = city_bounds.geometry.centroid.x.mean()
    
    # Convert center to WGS84 for map display
    center_coords = transform_coordinates(
        (center_utm_x, center_utm_y),
        CONFIG['dtm_crs'],
        CONFIG['map_crs']
    )
    if center_coords is None:
        st.error("Failed to calculate map center coordinates.")
        return
    center_lon, center_lat = center_coords
    
    # Create three columns
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        # Display instructions
        st.write("1. Enter a name for the area of interest")
        st.write("2. Use the rectangle tool (square icon) to draw your selection")
        st.write("3. Draw a rectangle (within the purple boundary if a full road data coverage is required)")
        
        # Create the map
        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=12,
            tiles='OpenStreetMap'
        )
        
        # Add DTM coverage
        dtm_coverage = get_dtm_coverage()
        if dtm_coverage:
            folium.GeoJson(
                dtm_coverage,
                name='DTM Coverage',
                style_function=lambda x: {
                    'fillColor': 'purple',
                    'color': 'none',
                    'fillOpacity': 0.2
                }
            ).add_to(m)
        
        # Add the city boundary
        folium.GeoJson(
            city_bounds_wgs84.__geo_interface__,
            name='DTM Extent',
            style_function=lambda x: {
                'color': 'purple',
                'fillColor': 'none',
                'weight': 2
            }
        ).add_to(m)
        
        # Add drawing controls
        draw = Draw(
            draw_options={
                'polyline': False,
                'polygon': False,
                'circle': False,
                'marker': False,
                'circlemarker': False,
                'rectangle': True
            },
            edit_options={'edit': False}
        )
        m.add_child(draw)
        
        # Add layer control
        folium.LayerControl().add_to(m)
        
        # Get the drawn features using st_folium
        output = st_folium(m, width=800)
    
    with col2:
        # Area name input with validation
        area_name = st.text_input(
            "Area name (use underscores instead of spaces):",
            "my_area",
            help="Only use letters, numbers, and underscores"
        )
        
        if not area_name.replace('_', '').isalnum():
            st.error("Area name can only contain letters, numbers, and underscores")
            return
        
        # Process drawn features
        if (output is not None and isinstance(output, dict) and 
            "last_active_drawing" in output and 
            output["last_active_drawing"] and 
            output["last_active_drawing"].get('geometry', {}).get('type') == 'Polygon'):
            
            # Get the drawn feature
            last_feature = output["last_active_drawing"]
            coords = last_feature['geometry']['coordinates'][0]
            
            # Display raw coordinates for debugging
            st.write("### Raw Coordinates")
            st.write(f"Rectangle corners (lon, lat) in {CONFIG['map_crs']}:")
            for i, coord in enumerate(coords[:-1]):  # Skip last point as it's same as first
                st.write(f"Corner {i+1}: {coord}")
            
            # Get the bounding box in WGS84
            lons = [coord[0] for coord in coords]
            lats = [coord[1] for coord in coords]
            sw_lon, ne_lon = min(lons), max(lons)
            sw_lat, ne_lat = min(lats), max(lats)
            
            # Convert coordinates from WGS84 to UTM Zone 32N
            sw_coords = transform_coordinates(
                (sw_lon, sw_lat),
                CONFIG['map_crs'],
                CONFIG['dtm_crs']
            )
            ne_coords = transform_coordinates(
                (ne_lon, ne_lat),
                CONFIG['map_crs'],
                CONFIG['dtm_crs']
            )
            
            if sw_coords is None or ne_coords is None:
                st.error("Failed to transform coordinates. Please try again.")
                return
                
            sw_x, sw_y = sw_coords
            ne_x, ne_y = ne_coords
            
            # Calculate area in km²
            area_km2 = calculate_area_km2(sw_x, sw_y, ne_x, ne_y)
            if area_km2 is None:
                st.error("Failed to calculate area. Please try again.")
                return
                
            st.write(f"### Selected Area: {area_km2:.2f} km²")
            
            if area_km2 > MAX_AREA_KM2:
                st.error(f"⚠️ Selected area ({area_km2:.2f} km²) exceeds the maximum allowed size of {MAX_AREA_KM2:.1f} km²")
                st.write("Please draw a smaller rectangle")
            else:
                # Format the parameters dictionary to match config.py structure
                params = {
                    area_name: {
                        "minx": sw_x,
                        "miny": sw_y,
                        "maxx": ne_x,
                        "maxy": ne_y,
                        "crs": int(CONFIG['dtm_crs'].split(':')[1])
                    }
                }
                
                st.write("### Region Parameters")
                st.write("Add this to the REGION_PARAMS dictionary in config.py:")
                st.code(f"REGION_PARAMS.update({json.dumps(params, indent=4)})", language='python')
        else:
            st.write("⚠️ Please draw a rectangle on the map.")

if __name__ == "__main__":
    main() 