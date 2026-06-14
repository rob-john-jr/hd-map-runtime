"""
map_visualizer.py

Visualizes HD map SQLite database contents using GeoPandas and Shapely.
Renders lane centrelines, paint line boundaries, and geohash tile bounding
boxes as a matplotlib figure.

Usage:
    python scripts/map_visualizer.py --db sample_map.db

Overview:
    1. load_lane_centrelines() — Queries LANE_CENTER_POINT joined to LANE,
       groups points by lane_id ordered by sequence_number, and builds a
       Shapely LineString per lane. Includes lane_type for colour coding.

    2. load_paint_lines() — Same pattern for PAINT_LINE_POINT, building one
       LineString per paint line boundary with its marking type for styling.

    3. load_geohash_tiles() — Reads bounding box columns from GEOHASH_TILE
       and reprojects from WGS84 to UTM Zone 10N (EPSG:32610) for metric
       display. Uses Shapely's box() to build tile rectangles.

    4. Styling maps — LANE_TYPE_COLORS maps each lane type to a colour;
       PAINT_LINE_STYLES maps each marking type to a line colour/style/weight.

    5. plot_map() — Renders 3 layers bottom-to-top: geohash tile outlines,
       paint line boundaries, then lane centrelines. Dark background mimics
       a real map renderer.

    6. CLI entry point — Takes --db argument, loads all three GeoDataFrames,
       reports row counts, then renders the plot.
"""

import argparse
import sqlite3
from typing import Optional

import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from shapely.geometry import LineString, box

# ---------------------------------------------------------------------------
# Coordinate Reference Systems
# ---------------------------------------------------------------------------

# All coordinates are stored in WGS84 (EPSG:4326) in the database.
# For display we reproject to UTM Zone 10N (EPSG:32610) which covers
# the San Francisco Bay Area. UTM is a metric projection — 1 unit = 1 metre —
# so set_aspect("equal") produces geometrically correct proportions and
# lane widths render without degree-scale distortion.
WGS84_CRS = "EPSG:4326"
DISPLAY_CRS = "EPSG:32610"  # UTM Zone 10N


# ---------------------------------------------------------------------------
# Database Loaders
# ---------------------------------------------------------------------------

def load_lane_centrelines(conn: sqlite3.Connection) -> gpd.GeoDataFrame:
    """
    Load all lane centreline geometries from LANE_CENTER_POINT.

    Groups points by lane_id, orders them by sequence_number, and builds
    a Shapely LineString per lane. Also joins LANE to include lane_type
    so we can colour lanes by type in the plot.
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            lcp.lane_id,
            l.lane_type,
            lcp.x,
            lcp.y,
            lcp.sequence_number
        FROM LANE_CENTER_POINT lcp
        JOIN LANE l ON l.id = lcp.lane_id
        ORDER BY lcp.lane_id, lcp.sequence_number
    """)
    rows = cursor.fetchall()

    # Group points by lane_id into an ordered list of (x, y) tuples
    lanes: dict[int, dict] = {}
    for lane_id, lane_type, x, y, _ in rows:
        if lane_id not in lanes:
            lanes[lane_id] = {"lane_type": lane_type, "coords": []}
        lanes[lane_id]["coords"].append((x, y))

    # Build a GeoDataFrame — one row per lane
    records = []
    for lane_id, data in lanes.items():
        if len(data["coords"]) >= 2:  # LineString requires at least 2 points
            records.append({
                "lane_id": lane_id,
                "lane_type": data["lane_type"],
                "geometry": LineString(data["coords"])
            })

    gdf = gpd.GeoDataFrame(records, crs=WGS84_CRS)
    return gdf.to_crs(DISPLAY_CRS)  # Reproject to UTM Zone 10N (metres)


