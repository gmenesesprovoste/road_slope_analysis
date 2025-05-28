# Data Sources

This directory contains pointers to the raw data used in this project.

## Digital Elevation Model (DTM)

* **Source**: [Wuppertal 1m Resolution DTM](https://www.geoportal.nrw/?activetab=map)
* **Resolution**: 1m
* **Format**: TIFF tiles
* **Size**: 581.9 MB (zipped)
* **Date accessed**: May 2025
* **License**: Datenlizenz Deutschland – Namensnennung – Version 2.0
* **Downloading notes**: Clipped to Wuppertal city boundaries using "Download - Gebiete über die Karte - Kreis"
* **CRS**: EPSG:25832 (UTM Zone 32N)

## Road Network Data

* **Source**: [Geofabrik OSM Data Extracts](https://download.geofabrik.de/europe/germany/nordrhein-westfalen.html)
* **Processing Pipeline**:
  1. Download .osm.pbf file for the region
  2. Convert to OSM format using osmium: `osmium cat input.osm.pbf -o output.osm`
  3. Convert to GeoPackage using ogr2ogr with custom configuration and correct CRS: 
     ```bash
     ogr2ogr -f GPKG -t_srs EPSG:25832 output_25832.gpkg output.osm -oo CONFIG_FILE=osmconf.ini lines
     ```
* **Date extracted**: May 2025
* **Format**: GeoPackage (.gpkg)
* **CRS**: EPSG:25832 (UTM Zone 32N) - matches the DTM data
* **Important attributes**: Preserves all highway attributes, bridge/tunnel information, and additional tags
* **License**: OpenStreetMap data © OpenStreetMap contributors, ODbL 1.0 