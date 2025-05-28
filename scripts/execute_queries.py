import psycopg2
from pathlib import Path
import time
from datetime import datetime
import sys
from os.path import dirname, abspath

# Add the project root directory to Python path
project_root = dirname(dirname(abspath(__file__)))
sys.path.insert(0, project_root)

from config import CONFIG, get_region_params


SQL_DIR = Path(__file__).parent.parent / 'database' / 'queries'

def run_query(sqlfilename, params):
    start_time = time.time()
    print(f"\nStarting {sqlfilename} at {datetime.now().strftime('%H:%M:%S')} for database/region: {CONFIG['database']}/{CONFIG['region']}")
    sql = (SQL_DIR / f"{sqlfilename}.sql").read_text()
    
    # Create a copy of params for modification
    sql_params = params.copy()
    
    # Handle name_area parameter by cleaning it and doing direct string replacement
    if 'name_area' in sql_params:
        # Replace hyphens and spaces with underscores for table names
        area_name = sql_params['name_area'].replace('-', '_').replace(' ', '_')
        # Do direct string replacement for table names
        sql = sql.replace('%(name_area)s', area_name)
        # Remove name_area from params since we handled it directly
        del sql_params['name_area']
    
    # Debug prints
    #print("\nDEBUG INFO:")
    print(f"SQL parameters: {sql_params}")
    print(f"Area name: {area_name}")
    #print(f"SQL preview after name_area replacement: {sql[:500]}...")
    
    with psycopg2.connect(
        dbname=CONFIG['database'],
        **CONFIG['db_connection']
    ) as conn:
        with conn.cursor() as cur:
            try:
                # Create public schema if it doesn't exist and set search_path
                cur.execute("""
                    CREATE SCHEMA IF NOT EXISTS public;
                    SET search_path TO public;
                    SHOW search_path;
                """)
                search_path = cur.fetchone()
                #print(f"Current search_path: {search_path}")
                conn.commit()
                
                # Execute the main query with remaining parameters
                cur.execute(sql, sql_params)
                conn.commit()
            except Exception as e:
                print(f"Error executing query: {e}")
                print(f"SQL parameters: {sql_params}")
                print(f"SQL preview: {sql[:500]}...")  # Print first 500 chars of SQL
                conn.rollback()
                raise
    
    duration = time.time() - start_time
    print(f"{sqlfilename} complete in {duration:.2f} seconds")

if __name__ == '__main__':
    total_start = time.time()
    
    # Get parameters for the configured region
    params = get_region_params(CONFIG['region'])
    if params is None:
        print(f"Error: No parameters found for region '{CONFIG['region']}'")
        sys.exit(1)
    
    print(f"Using region parameters: {params}")
    
    run_query('01_extract_points_window', params)
    run_query('02_create_segment_slopes_table', params)

    total_time = time.time() - total_start
    print(f"\nTotal processing completed in {total_time:.2f} seconds")