def load_paint_lines(conn: sqlite3.Connection) -> gpd.GeoDataFrame:
    """
    Load all paint line boundary geometries from PAINT_LINE_POINT.

    Groups points by paint_line_id and builds a LineString per paint line.
    Joins PAINT_LINE to include the line type for styling.
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            plp.paint_line_id,
            pl.type,
            plp.x,
            plp.y,
            plp.sequence_number
        FROM PAINT_LINE_POINT plp
        JOIN PAINT_LINE pl ON pl.id = plp.paint_line_id
        ORDER BY plp.paint_line_id, plp.sequence_number
    """)
    rows = cursor.fetchall()

    lines: dict[int, dict] = {}
    for line_id, line_type, x, y, _ in rows:
        if line_id not in lines:
            lines[line_id] = {"line_type": line_type, "coords": []}
        lines[line_id]["coords"].append((x, y))

    records = []
    for line_id, data in lines.items():
        if len(data["coords"]) >= 2:
            records.append({
                "line_id": line_id,
                "line_type": data["line_type"],
                "geometry": LineString(data["coords"])
            })

    gdf = gpd.GeoDataFrame(records, crs=WGS84_CRS)
    return gdf.to_crs(DISPLAY_CRS)  # Reproject to UTM Zone 10N (metres)


def load_geohash_tiles(conn: sqlite3.Connection) -> gpd.GeoDataFrame:
    """
    Load all geohash tile bounding boxes from GEOHASH_TILE.

    Bounding box columns (min_x, min_y, max_x, max_y) are stored as WGS84
    lon/lat degrees — the same coordinate space as the lane and paint line
    geometry — so no conversion is needed. Shapely's box() constructs the
    tile polygon directly from the stored degree values.
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT geohash, min_x, min_y, max_x, max_y
        FROM GEOHASH_TILE
    """)
    rows = cursor.fetchall()

    records = []
    for geohash, min_x, min_y, max_x, max_y in rows:
        # min_x = west lon, min_y = south lat, max_x = east lon, max_y = north lat
        records.append({
            "geohash": geohash,
            "geometry": box(min_x, min_y, max_x, max_y)
        })

    gdf = gpd.GeoDataFrame(records, crs=WGS84_CRS)
    return gdf.to_crs(DISPLAY_CRS)  # Reproject to UTM Zone 10N (metres)


# ---------------------------------------------------------------------------
# Plot Styling
# ---------------------------------------------------------------------------

# Colour map for lane types
LANE_TYPE_COLORS = {
    "driving":  "#2196F3",  # blue
    "shoulder": "#FF9800",  # orange
    "bike":     "#4CAF50",  # green
    "merge":    "#9C27B0",  # purple
    "exit":     "#F44336",  # red
    "parking":  "#795548",  # brown
}

# Line style map for paint line types
PAINT_LINE_STYLES = {
    "solid_white":    {"color": "white",  "linestyle": "-",  "linewidth": 1.5},
    "dashed_white":   {"color": "white",  "linestyle": "--", "linewidth": 1.2},
    "solid_yellow":   {"color": "yellow", "linestyle": "-",  "linewidth": 1.5},
    "dashed_yellow":  {"color": "yellow", "linestyle": "--", "linewidth": 1.2},
    "double_yellow":  {"color": "yellow", "linestyle": "-",  "linewidth": 2.5},
    "no_paint":       {"color": "gray",   "linestyle": ":",  "linewidth": 0.8},
}


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------

