#!/bin/bash
# Road Slope Analysis - Data Loading Script
# This script loads DTM and road data into the PostgreSQL database

DB_NAME=$(python3 -c "from config import CONFIG; print(CONFIG['database'])")
DB_USER=$(python3 -c "from config import CONFIG; print(CONFIG['db_connection']['user'])")
DB_PASSWORD=$(python3 -c "from config import CONFIG; print(CONFIG['db_connection']['password'])")
DB_HOST=$(python3 -c "from config import CONFIG; print(CONFIG['db_connection']['host'])")
TARGET_SRID=$(python3 -c "from config import CONFIG; print(CONFIG['dtm_crs'].split(':')[1])")

# See README in data folder for more details about downloading the data
# Default values
DTM_FILE="data/dtm.tif"
ROADS_FILE="data/roads.gpkg"
TILE_SIZE="500x500"
TILES_PATH=""
# Flags to track what should be loaded
LOAD_DTM=false
LOAD_ROADS=false

# Function to display usage information
show_usage() {
  echo -e "Usage: $0 [options]"
  echo -e "Options:"
  echo -e "  -d, --dtm FILE         Path to unified DTM file (default: wuppertal_dtm_test.tif)"
  echo -e "  -r, --roads FILE       Path to roads GeoPackage (default: roads.gpkg)"
  echo -e "  -t, --tile-size SIZE   Tile size for raster import (default: 500x500)"
  echo -e "  -s, --srid EPSG        Target SRID/EPSG code (default: $TARGET_SRID)"
  echo -e "  -p, --tiles-path PATH  Path to DTM tiles (if creating unified DTM)"
  echo -e "  -do, --dtm-only        Load only DTM"
  echo -e "  -ro, --roads-only      Load only roads"
  echo -e "  -h, --help             Show this help message"
  echo -e "\nExample:"
  echo -e "  $0 -d my_dtm.tif -r my_roads.gpkg -s $TARGET_SRID"
}

