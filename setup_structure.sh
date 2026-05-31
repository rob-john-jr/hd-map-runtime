#!/bin/bash
# Run this from the root of your cloned GitHub repo
# chmod +x setup_structure.sh && ./setup_structure.sh

set -e
BASE="."

echo "Creating hd-map-runtime project structure..."

# Directories
mkdir -p $BASE/common/proto
mkdir -p $BASE/common/schema
mkdir -p $BASE/common/utils
mkdir -p $BASE/map-compression/src
mkdir -p $BASE/map-compression/tests
mkdir -p $BASE/map-tile-service/server
mkdir -p $BASE/map-tile-service/client
mkdir -p $BASE/map-tile-service/tests
mkdir -p $BASE/ehorizon/src
mkdir -p $BASE/ehorizon/include
mkdir -p $BASE/ehorizon/tests
mkdir -p $BASE/docs/adr
mkdir -p $BASE/docs/diagrams
mkdir -p $BASE/scripts

# Common
touch $BASE/common/proto/horizon.proto
touch $BASE/common/schema/map_schema.sql
touch $BASE/common/utils/__init__.py

# Map Compression (Problem 1 - Python)
touch $BASE/map-compression/src/__init__.py
touch $BASE/map-compression/src/compressor.py
touch $BASE/map-compression/src/point_reducer.py
touch $BASE/map-compression/src/db_handler.py
touch $BASE/map-compression/tests/__init__.py
touch $BASE/map-compression/tests/test_compressor.py
touch $BASE/map-compression/tests/test_point_reducer.py
touch $BASE/map-compression/requirements.txt
touch $BASE/map-compression/README.md

# Map Tile Service (Problem 2 - Python)
touch $BASE/map-tile-service/server/__init__.py
touch $BASE/map-tile-service/server/app.py
touch $BASE/map-tile-service/server/tile_manager.py
touch $BASE/map-tile-service/server/route_parser.py
touch $BASE/map-tile-service/client/__init__.py
touch $BASE/map-tile-service/client/tile_client.py
touch $BASE/map-tile-service/client/cache_manager.py
touch $BASE/map-tile-service/tests/__init__.py
touch $BASE/map-tile-service/tests/test_tile_manager.py
touch $BASE/map-tile-service/tests/test_tile_client.py
touch $BASE/map-tile-service/requirements.txt
touch $BASE/map-tile-service/README.md

# eHorizon (Problem 3 - C++)
touch $BASE/ehorizon/src/main.cpp
touch $BASE/ehorizon/src/map_provider.cpp
touch $BASE/ehorizon/src/pose_handler.cpp
touch $BASE/ehorizon/src/horizon_builder.cpp
touch $BASE/ehorizon/include/map_provider.h
touch $BASE/ehorizon/include/pose_handler.h
touch $BASE/ehorizon/include/horizon_builder.h
touch $BASE/ehorizon/include/types.h
touch $BASE/ehorizon/tests/test_map_provider.cpp
touch $BASE/ehorizon/tests/test_horizon_builder.cpp
touch $BASE/ehorizon/CMakeLists.txt
touch $BASE/ehorizon/README.md

# Docs
touch $BASE/docs/architecture.md
touch $BASE/docs/adr/001-sqlite-over-flatfiles.md
touch $BASE/docs/adr/002-protobuf-message-format.md
touch $BASE/docs/adr/003-fastapi-tile-server.md

# Scripts
touch $BASE/scripts/generate_sample_map.py

echo ""
echo "Done. Project structure:"
find $BASE -not -path '*/.git/*' -type f | sort
