"""
generate_database_schema.py

Creates the HD map SQLite database file and initialises all core tables,
constraints, and indexes. Does NOT insert any map data — use inject_map_data.py
for that.

Usage:
    python scripts/generate_database_schema.py --output sample_map.db
"""

import sqlite3
import argparse


# ---------------------------------------------------------------------------
# Schema Creation
# ---------------------------------------------------------------------------

def create_schema(conn: sqlite3.Connection) -> None:
    """
    Create all HD map tables if they don't already exist.

    Table order matters: referenced tables must be created before tables
    that hold foreign keys pointing to them.

    Coordinate convention (WGS84):
        x = longitude  (decimal degrees, min 6 decimal places)
        y = latitude   (decimal degrees, min 6 decimal places)
        z = elevation  (metres above WGS84 ellipsoid)
    """
    cursor = conn.cursor()

    # Enable foreign key enforcement — SQLite disables this by default
    cursor.execute("PRAGMA foreign_keys = ON;")

    # PAINT_LINE: represents a road marking (solid, dashed, double-yellow, etc.)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS PAINT_LINE (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            type    TEXT    NOT NULL CHECK(type IN (
                        'solid_white', 'dashed_white',
                        'solid_yellow', 'dashed_yellow', 'double_yellow',
                        'no_paint'
                    )),
            length  REAL    NOT NULL  -- total arc length in metres
        );
    """)

    # PAINT_LINE_POINT: ordered 3D polyline points defining a paint line's geometry.
    # x/y stored as WGS84 lon/lat in decimal degrees (≥ 6 decimal places).
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS PAINT_LINE_POINT (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            paint_line_id   INTEGER NOT NULL REFERENCES PAINT_LINE(id),
            sequence_number INTEGER NOT NULL,   -- ordering index along the line
            x               REAL    NOT NULL,   -- longitude (WGS84 decimal degrees)
            y               REAL    NOT NULL,   -- latitude  (WGS84 decimal degrees)
            z               REAL    NOT NULL    -- elevation (metres)
        );
    """)

    # LANE: a drivable lane bounded by two paint lines.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS LANE (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            right_paint_line_id INTEGER NOT NULL REFERENCES PAINT_LINE(id),
            left_paint_line_id  INTEGER NOT NULL REFERENCES PAINT_LINE(id),
            length              REAL    NOT NULL,  -- arc length in metres
            lane_type           TEXT    NOT NULL CHECK(lane_type IN (
                                    'driving', 'shoulder', 'bike',
                                    'merge', 'exit', 'parking'
                                ))
        );
    """)

    # LANE_CENTER_POINT: ordered 3D points along the lane centreline.
    # station = cumulative arc length from the lane start (metres).
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS LANE_CENTER_POINT (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            lane_id         INTEGER NOT NULL REFERENCES LANE(id),
            sequence_number INTEGER NOT NULL,
            x               REAL    NOT NULL,   -- longitude (WGS84 decimal degrees)
            y               REAL    NOT NULL,   -- latitude  (WGS84 decimal degrees)
            z               REAL    NOT NULL,   -- elevation (metres)
            station         REAL    NOT NULL    -- distance along lane from origin (metres)
        );
    """)

    # GEOHASH_TILE: a spatial index cell that groups nearby lanes for fast lookup.
    # version allows cache invalidation when tile content changes.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS GEOHASH_TILE (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            geohash    TEXT    NOT NULL UNIQUE,  -- e.g. "9q8yyk"
            precision  INTEGER NOT NULL,          -- number of geohash characters
            min_x      REAL    NOT NULL,          -- bounding box: west  longitude
            min_y      REAL    NOT NULL,          -- bounding box: south latitude
            max_x      REAL    NOT NULL,          -- bounding box: east  longitude
            max_y      REAL    NOT NULL,          -- bounding box: north latitude
            version    INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT    NOT NULL           -- ISO-8601 UTC timestamp
        );
    """)

    # GEOHASH_TILE_LANE: many-to-many join between tiles and lanes.
    # A lane that spans a tile boundary will appear in multiple tiles.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS GEOHASH_TILE_LANE (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            geohash_tile_id INTEGER NOT NULL REFERENCES GEOHASH_TILE(id),
            lane_id         INTEGER NOT NULL REFERENCES LANE(id),
            UNIQUE(geohash_tile_id, lane_id)  -- prevent duplicate associations
        );
    """)

    # ---------------------------------------------------------------------------
    # Indexes — critical for runtime query performance
    # ---------------------------------------------------------------------------

    # Primary runtime query: "give me all lanes in geohash tile X"
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_geohash_tile_lane_tile
        ON GEOHASH_TILE_LANE(geohash_tile_id);
    """)

    # Tile lookup by geohash string (already covered by UNIQUE, but explicit)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_geohash_tile_geohash
        ON GEOHASH_TILE(geohash);
    """)

    # Point lookup ordered by sequence when reconstructing polylines
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_paint_line_point_line
        ON PAINT_LINE_POINT(paint_line_id, sequence_number);
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_lane_center_point_lane
        ON LANE_CENTER_POINT(lane_id, sequence_number);
    """)

    conn.commit()
    print("Schema created successfully.")


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create the HD map SQLite database schema."
    )
    parser.add_argument(
        "--output", default="sample_map.db",
        help="Path for the output .db file (default: sample_map.db)"
    )
    args = parser.parse_args()

    print(f"Initialising database: {args.output}")
    conn = sqlite3.connect(args.output)

    try:
        create_schema(conn)
        print(f"Database ready: {args.output}")
        print("Run inject_map_data.py to populate with map data.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
