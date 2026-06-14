"""
generate_sample_map.py

Generates a sample HD map SQLite database (.db) for development and testing.
Populates all core tables: PAINT_LINE, PAINT_LINE_POINT, LANE, LANE_CENTER_POINT,
GEOHASH_TILE, and GEOHASH_TILE_LANE with realistic synthetic geometry.

Usage:
    python scripts/generate_sample_map.py --output sample_map.db
"""

import sqlite3
import argparse
import math
import hashlib
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Geohash Utilities
# ---------------------------------------------------------------------------

# Base32 character set used by the geohash encoding standard
GEOHASH_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"

def encode_geohash(lat: float, lon: float, precision: int = 6) -> str:
    """
    Encode a (lat, lon) coordinate into a geohash string.

    Geohashes interleave bits of latitude and longitude to produce a
    short string where prefix length controls spatial resolution.
    Precision 6 ≈ 1.2 km x 0.6 km, which suits tile-level indexing.
    """
    min_lat, max_lat = -90.0, 90.0
    min_lon, max_lon = -180.0, 180.0

    bits = []
    even = True  # Alternate between encoding longitude (even) and latitude (odd)

    while len(bits) < precision * 5:
        if even:
            mid = (min_lon + max_lon) / 2
            if lon >= mid:
                bits.append(1)
                min_lon = mid
            else:
                bits.append(0)
                max_lon = mid
        else:
            mid = (min_lat + max_lat) / 2
            if lat >= mid:
                bits.append(1)
                min_lat = mid
            else:
                bits.append(0)
                max_lat = mid
        even = not even

    # Pack bits into base32 characters (5 bits per character)
    geohash = ""
    for i in range(0, len(bits), 5):
        chunk = bits[i:i + 5]
        index = sum(b << (4 - j) for j, b in enumerate(chunk))
        geohash += GEOHASH_BASE32[index]

    return geohash


def geohash_bounds(geohash: str) -> tuple[float, float, float, float]:
    """
    Decode a geohash string into its bounding box (min_lat, min_lon, max_lat, max_lon).
    Used to populate the GEOHASH_TILE spatial extent columns.
    """
    min_lat, max_lat = -90.0, 90.0
    min_lon, max_lon = -180.0, 180.0
    even = True

    for char in geohash:
        index = GEOHASH_BASE32.index(char)
        # Decode 5 bits from the base32 character
        for bit in [4, 3, 2, 1, 0]:
            b = (index >> bit) & 1
            if even:
                mid = (min_lon + max_lon) / 2
                if b:
                    min_lon = mid
                else:
                    max_lon = mid
            else:
                mid = (min_lat + max_lat) / 2
                if b:
                    min_lat = mid
                else:
                    max_lat = mid
            even = not even

    # Return as (min_x, min_y, max_x, max_y) where x=lon, y=lat
    return min_lon, min_lat, max_lon, max_lat


# ---------------------------------------------------------------------------
# Schema Creation
# ---------------------------------------------------------------------------