def plot_map(
    centrelines: gpd.GeoDataFrame,
    paint_lines: gpd.GeoDataFrame,
    tiles: gpd.GeoDataFrame,
    save_path: Optional[str] = None,
) -> None:
    """
    Render the HD map layers onto a single matplotlib figure.

    Layer order (bottom to top):
      1. Geohash tile bounding boxes — spatial index cells
      2. Paint line boundaries — road markings
      3. Lane centrelines — coloured by lane type
    """
    fig, ax = plt.subplots(figsize=(12, 10))
    ax.set_facecolor("#1a1a2e")  # Dark background mimics a real map renderer
    fig.patch.set_facecolor("#1a1a2e")
    ax.tick_params(colors="white")
    ax.title.set_color("white")
    for spine in ax.spines.values():
        spine.set_edgecolor("#444")

    # --- Layer 1: Geohash tile bounding boxes ---
    if not tiles.empty:
        tiles.boundary.plot(
            ax=ax,
            color="#00BCD4",      # cyan outline
            linewidth=0.8,
            linestyle="--",
            alpha=0.5,
            label="Geohash Tiles"
        )

    # --- Layer 2: Paint line boundaries ---
    for _, row in paint_lines.iterrows():
        style = PAINT_LINE_STYLES.get(
            row["line_type"],
            {"color": "gray", "linestyle": "-", "linewidth": 1.0}
        )
        ax.plot(
            *row["geometry"].xy,
            color=style["color"],
            linestyle=style["linestyle"],
            linewidth=style["linewidth"],
            alpha=0.8
        )

    # --- Layer 3: Lane centrelines coloured by lane type ---
    for _, row in centrelines.iterrows():
        color = LANE_TYPE_COLORS.get(row["lane_type"], "#FFFFFF")
        ax.plot(
            *row["geometry"].xy,
            color=color,
            linewidth=2.5,
            alpha=0.9,
            label=row["lane_type"]  # deduplicated in legend below
        )

    # --- Legend ---
    # Build legend patches for lane types present in the data
    seen_types = centrelines["lane_type"].unique()
    lane_patches = [
        mpatches.Patch(color=LANE_TYPE_COLORS.get(lt, "white"), label=lt.capitalize())
        for lt in seen_types
    ]
    tile_patch = mpatches.Patch(
        edgecolor="#00BCD4", facecolor="none", linestyle="--", label="Geohash Tile"
    )
    ax.legend(
        handles=lane_patches + [tile_patch],
        loc="upper left",
        facecolor="#2a2a3e",
        labelcolor="white",
        framealpha=0.8
    )

    ax.set_title("HD Map — Lane & Paint Line Visualization", fontsize=14, pad=12)
    ax.set_xlabel("Easting (metres, UTM Zone 10N)", color="white")
    ax.set_ylabel("Northing (metres, UTM Zone 10N)", color="white")
    ax.set_aspect("equal")

    # Fit the view to the road geometry (centrelines + paint lines) with a 50 m
    # padding on each side. Without this the large geohash tile bounding box
    # dominates the zoom level and compresses the road into a small corner.
    road_bounds = centrelines.total_bounds  # (minx, miny, maxx, maxy)
    pad = 50
    ax.set_xlim(road_bounds[0] - pad, road_bounds[2] + pad)
    ax.set_ylim(road_bounds[1] - pad, road_bounds[3] + pad)

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
        print(f"Plot saved to: {save_path}")

    plt.show()


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Visualize an HD map SQLite database using GeoPandas."
    )
    parser.add_argument(
        "--db", default="sample_map.db",
        help="Path to the SQLite .db file (default: sample_map.db)"
    )
    parser.add_argument(
        "--save", default=None,
        help="Optional path to save the plot as an image (e.g. docs/map_preview.png)"
    )
    args = parser.parse_args()

    print(f"Loading database: {args.db}")
    conn = sqlite3.connect(args.db)

    try:
        print("  Reading lane centrelines...")
        centrelines = load_lane_centrelines(conn)
        print(f"  → {len(centrelines)} lanes loaded")

        print("  Reading paint lines...")
        paint_lines = load_paint_lines(conn)
        print(f"  → {len(paint_lines)} paint lines loaded")

        print("  Reading geohash tiles...")
        tiles = load_geohash_tiles(conn)
        print(f"  → {len(tiles)} tiles loaded")
    finally:
        conn.close()

    print("Rendering plot...")
    plot_map(centrelines, paint_lines, tiles, save_path=args.save)


if __name__ == "__main__":
    main()