# Function to resolve relative paths
resolve_path() {
    local path=$1
    local script_dir=$(dirname "$(readlink -f "$0")")
    
    # If path is relative, make it relative to script directory
    if [[ ! "$path" = /* ]]; then
        path="$script_dir/$path"
    fi
    
    echo "$path"
}

# Function to get CRS and check if it's metric
get_and_check_crs() {
    local input_file=$1
    local file_type=$2  # 'raster' or 'vector'
    
    # First check if file exists
    if [ ! -f "$input_file" ]; then
        echo "ERROR: File not found: $input_file"
        return 1
    fi
    
    if [ "$file_type" = "raster" ]; then
        # Try multiple methods to get the EPSG code
        # Method 1: Look for ID["EPSG"] tag at the end of the CRS definition
        current_srid=$(gdalinfo "$input_file" | grep -A 50 "Coordinate System is:" | grep 'ID["EPSG",' | tail -n 1 | grep -o '[0-9]*')
        
        # Method 2: Parse from PROJCRS name if it contains the UTM zone
        if [ -z "$current_srid" ]; then
            local utm_zone=$(gdalinfo "$input_file" | grep "PROJCRS" | grep -o "UTM zone.*N" | grep -o "32")
            if [ ! -z "$utm_zone" ]; then
                current_srid="258${utm_zone}"  # Convert UTM zone to EPSG code for ETRS89
            fi
        fi
    else
        # For vector data, try multiple methods to get the correct CRS
        # Method 1: Try to get the SRID directly from the geometry
        current_srid=$(ogrinfo -so -al "$input_file" | grep -i "PROJCRS\|PROJECTED CRS" | grep -o "ID\[\"EPSG\",\"[0-9]*\"\]" | grep -o '[0-9]*' | head -n 1)
        
        # Method 2: If that didn't work, try getting it from the authority code
        if [ -z "$current_srid" ]; then
            current_srid=$(ogrinfo -so -al "$input_file" | grep -i "AUTHORITY" | grep "EPSG" | tail -n 1 | grep -o '[0-9]*')
        fi
        
        # Method 3: If still no result, try parsing from the full CRS name for UTM zones
        if [ -z "$current_srid" ]; then
            utm_info=$(ogrinfo -so -al "$input_file" | grep -i "UTM zone 32N")
            if [ ! -z "$utm_info" ]; then
                current_srid="25832"  # ETRS89 / UTM zone 32N
            fi
        fi
    fi
    
    if [ -z "$current_srid" ]; then
        echo "ERROR: Could not determine CRS of $input_file"
        echo "Debug info:"
        echo "File type: $file_type"
        if [ "$file_type" = "raster" ]; then
            gdalinfo "$input_file" | grep -A 5 "Coordinate System"
        else
            echo "Layer info:"
            ogrinfo -so -al "$input_file"
        fi
        return 1
    fi

    # Return the SRID
    echo "$current_srid"
    return 0
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    -d|--dtm)
      DTM_FILE="$2"
      shift 2
      ;;
    -r|--roads)
      ROADS_FILE="$2"
      shift 2
      ;;
    -t|--tile-size)
      TILE_SIZE="$2"
      shift 2
      ;;
    -s|--srid)
      TARGET_SRID="$2"
      shift 2
      ;;
    -p|--tiles-path)
      TILES_PATH="$2"
      shift 2
      ;;
    -do|--dtm-only)
      LOAD_DTM=true
      LOAD_ROADS=false
      shift 1
      ;;
    -ro|--roads-only)
      LOAD_DTM=false
      LOAD_ROADS=true
      shift 1
      ;;  
    -h|--help)
      show_usage
      exit 0
      ;;
    *)
      echo -e "${RED}Unknown option: $1${NC}"
      show_usage
      exit 1
      ;;
  esac
done

# If no specific load flags are set, load both by default
if [ "$LOAD_DTM" = false ] && [ "$LOAD_ROADS" = false ]; then
    LOAD_DTM=true
    LOAD_ROADS=true
fi

# Resolve paths
if [ ! -z "$DTM_FILE" ]; then
    DTM_FILE=$(resolve_path "$DTM_FILE")
fi

if [ ! -z "$ROADS_FILE" ]; then
    ROADS_FILE=$(resolve_path "$ROADS_FILE")
fi

if [ ! -z "$TILES_PATH" ]; then
    TILES_PATH=$(resolve_path "$TILES_PATH")
fi

echo "Using paths:"
[ ! -z "$DTM_FILE" ] && echo "DTM file: $DTM_FILE"
[ ! -z "$ROADS_FILE" ] && echo "Roads file: $ROADS_FILE"
[ ! -z "$TILES_PATH" ] && echo "Tiles path: $TILES_PATH"

echo -e "Starting data loading process for database: $DB_NAME"
echo "Target CRS: EPSG:$TARGET_SRID"

if [ "$LOAD_DTM" = true ]; then
    # Drop existing DTM table if it exists
    echo "Dropping existing DTM table if it exists..."
    PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -U $DB_USER -d "$DB_NAME" -c "DROP TABLE IF EXISTS public.dtm CASCADE;"

    dtm_srid=""
    if [[ ! -z "$TILES_PATH" ]]; then
        # Check CRS of first tile
        first_tile=$(ls "$TILES_PATH"/*.tif | head -n 1)
        if [ ! -f "$first_tile" ]; then
            echo "Error: No .tif files found in $TILES_PATH"
            exit 1
        fi

        dtm_srid=$(get_and_check_crs "$first_tile" "raster")
        check_result=$?
        if [ $check_result -ne 0 ]; then
            echo "Error: Failed to determine CRS of DTM tiles"
            exit 1
        fi
        echo "DTM CRS detected: EPSG:$dtm_srid"
        
        # Create output directory if needed
        output_dir=$(dirname "$DTM_FILE")
        if [ ! -d "$output_dir" ] && [ "$output_dir" != "." ]; then
            mkdir -p "$output_dir"
        fi

        echo "Step 1: Creating virtual dataset (VRT) from tiles..."
        gdalbuildvrt merged_dtm.vrt "$TILES_PATH"/*.tif
        
        if [[ $? -ne 0 ]]; then
            echo "Error creating VRT from tiles"
            exit 1
        fi
        
        echo "Step 2: Converting VRT to GeoTIFF with target CRS (EPSG:$TARGET_SRID)..."
        gdal_translate -of GTiff -co "COMPRESS=LZW" -co "TILED=YES" \
            -a_srs "EPSG:$dtm_srid" merged_dtm.vrt temp_dtm.tif
        gdalwarp -t_srs "EPSG:$TARGET_SRID" -r bilinear \
            -co "COMPRESS=LZW" -co "TILED=YES" temp_dtm.tif "$DTM_FILE"
        
        if [[ $? -ne 0 ]]; then
            echo "Error creating GeoTIFF from VRT"
            rm -f merged_dtm.vrt temp_dtm.tif
            exit 1
        fi
        
        rm -f merged_dtm.vrt temp_dtm.tif
        echo "Unified DTM created: $DTM_FILE"

        # Verify the created file exists and is readable
        if [ ! -f "$DTM_FILE" ]; then
            echo "Error: Failed to create DTM file"
            exit 1
        fi
    else
        if [ ! -f "$DTM_FILE" ]; then
            echo "Error: DTM file '$DTM_FILE' not found"
            exit 1
        fi
        
        dtm_srid=$(get_and_check_crs "$DTM_FILE" "raster")
        check_result=$?
        if [ $check_result -ne 0 ]; then
            echo "Error: Failed to determine CRS of DTM file"
            exit 1
        fi
        echo "DTM CRS detected: EPSG:$dtm_srid"

        # Convert DTM to target CRS if needed
        if [ "$dtm_srid" != "$TARGET_SRID" ]; then
            echo "Converting DTM to target CRS (EPSG:$TARGET_SRID)..."
            mv "$DTM_FILE" "original_$DTM_FILE"
            gdalwarp -t_srs "EPSG:$TARGET_SRID" -r bilinear \
                -co "COMPRESS=LZW" -co "TILED=YES" \
                "original_$DTM_FILE" "$DTM_FILE"
            if [[ $? -ne 0 ]]; then
                echo "Error converting DTM to target CRS"
                mv "original_$DTM_FILE" "$DTM_FILE"
                exit 1
            fi
            rm "original_$DTM_FILE"
        fi
    fi

    # Load DTM raster to the database
    echo "Loading DTM raster into database..."
    echo "This may take some time depending on the size of your DTM file."

    # Create a temporary SQL file for the raster import
    TMPFILE=$(mktemp)
    raster2pgsql -s $TARGET_SRID -C -I -M -F -t $TILE_SIZE "$DTM_FILE" public.dtm > "$TMPFILE"

    if [[ $? -ne 0 ]]; then
        echo "Error: Failed to create SQL for DTM import"
        rm -f "$TMPFILE"
        exit 1
    fi

    # Import the raster
    PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -U $DB_USER -d "$DB_NAME" -f "$TMPFILE" 2>&1 | tee import.log
    
    if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
        echo "Error: Failed to load DTM into database"
        rm -f "$TMPFILE"
        exit 1
    fi

    # Check if the table was actually created and has data
    table_check=$(PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -U $DB_USER -d "$DB_NAME" -tAc "SELECT COUNT(*) FROM public.dtm")
    if [[ $? -ne 0 ]] || [[ $table_check -eq 0 ]]; then
        echo "Error: DTM table is empty or was not created"
        rm -f "$TMPFILE"
        exit 1
    fi

    rm -f "$TMPFILE"
    echo "DTM loaded successfully into table 'public.dtm'"
fi

if [ "$LOAD_ROADS" = true ]; then
    if [ ! -f "$ROADS_FILE" ]; then
        echo -e "Error: Roads file '$ROADS_FILE' not found"
        exit 1
    fi

    roads_srid=$(get_and_check_crs "$ROADS_FILE" "vector")
    if [ $? -ne 0 ]; then
        echo "Error: Please ensure roads data is in a metric coordinate system"
        exit 1
    fi
    echo "Roads CRS detected: EPSG:$roads_srid"

    # Convert roads to target CRS if needed
    if [ "$roads_srid" != "$TARGET_SRID" ]; then
        echo "Converting roads to target CRS (EPSG:$TARGET_SRID)..."
        mv "$ROADS_FILE" "original_$ROADS_FILE"
        ogr2ogr -f "GPKG" -t_srs "EPSG:$TARGET_SRID" \
            "$ROADS_FILE" "original_$ROADS_FILE"
        if [[ $? -ne 0 ]]; then
            echo "Error converting roads to target CRS"
            mv "original_$ROADS_FILE" "$ROADS_FILE"
            exit 1
        fi
        rm "original_$ROADS_FILE"
    fi

    # Load the roads to the database
    echo -e "Loading roads from GeoPackage..."
    
    PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -U $DB_USER -d "$DB_NAME" -c "DROP TABLE IF EXISTS public.roads CASCADE;"
    
    PGPASSWORD=$DB_PASSWORD ogr2ogr -f "PostgreSQL" \
            PG:"dbname=$DB_NAME host=$DB_HOST user=$DB_USER password=$DB_PASSWORD" \
            "$ROADS_FILE" \
            -nln public.roads \
            -nlt PROMOTE_TO_MULTI \
            -lco GEOMETRY_NAME=geom

    if [[ $? -ne 0 ]]; then
        echo -e "Error loading roads into database"
        exit 1
    fi

    echo -e "Roads loaded successfully into table 'public.roads'"
fi

if [ "$LOAD_DTM" = true ] || [ "$LOAD_ROADS" = true ]; then
    echo "You can now proceed with the slope analysis."
fi