def create_schema(conn: sqlite3.Connection) -> None:
    """
    Create all HD map tables if they don't already exist.

    Table order matters: referenced tables must be created before tables
    that hold foreign keys pointing to them.
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

    # PAINT_LINE_POINT: ordered 3D polyline points defining a paint line's geometry
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS PAINT_LINE_POINT (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            paint_line_id   INTEGER NOT NULL REFERENCES PAINT_LINE(id),
            sequence_number INTEGER NOT NULL,  -- ordering index along the line
            x               REAL    NOT NULL,  -- easting  (metres, local ENU frame)
            y               REAL    NOT NULL,  -- northing (metres, local ENU frame)
            z               REAL    NOT NULL   -- elevation (metres)
        );
    """)

    # LANE: a drivable lane bounded by two paint lines
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

    # LANE_CENTER_POINT: ordered 3D points along the lane centreline
    # station = cumulative arc length from the lane start (metres)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS LANE_CENTER_POINT (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            lane_id         INTEGER NOT NULL REFERENCES LANE(id),
            sequence_number INTEGER NOT NULL,
            x               REAL    NOT NULL,
            y               REAL    NOT NULL,
            z               REAL    NOT NULL,
            station         REAL    NOT NULL  -- distance along lane from origin
        );
    """)

    # GEOHASH_TILE: a spatial index cell that groups nearby lanes for fast lookup
    # version allows cache invalidation when tile content changes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS GEOHASH_TILE (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            geohash    TEXT    NOT NULL UNIQUE,  -- e.g. "9q8yy"
            precision  INTEGER NOT NULL,          -- number of geohash characters
            min_x      REAL    NOT NULL,          -- bounding box lon west
            min_y      REAL    NOT NULL,          -- bounding box lat south
            max_x      REAL    NOT NULL,          -- bounding box lon east
            max_y      REAL    NOT NULL,          -- bounding box lat north
            version    INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT    NOT NULL           -- ISO-8601 UTC timestamp
        );
    """)

    # GEOHASH_TILE_LANE: many-to-many join between tiles and lanes
    # A lane that spans a tile boundary will appear in multiple tiles
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
    print("Schema created.")


# ---------------------------------------------------------------------------
# Sample Data Generation
# ---------------------------------------------------------------------------

def generate_straight_lane(
    conn: sqlite3.Connection,
    origin_lat: float,
    origin_lon: float,
    bearing_deg: float,
    length_m: float,
    width_m: float,
    lane_type: str,
    paint_left: str,
    paint_right: str,
    num_points: int = 10,
) -> int:
    """
    Insert a single straight lane into the database and return its lane id.

    The lane geometry is computed in a simple local ENU (East-North-Up) frame
    centred on (origin_lat, origin_lon). For a sample map this avoids the
    complexity of a full projection library while still producing realistic
    spatial relationships between points.

    Args:
        conn          : open SQLite connection
        origin_lat/lon: start coordinate of the lane centreline (decimal degrees)
        bearing_deg   : direction of travel (degrees clockwise from north)
        length_m      : lane length in metres
        width_m       : lane width in metres (used to offset boundary lines)
        lane_type     : must match the CHECK constraint on LANE.lane_type
        paint_left/right: line marking types for each boundary
        num_points    : number of polyline vertices (more = smoother curves)

    Returns:
        The rowid of the newly inserted LANE row.
    """
    cursor = conn.cursor()

    # Convert bearing to standard math angle (radians, CCW from east)
    bearing_rad = math.radians(90 - bearing_deg)
    dx = math.cos(bearing_rad)  # unit step in X (east) per metre
    dy = math.sin(bearing_rad)  # unit step in Y (north) per metre

    # Perpendicular offset direction for lane boundaries
    perp_x = -dy
    perp_y = dx
    half_w = width_m / 2.0

    def insert_paint_line(offset_sign: float, line_type: str) -> int:
        """Insert a paint line offset from the centreline and return its id."""
        cursor.execute(
            "INSERT INTO PAINT_LINE (type, length) VALUES (?, ?)",
            (line_type, length_m)
        )
        line_id = cursor.lastrowid

        for i in range(num_points):
            t = i / (num_points - 1)  # 0.0 → 1.0 along the lane
            dist = t * length_m
            x = dist * dx + offset_sign * half_w * perp_x
            y = dist * dy + offset_sign * half_w * perp_y
            cursor.execute(
                "INSERT INTO PAINT_LINE_POINT "
                "(paint_line_id, sequence_number, x, y, z) VALUES (?,?,?,?,?)",
                (line_id, i, x, y, 0.0)
            )
        return line_id

    # Insert left and right boundary lines
    left_id  = insert_paint_line(+1, paint_left)
    right_id = insert_paint_line(-1, paint_right)

    # Insert the lane row linking both boundaries
    cursor.execute(
        "INSERT INTO LANE (right_paint_line_id, left_paint_line_id, length, lane_type) "
        "VALUES (?, ?, ?, ?)",
        (right_id, left_id, length_m, lane_type)
    )
    lane_id = cursor.lastrowid

    # Insert centreline points with cumulative station distance
    for i in range(num_points):
        t = i / (num_points - 1)
        dist = t * length_m
        x = dist * dx
        y = dist * dy
        cursor.execute(
            "INSERT INTO LANE_CENTER_POINT "
            "(lane_id, sequence_number, x, y, z, station) VALUES (?,?,?,?,?,?)",
            (lane_id, i, x, y, 0.0, dist)
        )

    return lane_id


