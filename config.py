"""Configuration parameters for the road slope analysis project."""
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Determine if we're running in Docker
IN_DOCKER = os.getenv('IN_DOCKER', 'false').lower() == 'true'

CONFIG = {
    "database": os.getenv("DB_NAME", "road_slopes"),
    "region": "wuppertal_center",
    "dtm_crs": "EPSG:25832",    # UTM Zone 32N - our primary CRS for all calculations
    "map_crs": "EPSG:4326",     # WGS84 - only used for web map display
    "db_connection": {
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", "postgres"),
        # Use 'db' for Docker, 'localhost' for native
        "host": os.getenv("DB_HOST", "db" if IN_DOCKER else "localhost")
    }
}

# Default bounding box parameters for the region
REGION_PARAMS = {
    "wuppertal_east": {
        "minx": 372887.291,
        "miny": 5673639.129,
        "maxx": 381263.991,
        "maxy": 5680948.462,
        "crs": 25832
    }
}
REGION_PARAMS.update({
    "koeln_center": {
        "minx": 352218.5014303498,
        "miny": 5639892.920625344,
        "maxx": 366761.715006059,
        "maxy": 5649224.69687352,
        "crs": 25832
    }
})

REGION_PARAMS.update({
    "wuppertal_elberfeld": {
        "minx": 369943.2521041449,
        "miny": 5679155.476870068,
        "maxx": 374403.90064715076,
        "maxy": 5681661.825148035,
        "crs": 25832
    }
})
REGION_PARAMS.update({
    "wuppertal_center": {
        "minx": 369233.9560975032,
        "miny": 5678133.279248141,
        "maxx": 375710.4075746999,
        "maxy": 5682179.590222261,
        "crs": 25832
    }
})
def get_region_params(region_name=None):
    """Get parameters for a specific region or the default region."""
    if region_name is None:
        region_name = CONFIG["region"]
    params = REGION_PARAMS.get(region_name)
    if params:
        # Add the region name to the parameters
        return {**params, "name_area": region_name}
    return None 