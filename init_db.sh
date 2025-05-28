#!/bin/bash
# Database initialization script

# Get database name from config.py
DB_NAME=$(python3 -c "from config import CONFIG; print(CONFIG['database'])")
DB_USER=$(python3 -c "from config import CONFIG; print(CONFIG['db_connection']['user'])")
DB_PASSWORD=$(python3 -c "from config import CONFIG; print(CONFIG['db_connection']['password'])")
DB_HOST=$(python3 -c "from config import CONFIG; print(CONFIG['db_connection']['host'])")

echo "Initializing database: $DB_NAME"

# Create database if it doesn't exist
if PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -U $DB_USER -lqt | cut -d \| -f 1 | grep -qw $DB_NAME; then
    echo "Database $DB_NAME already exists"
else
    echo "Creating database $DB_NAME..."
    PGPASSWORD=$DB_PASSWORD createdb -h $DB_HOST -U $DB_USER $DB_NAME
    # Install extensions
    echo "Installing PostGIS extensions..."
    PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "CREATE EXTENSION IF NOT EXISTS postgis; CREATE EXTENSION IF NOT EXISTS postgis_raster;"

    echo "Database initialization complete!"
fi







