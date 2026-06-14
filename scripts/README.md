# Scripts

Utility scripts for generating and managing HD map SQLite databases.

---

## generate_sample_map.py

Generates a sample HD map `.db` file for development and testing. Populates all core tables with realistic synthetic geometry.

### Usage

```bash
python scripts/generate_sample_map.py --output sample_map.db
```

| Argument | Default | Description |
|---|---|---|
| `--output` | `sample_map.db` | Path for the output `.db` file |

---

### How It Works

#### 1. Geohash Utilities
Implements standard geohash encoding (`encode_geohash`) and bounding box decoding (`geohash_bounds`). Coordinates are encoded at precision 6, giving tiles of approximately 1.2 km × 0.6 km — a practical granularity for eHorizon tile fetching at runtime.

#### 2. Schema Creation (`create_schema`)
Creates all 6 core tables with `CHECK` constraints on enumerated fields (e.g. `lane_type`, `type` on paint lines) and foreign key enforcement via `PRAGMA foreign_keys = ON`. Four indexes are created targeting the runtime hot path, in particular `GEOHASH_TILE_LANE(geohash_tile_id)` for fast tile-based lane lookups.

| Table | Description |
|---|---|
| `PAINT_LINE` | A road marking boundary (solid, dashed, double-yellow, etc.) |
| `PAINT_LINE_POINT` | Ordered 3D polyline points defining a paint line |
| `LANE` | A drivable lane bounded by two paint lines |
| `LANE_CENTER_POINT` | Ordered centreline points with cumulative station distance |
| `GEOHASH_TILE` | A spatial index cell grouping nearby lanes |
| `GEOHASH_TILE_LANE` | Many-to-many join between tiles and lanes |

#### 3. Lane Geometry (`generate_straight_lane`)
Computes lane geometry in a local ENU (East-North-Up) frame centred on a given origin coordinate. Left and right `PAINT_LINE` rows are inserted first with their ordered `PAINT_LINE_POINT` sequences, followed by the `LANE` row and `LANE_CENTER_POINT` rows with cumulative `station` values along the centreline.

#### 4. Tile Assignment (`assign_lane_to_tiles`)
Computes the geohash tile for a lane's centre coordinate and links it via `GEOHASH_TILE_LANE`. Uses `INSERT OR IGNORE` on both the tile and the join row, making the function safe to call multiple times without creating duplicates.

#### 5. Sample Data (`populate_sample_data`)
Seeds 3 lanes centred on Market St & 5th St, San Francisco — 2 northbound driving lanes and 1 shoulder — with correct paint line marking types on each boundary.

#### 6. CLI Entry Point
Parses the `--output` argument, opens a SQLite connection, runs schema creation and data population, then closes the connection. Safe to re-run against an existing file; `CREATE TABLE IF NOT EXISTS` and `INSERT OR IGNORE` prevent duplicate data.