def assign_lane_to_tiles(
    conn: sqlite3.Connection,
    lane_id: int,
    center_lat: float,
    center_lon: float,
    precision: int = 6,
) -> None:
    """
    Compute the geohash tile for a lane's centre coordinate and link them
    in GEOHASH_TILE_LANE.

    In a production pipeline you would compute the geohash for every point
    along the lane and insert a row for every unique tile it crosses.
    For this sample generator, using the centre point is sufficient.
    """
    cursor = conn.cursor()
    gh = encode_geohash(center_lat, center_lon, precision)
    now = datetime.now(timezone.utc).isoformat()

    # Upsert the tile — insert if new, ignore if the geohash already exists
    cursor.execute(
        "INSERT OR IGNORE INTO GEOHASH_TILE "
        "(geohash, precision, min_x, min_y, max_x, max_y, version, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
        (gh, precision, *geohash_bounds(gh), now)
    )

    # Retrieve the tile id (whether just inserted or pre-existing)
    cursor.execute("SELECT id FROM GEOHASH_TILE WHERE geohash = ?", (gh,))
    tile_id = cursor.fetchone()[0]

    # Link the lane to its tile (UNIQUE constraint prevents duplicates)
    cursor.execute(
        "INSERT OR IGNORE INTO GEOHASH_TILE_LANE (geohash_tile_id, lane_id) VALUES (?, ?)",
        (tile_id, lane_id)
    )


def populate_sample_data(conn: sqlite3.Connection) -> None:
    """
    Insert a small realistic road segment: two parallel driving lanes
    heading north, each with a shoulder, centred on downtown San Francisco.
    """
    # San Francisco — Market St & 5th St approximate coordinates
    BASE_LAT = 37.7841
    BASE_LON = -122.4075

    # Small longitude offset between lanes (~3.7 m per 0.00003 deg lon at this lat)
    LON_LANE_OFFSET = 0.00004

    lanes = [
        # (label, lat,      lon,              bearing, length, width, type,      left_paint,     right_paint)
        ("Lane 1 NB driving", BASE_LAT, BASE_LON,                  0, 200, 3.7, "driving",  "solid_white",  "dashed_white"),
        ("Lane 2 NB driving", BASE_LAT, BASE_LON + LON_LANE_OFFSET, 0, 200, 3.7, "driving",  "dashed_white", "solid_white"),
        ("Lane 1 NB shoulder",BASE_LAT, BASE_LON - LON_LANE_OFFSET, 0, 200, 2.5, "shoulder", "solid_white",  "no_paint"),
    ]

    for label, lat, lon, bearing, length, width, ltype, lpaint, rpaint in lanes:
        lane_id = generate_straight_lane(
            conn, lat, lon, bearing, length, width, ltype, lpaint, rpaint
        )
        # Place the tile at the lane midpoint
        mid_lat = lat + (length / 2) * (1 / 111_320)  # ~111,320 m per degree lat
        assign_lane_to_tiles(conn, lane_id, mid_lat, lon)
        print(f"  Inserted: {label} → lane_id={lane_id}")

    conn.commit()
    print("Sample data committed.")


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a sample HD map SQLite database."
    )
    parser.add_argument(
        "--output", default="sample_map.db",
        help="Path for the output .db file (default: sample_map.db)"
    )
    args = parser.parse_args()

    print(f"Creating database: {args.output}")
    conn = sqlite3.connect(args.output)

    try:
        create_schema(conn)
        print("Inserting sample lanes...")
        populate_sample_data(conn)
        print(f"\nDone. Database written to: {args.output}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
