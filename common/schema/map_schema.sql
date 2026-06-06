PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS paint_line (
    id      INTEGER PRIMARY KEY,
    type    TEXT    NOT NULL,
    length  REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS paint_line_point (
    id              INTEGER PRIMARY KEY,
    paint_line_id   INTEGER NOT NULL REFERENCES paint_line(id),
    sequence_number INTEGER NOT NULL,
    x               REAL    NOT NULL,
    y               REAL    NOT NULL,
    z               REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS lane (
    id                   INTEGER PRIMARY KEY,
    right_paint_line_id  INTEGER NOT NULL REFERENCES paint_line(id),
    left_paint_line_id   INTEGER NOT NULL REFERENCES paint_line(id),
    length               REAL    NOT NULL,
    lane_type            TEXT    NOT NULL CHECK(lane_type IN ('driving', 'shoulder', 'bike', 'parking', 'merge', 'exit', 'on_ramp', 'off_ramp', 'hov', 'restricted'))
);

CREATE TABLE IF NOT EXISTS lane_center_point (
    id              INTEGER PRIMARY KEY,
    lane_id         INTEGER NOT NULL REFERENCES lane(id),
    sequence_number INTEGER NOT NULL,
    x               REAL    NOT NULL,
    y               REAL    NOT NULL,
    z               REAL    NOT NULL,
    station         REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS geohash_tile (
    id          INTEGER PRIMARY KEY,
    geohash     TEXT    NOT NULL UNIQUE,
    precision   INTEGER NOT NULL,
    min_x       REAL    NOT NULL,
    min_y       REAL    NOT NULL,
    max_x       REAL    NOT NULL,
    max_y       REAL    NOT NULL,
    version     INTEGER NOT NULL DEFAULT 1,
    updated_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS geohash_tile_lane (
    id              INTEGER PRIMARY KEY,
    geohash_tile_id INTEGER NOT NULL REFERENCES geohash_tile(id),
    lane_id         INTEGER NOT NULL REFERENCES lane(id),
    UNIQUE(geohash_tile_id, lane_id)
);

CREATE INDEX IF NOT EXISTS idx_paint_line_point_line   ON paint_line_point(paint_line_id, sequence_number);
CREATE INDEX IF NOT EXISTS idx_lane_center_point_lane  ON lane_center_point(lane_id, sequence_number);
CREATE INDEX IF NOT EXISTS idx_geohash_tile_geohash    ON geohash_tile(geohash);
CREATE INDEX IF NOT EXISTS idx_geohash_tile_lane_tile  ON geohash_tile_lane(geohash_tile_id);
CREATE INDEX IF NOT EXISTS idx_geohash_tile_lane_lane  ON geohash_tile_lane(lane_id);
