import streamlit as st
import folium
from streamlit_folium import folium_static
import pandas as pd
import geopandas as gpd
from sqlalchemy import create_engine, text
import json
from branca.colormap import LinearColormap
from shapely.geometry import shape
import pyproj
import os
import sys
import matplotlib.pyplot as plt

# Add the project root to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))  # web-app directory
project_root = os.path.dirname(current_dir)  # wuppertal-road-slope directory
sys.path.append(project_root)

# Now we can import from project root
from config import CONFIG, REGION_PARAMS, get_region_params
from scripts.bbox_selector import get_dtm_extent

# Page config
st.set_page_config(
    page_title=f"Road Slopes Analysis",
    layout="wide",
    initial_sidebar_state="collapsed"  # Hide sidebar by default
)

# Get the current region from config
region = CONFIG["region"]

# Database configuration
DB_CONNECTION = f"postgresql://{CONFIG['db_connection']['user']}:{CONFIG['db_connection']['password']}@{CONFIG['db_connection']['host']}/{CONFIG['database']}"
engine = create_engine(DB_CONNECTION)

# Custom CSS to make the layout more compact but with larger fonts
#st.markdown("""
#<style>
#    .block-container {
#        padding-top: 1rem;
#        padding-bottom: 0rem;
#        padding-left: 1rem;
#        padding-right: 1rem;
#    }
#    .element-container {
#        margin-bottom: 0.5rem;
#    }
#    .stMarkdown {
#        margin-bottom: 0.5rem;
#    }
#    div[data-testid="stMetricValue"] {
#        font-size: 1.2rem;
#    }
#    div[data-testid="stMetricLabel"] {
#        font-size: 1rem;
#    }
#    div.stMarkdown p {
#        font-size: 1.1rem;
#    }
#    h1 {
#        font-size: 2rem !important;
#    }
#    h2 {
#        font-size: 1.8rem !important;
#    }
#    h3 {
#        font-size: 1.6rem !important;
#    }
#    /* Custom styling for number inputs */
#    [data-testid="stTextInput"] {
#        width: 80px !important;
#        margin-right: 0.5rem !important;
#    }
#    /* Container for inputs to be side by side */
#    .slope-inputs {
#        display: flex;
#        align-items: center;
#        gap: 0.5rem;
#    }
#    /* Make figures container more compact */
#    [data-testid="column"] {
#        padding: 0rem !important;
#        margin: 0rem !important;
#    }
#    /* Adjust column spacing for statistics */
#    div[data-testid="column"] > div {
#        margin-right: -2rem;
#    }
#    /* Make map container larger */
#    .map-container {
#        flex: 4 !important;
#    }
#    .histogram-container {
#        flex: 1 !important;
#    }
#</style>
#""", unsafe_allow_html=True)

# Title and description - more compact
st.title(f'Road Slopes Analysis - Region "{region}"')
st.markdown("""
<div style="font-size: 1.5em">
Analysis of road slopes based on 1m resolution DTM. Color-coded segments show slope (%) distribution.
<br><br>
<b>Note:</b> Values greater than 15% are unrealistic for roads. High values indicate stairs or data artefacts (the analysis assumes that roads are not above ground).
</div>
""", unsafe_allow_html=True)

st.markdown("""
    <style>
    /* Increase font size for input labels and values */
    div[data-testid="stTextInput"] label {
        font-size: 1.5rem !important;
    }
    div[data-testid="stTextInput"] input {
        font-size: 1.5rem !important;
    }
    </style>
""", unsafe_allow_html=True)

