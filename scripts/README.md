# Scripts

Utility scripts for generating and managing HD map SQLite databases.

All coordinates are stored in **WGS84 (EPSG:4326)** decimal degrees with a minimum
of 6 decimal places — consistent with industry HD map formats (NDS, OpenDRIVE).

---

## Workflow

```bash
# Step 1 — create the database schema
python scripts/generate_database_schema.py --output sample_map.db

# Step 2 — inject the road network data
python scripts/inject_map_data.py --db sample_map.db

# Step 3 — visualize the result
python scripts/map_visualizer.py --db sample_map.db
```

---

## generate_database_schema.py

Creates the HD map SQLite database file and initialises all core tables,
constraints, and indexes. Does **not** insert any map data.

### Usage

```bash
python scripts/generate_database_schema.py --output sample_map.db
```

| Argument | Default | Description |
|---|---|---|
| `--output` | `sample_map.db` | Path for the output `.db` file |

### Schema

| Table | Description |
|---|---|
| `PAINT_LINE` | A road marking boundary (solid, dashed, double-yellow, etc.) |
| `PAINT_LINE_POINT` | Ordered WGS84 polyline points defining a paint line (x=lon, y=lat) |
| `LANE` | A drivable lane bounded by two paint lines |
| `LANE_CENTER_POINT` | Ordered WGS84 centreline points with cumulative station distance |
| `GEOHASH_TILE` | A spatial index cell grouping nearby lanes |
| `GEOHASH_TILE_LANE` | Many-to-many join between tiles and lanes |

`CHECK` constraints enforce valid `lane_type` and paint line `type` values.
Four indexes target the runtime hot path, in particular `GEOHASH_TILE_LANE(geohash_tile_id)`
for fast tile-based lane lookups.

---

## inject_map_data.py

Injects a fully connected HD map road network into an existing database.
Point density is **1 point per metre** along every centreline and paint line.

### Usage

```bash
python scripts/inject_map_data.py --db sample_map.db
```

| Argument | Default | Description |
|---|---|---|
| `--db` | `sample_map.db` | Path to an existing `.db` file created by `generate_database_schema.py` |

### Road Network

Anchored at **SF Market St & 5th St (37.784100, -122.407500)**:

| Segment | Type | Length | Heading |
|---|---|---|---|
| 1 | Straight | 300 m | North (0°) |
| 2 | Right-hand curve | 150 m radius, 90° arc | North → East |
| 3 | Straight | 300 m | East (90°) |

Segments connect end-to-end — the endpoint of each segment is the start of the next.

### Cross-Section (left → right facing direction of travel)

| Lane | Type | Width | Left Marking | Right Marking |
|---|---|---|---|---|
| Left shoulder | `shoulder` | 2.5 m | `solid_white` | `dashed_white` |
| Lane 1 | `driving` | 3.7 m | `dashed_white` | `dashed_white` |
| Lane 2 | `driving` | 3.7 m | `dashed_white` | `dashed_white` |
| Lane 3 | `driving` | 3.7 m | `dashed_white` | `solid_white` |
| Right shoulder | `shoulder` | 2.5 m | `dashed_white` | `solid_white` |

Total road width: **16.1 m**

### How It Works

#### 1. WGS84 Geometry Utilities (`offset_wgs84`, `perpendicular_bearing`)
Moves a WGS84 coordinate by a given distance and bearing using the spherical direct
formula. Accurate to within ~0.3% at road-scale distances. `perpendicular_bearing`
computes the 90° left/right bearing used for lateral lane offsets.

#### 2. Straight Segment Points (`straight_centreline_points`, `straight_bearings`)
Generates centreline points at 1 m intervals along a straight segment by repeatedly
calling `offset_wgs84`. All points share the same bearing (constant heading).

#### 3. Arc Segment Points (`arc_centreline_points`, `arc_bearings`)
Generates points along a circular arc by locating the centre of curvature, then
sweeping the back-bearing around it by the turn angle. Each lane on a curve has
a unique radius — inner lanes have shorter arcs, outer lanes longer — and point
counts are computed per-lane to preserve 1 m density throughout.

#### 4. Lane Offset (`offset_centreline`)
Offsets a centreline laterally to produce paint line boundaries. Each centreline
point is shifted perpendicular to its local travel bearing, correctly handling
per-point bearing variation on curved sections.

#### 5. Database Insertion (`insert_lane`, `insert_paint_line`)
Inserts `PAINT_LINE` + `PAINT_LINE_POINT` rows for both boundaries, the `LANE` row
linking them, and `LANE_CENTER_POINT` rows for the centreline. Uses `executemany`
for bulk point insertion.

#### 6. Tile Assignment (`assign_lane_to_tiles`)
Iterates every centreline point, computes its geohash, and upserts a `GEOHASH_TILE`
row and `GEOHASH_TILE_LANE` join row. Lanes spanning tile boundaries are registered
in all intersected tiles. Uses `INSERT OR IGNORE` — safe to call multiple times.

---

## map_visualizer.py

Visualizes the contents of an HD map `.db` file using GeoPandas and Shapely.
Renders lane centrelines, paint line boundaries, and geohash tile bounding boxes
as a matplotlib figure on a dark background.

### Requirements

```bash
pip install geopandas shapely matplotlib
```

### Usage

```bash
python scripts/map_visualizer.py --db sample_map.db
```

| Argument | Default | Description |
|---|---|---|
| `--db` | `sample_map.db` | Path to the SQLite `.db` file to visualize |

### Preview

![HD Map Visualization](../docs/map_preview.png)

### What Gets Rendered

| Layer | Description |
|---|---|
| Geohash tile outlines | Cyan dashed rectangles showing spatial index cells |
| Paint line boundaries | White/yellow solid or dashed lines per marking type |
| Lane centrelines | Coloured by lane type (blue = driving, orange = shoulder, etc.) |

### How It Works

#### 1. `load_lane_centrelines()`
Queries `LANE_CENTER_POINT` joined to `LANE`, groups points by `lane_id` ordered
by `sequence_number`, and builds a Shapely `LineString` per lane. Includes
`lane_type` for colour coding.

#### 2. `load_paint_lines()`
Same pattern for `PAINT_LINE_POINT`, building one `LineString` per paint line
boundary with its marking type for styling.

#### 3. `load_geohash_tiles()`
Reads bounding box columns from `GEOHASH_TILE` and converts them from lon/lat
degrees into local ENU metres to match the lane geometry coordinate frame. Uses
Shapely's `box()` to build the tile rectangles.

#### 4. Styling Maps
`LANE_TYPE_COLORS` maps each lane type to a colour; `PAINT_LINE_STYLES` maps
each marking type to a line colour, style, and weight.

#### 5. `plot_map()`
Renders 3 layers bottom-to-top: geohash tile outlines → paint line boundaries →
lane centrelines. Dark background mimics a real map renderer.

#### 6. CLI Entry Point
Takes the `--db` argument, loads all three GeoDataFrames, reports row counts to
the terminal, then renders the interactive plot.
