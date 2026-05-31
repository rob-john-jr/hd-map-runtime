ADR-001: Hybrid Geohash Precision for Map Tile Delivery

Context
The map tile service must efficiently deliver HD map data to a large fleet of vehicles over LTE. Each vehicle follows a planned route and only requires map data relevant to that route. The system needs a spatial indexing strategy that minimizes data transfer while keeping server-side route resolution fast.

Decision
Adopt a two-precision geohash approach using a single GEOHASH_TILE table with a precision column to distinguish tile levels.

Precision 5 — routing index (~5km cells)
Used server-side only to resolve a planned route into a geographic corridor. A 200-mile route intersects approximately 15-20 precision 5 tiles, making corridor identification fast without expensive spatial queries across the full dataset. These tiles are never delivered to the vehicle.

Precision 6 — delivery tiles (~600m cells)
The unit of map data delivered to the vehicle over LTE. Tiles are small enough that each vehicle receives only what its route requires. Each tile is versioned independently so a localized map update — a single intersection or lane change — does not force a full re-download.

Consequences
Advantages

Route resolution at precision 5 acts as a coarse filter, dramatically reducing the search space before precision 6 queries run
Independent tile versioning minimizes LTE bandwidth across a large fleet
Mirrors how production autonomous vehicle map systems operate at runtime

Tradeoffs

The GEOHASH_TILE_LANE junction table requires entries at both precision levels, doubling indexing writes during map ingestion
A single precision approach would be simpler to implement and maintain

SQLITE Table Design
A few things worth noting about the design:
GEOHASH_TILE

geohash stores the encoded string like dp3w (precision 5) or dp3wj2 (precision 6) — this is what your RouteParser queries against
precision column is what lets a single table serve both levels — query WHERE precision = 5 for routing, WHERE precision = 6 for delivery
version and updated_at are the heartbeat of Problem 2 — the client sends its current tile versions and the server only pushes what has changed

GEOHASH_TILE_LANE

The junction is simple by design — the complexity lives in the query, not the schema
A lane that straddles a cell boundary gets two rows here, one for each tile it touches
At both precision levels, so a lane near a cell boundary could have up to 4 rows in this table.