# Function to get road data
def get_road_data(min_slope, max_slope):
    # Format the table name with the region
    table_name = f"road_segments_slope_{region}"
    
    # Modified query to reduce data and pre-calculate clusters for the map
    map_query = text(f"""
        WITH slope_ranges AS (
            SELECT 
                CASE
                    WHEN slope_pct <= 1 THEN 1
                    WHEN slope_pct <= 3 THEN 2
                    WHEN slope_pct <= 6 THEN 3
                    WHEN slope_pct <= 10 THEN 4
                    ELSE 5
                END AS slope_category,
                ST_Transform(segment_geom, {CONFIG['map_crs'].split(':')[1]}) as geom_wgs84
            FROM {table_name}
            WHERE slope_pct BETWEEN :min_slope AND :max_slope
            AND slope_pct IS NOT NULL
        ),
        clusters AS (
            SELECT 
                slope_category,
                ST_Collect(geom_wgs84) as geometry
            FROM slope_ranges
            GROUP BY slope_category
        )
        SELECT 
            slope_category,
            ST_AsGeoJSON(geometry) as geometry
        FROM clusters;
    """)
    
    # Separate query to get slope percentages for the histogram
    hist_query = text(f"""
        SELECT slope_pct
        FROM {table_name}
        WHERE slope_pct BETWEEN :min_slope AND :max_slope
        AND slope_pct IS NOT NULL;
    """)
    
    with engine.connect() as conn:
        # Get map data
        map_df = pd.read_sql(map_query, conn, params={"min_slope": min_slope, "max_slope": max_slope})
        # Get histogram data
        hist_df = pd.read_sql(hist_query, conn, params={"min_slope": min_slope, "max_slope": max_slope})
    
    # Convert geometry from GeoJSON string to GeoDataFrame
    map_df['geometry'] = map_df['geometry'].apply(lambda x: shape(json.loads(x)))
    
    # Create GeoDataFrame for map
    map_gdf = gpd.GeoDataFrame(map_df, geometry='geometry', crs=CONFIG['map_crs'])
    
    return map_gdf, hist_df

# Function to get color based on slope category
def get_color(category):
    color_map = {
        1: '#00ff00',  # Flat (0-1%)
        2: '#ffff00',  # Gentle (1-3%)
        3: '#ffa500',  # Moderate (3-6%)
        4: '#982d80',  # Steep (6-10%)
        5: '#ff0000'   # Very Steep (>10%)
    }
    return color_map.get(category, '#gray')

# Function to get statistics
def get_stats():
    # Format the table name with the region
    table_name = f"road_segments_slope_{region}"
    
    query = text(f"""
        SELECT 
            MIN(slope_pct) as min_slope,
            MAX(slope_pct) as max_slope,
            AVG(slope_pct) as avg_slope,
            COUNT(*) as total_segments,
            COUNT(DISTINCT fid) as total_roads
        FROM {table_name}
        WHERE slope_pct IS NOT NULL
    """)
    
    with engine.connect() as conn:
        return pd.read_sql(query, conn).iloc[0]

# Get initial statistics for reference values
initial_stats = get_stats()

# Create columns with adjusted ratios for better fit
col1, col2, col3 = st.columns([2, 0.9, 1])  # Make the main column wider

with col2:
    # Add legend with more compact styling
    st.markdown("""
        <div style="display: flex; gap: 0rem; margin: 0rem; padding: 0rem;">
            <div style="flex: 4; margin-right: 1rem;">
    """, unsafe_allow_html=True)
    st.subheader("Legend")
    legend_data = {
        "Flat (0-1%)": "#00ff00",
        "Gentle (1-3%)": "#ffff00",
        "Moderate (3-6%)": "#ffa500",
        "Steep (6-10%)": "#982d80",
        "Very Steep (>10%)": "#ff0000"
    }
    
    for label, color in legend_data.items():
        st.markdown(
            f'<div style="display: flex; align-items: center; margin-bottom: 0.3rem;">'
            f'<div style="width: 20px; height: 20px; background-color: {color}; '
            f'margin-right: 10px; border: 1px solid #ccc;"></div>'
            f'<span style="font-size: 1.3em">{label}</span></div>',
            unsafe_allow_html=True
        )

    # Add vertical space
    st.markdown('<div style="margin: 3rem 0;"></div>', unsafe_allow_html=True)
    
    st.markdown("### Filters")
    col_min, col_max, col_extra = st.columns([1, 1, 2])
    with col_min:
        st.markdown('<div style="font-size: 2em;">', unsafe_allow_html=True)
        min_slope_str = st.text_input(
            "Min %",
            value=f"{float(initial_stats['min_slope']):.1f}",
            key="min_slope"
        )
        st.markdown('</div>', unsafe_allow_html=True)
    with col_max:
        # Get the initial max slope, but cap it at 40%
        initial_max = min(float(initial_stats['max_slope']), 40.0)
        st.markdown('<div style="font-size: 2em;">', unsafe_allow_html=True)
        max_slope_str = st.text_input(
            "Max %",
            value=f"{initial_max:.1f}",
            key="max_slope"
        )
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Convert inputs to float with validation
    try:
        min_slope = float(min_slope_str)
        max_slope = float(max_slope_str)
        # Enforce maximum slope limit
        max_slope = min(max_slope, 40.0)
        if min_slope > max_slope:
            st.error("Min slope > Max slope")
            min_slope = float(initial_stats['min_slope'])
            max_slope = min(float(initial_stats['max_slope']), 40.0)
    except ValueError:
        st.error("Invalid numbers")
        min_slope = float(initial_stats['min_slope'])
        max_slope = min(float(initial_stats['max_slope']), 40.0)
    
    # Get filtered statistics
    table_name = f"road_segments_slope_{region}"
    filtered_query = text(f"""
        SELECT 
            COUNT(*) as total_segments,
            COUNT(DISTINCT fid) as total_roads,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY slope_pct) as median_slope,
            MAX(slope_pct) as max_slope
        FROM {table_name}
        WHERE slope_pct BETWEEN :min_slope AND :max_slope
        AND slope_pct IS NOT NULL
    """)
    
    with engine.connect() as conn:
        filtered_stats = pd.read_sql(
            filtered_query, 
            conn, 
            params={"min_slope": min_slope, "max_slope": max_slope}
        ).iloc[0]

    # Display statistics in a more compact way
    st.markdown('<div style="margin: 3rem 0;"></div>', unsafe_allow_html=True)
    st.markdown("### Statistics")
    
    col2_stats1, col2_stats2 = st.columns([1, 1])
    with col2_stats1:
        st.metric("Segments", f"{filtered_stats['total_segments']:,}")
        st.metric("Roads", f"{filtered_stats['total_roads']:,}")
    with col2_stats2:
        st.metric("Median slope", f"{filtered_stats['median_slope']:.1f}%")
        st.metric("Max. slope", f"{filtered_stats['max_slope']:.1f}%")
        
with col1:
    # Show loading indicator while getting data
    with st.spinner('Loading data...'):
        map_gdf, hist_df = get_road_data(min_slope, max_slope)
    
    # Create the map
    dtm_extent = get_dtm_extent()
    center_x = (dtm_extent.bounds[0] + dtm_extent.bounds[2]) / 2
    center_y = (dtm_extent.bounds[1] + dtm_extent.bounds[3]) / 2
    
    transformer = pyproj.Transformer.from_crs(CONFIG['dtm_crs'], CONFIG['map_crs'], always_xy=True)
    center_lon, center_lat = transformer.transform(center_x, center_y)
    m = folium.Map(
        location=[center_lat, center_lon],  
        zoom_start=12,
        tiles='OpenStreetMap',
    )
    
    # Add road segments to map with thicker lines
    for _, row in map_gdf.iterrows():
        folium.GeoJson(
            row['geometry'],
            style_function=lambda x, cat=row['slope_category']: {
                'color': get_color(cat),
                'weight': 4,
                'opacity': 0.8
            }
        ).add_to(m)
    
    # Create a container div with custom styling
    st.markdown("""
        <div style="display: flex; gap: 0rem; margin: 0rem; padding: 0rem;">
            <div style="flex: 4; margin-right: 1rem;">
    """, unsafe_allow_html=True)
    
    # Map
    st.subheader(f"Road Segments ({min_slope:.1f}% - {max_slope:.1f}%)")
    folium_static(m, width=1300, height=1000)
    
    st.markdown('</div><div style="flex: 1; max-width: 300px;">', unsafe_allow_html=True)
    
with col3:
    # Histogram with dark background
    if not hist_df.empty:
        st.markdown("""
        <div style="display: flex; gap: 0rem; margin: 0rem; padding: 0rem;">
            <div style="flex: 4; margin-right: 1rem;">
        """, unsafe_allow_html=True)
        st.subheader("Slope Distribution")
        plt.style.use('dark_background')
        fig, ax = plt.subplots(figsize=(4, 3), constrained_layout=True)
        fig.patch.set_facecolor('#0E1117')  # Match Streamlit's dark theme
        ax.set_facecolor('#0E1117')
        
        # Create histogram with custom colors
        ax.hist(hist_df['slope_pct'], bins=20, edgecolor='#666666', color='#4A5460')
        ax.set_xlabel('Slope (%)', fontsize=10, color='white')
        ax.set_ylabel('Segment count', fontsize=10, color='white')
        ax.tick_params(axis='both', which='major', labelsize=8, colors='white')
        ax.spines['bottom'].set_color('#666666')
        ax.spines['left'].set_color('#666666')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.set_xlim(min_slope, max_slope + 1)
        
        plt.tight_layout()
        st.pyplot(fig, use_container_width=False)
        plt.close()
        plt.style.use('default')  # Reset to default style