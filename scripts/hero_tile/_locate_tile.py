"""
Identify the real-world location of the hero tile.

Pure Python — only stdlib + math. Reads the tile's EPSG:3857 bbox from
the extent notes, inverse-Mercators it to lon/lat, compares against a
hardcoded table of well-known Miami neighborhood centers, and writes
an ASCII locator map + JSON to data_processed/miami/hero_tile/notes/.
"""

import math
import json
import re
from pathlib import Path

ROOT = Path(r"C:\Users\Glytc\glytchdraft")
NOTES = ROOT / "data_processed" / "miami" / "hero_tile" / "notes"
EXTENT = NOTES / "hero_tile_extent.txt"
R_EARTH = 6378137.0  # Web Mercator sphere radius


def merc_to_lonlat(x, y):
    lon = math.degrees(x / R_EARTH)
    lat = math.degrees(2 * math.atan(math.exp(y / R_EARTH)) - math.pi / 2)
    return lon, lat


def haversine_km(lon1, lat1, lon2, lat2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def read_3857_bbox(p: Path):
    minx = miny = maxx = maxy = None
    in_3857 = False
    for line in p.read_text(encoding="utf-8").splitlines():
        if "EPSG:3857" in line and "##" in line:
            in_3857 = True
            continue
        if line.startswith("## EPSG:32617"):
            in_3857 = False
        if not in_3857:
            continue
        m = re.match(r"min:\s*\(([-\d.]+),\s*([-\d.]+)", line)
        if m:
            minx, miny = float(m.group(1)), float(m.group(2))
        m = re.match(r"max:\s*\(([-\d.]+),\s*([-\d.]+)", line)
        if m:
            maxx, maxy = float(m.group(1)), float(m.group(2))
    return minx, miny, maxx, maxy


# Approximate centers (lon, lat) of well-known Miami neighborhoods.
NEIGHBORHOODS = {
    "Downtown Miami":       (-80.193, 25.775),
    "Brickell":             (-80.193, 25.762),
    "Wynwood":              (-80.198, 25.802),
    "Design District":      (-80.193, 25.813),
    "Little Haiti":         (-80.205, 25.825),
    "Edgewater":            (-80.190, 25.795),
    "Overtown":             (-80.205, 25.788),
    "Miami Beach (mid)":    (-80.130, 25.793),
    "South Beach":          (-80.130, 25.776),
    "Mid-Beach/Fontainebleau": (-80.122, 25.815),
    "Coconut Grove":        (-80.247, 25.725),
    "Coral Gables":         (-80.272, 25.722),
    "Key Biscayne":         (-80.163, 25.694),
    "Virginia Key":         (-80.165, 25.737),
    "Kendall":              (-80.371, 25.679),
    "Pinecrest":            (-80.305, 25.665),
    "Palmetto Bay":         (-80.327, 25.621),
    "Cutler Bay":           (-80.349, 25.580),
    "Homestead":            (-80.477, 25.467),
    "Doral":                (-80.350, 25.819),
    "Aventura":             (-80.144, 25.957),
    "Hialeah":              (-80.279, 25.857),
    "Biscayne Bay (central)":  (-80.166, 25.760),
    "Biscayne Bay (southern)": (-80.190, 25.610),
    "Elliott Key (BNP)":    (-80.187, 25.453),
    "Boca Chita Key (BNP)": (-80.175, 25.524),
    "Sands Key (BNP)":      (-80.180, 25.490),
    "Black Point Marina":   (-80.323, 25.531),
    "Deering Estate":       (-80.300, 25.617),
    "Old Cutler Bay":       (-80.305, 25.598),
}


def main():
    minx, miny, maxx, maxy = read_3857_bbox(EXTENT)
    print(f"EPSG:3857 bbox:  ({minx}, {miny}) -> ({maxx}, {maxy})")

    sw_lon, sw_lat = merc_to_lonlat(minx, miny)
    ne_lon, ne_lat = merc_to_lonlat(maxx, maxy)
    nw_lon, nw_lat = merc_to_lonlat(minx, maxy)
    se_lon, se_lat = merc_to_lonlat(maxx, miny)
    c_lon, c_lat = merc_to_lonlat((minx + maxx) / 2, (miny + maxy) / 2)

    print(f"\nCorners (lon, lat):")
    print(f"  SW: {sw_lon:.4f}, {sw_lat:.4f}")
    print(f"  NW: {nw_lon:.4f}, {nw_lat:.4f}")
    print(f"  NE: {ne_lon:.4f}, {ne_lat:.4f}")
    print(f"  SE: {se_lon:.4f}, {se_lat:.4f}")
    print(f"  C : {c_lon:.4f}, {c_lat:.4f}")

    print(f"\nNeighborhoods by proximity to tile CENTER:")
    ranked = []
    for name, (nlon, nlat) in NEIGHBORHOODS.items():
        d_km = haversine_km(c_lon, c_lat, nlon, nlat)
        inside = (sw_lon <= nlon <= ne_lon) and (sw_lat <= nlat <= ne_lat)
        ranked.append((d_km, name, inside, nlon, nlat))
    ranked.sort()
    for d, name, inside, lon, lat in ranked[:10]:
        marker = "INSIDE" if inside else f"{d:5.1f} km"
        print(f"  [{marker:>10}] {name:30s} ({lon:.4f}, {lat:.4f})")

    print("\nNeighborhoods INSIDE the tile bbox (lon/lat rectangle test):")
    inside_list = [(d, n, lo, la) for d, n, ins, lo, la in ranked if ins]
    if inside_list:
        for d, name, lo, la in inside_list:
            print(f"  - {name}  ({lo:.4f}, {lo:.4f})")
    else:
        print("  (none of the listed reference points fall inside)")

    # ---- ASCII map ----
    print("\nASCII locator (north is up):")
    print()
    # Set up a coarse 30x12 grid covering greater Miami
    LON_LO, LON_HI = -80.55, -80.05
    LAT_LO, LAT_HI = 25.40, 25.95
    W, H = 60, 24
    grid = [[" "] * W for _ in range(H)]

    def to_grid(lon, lat):
        if not (LON_LO <= lon <= LON_HI and LAT_LO <= lat <= LAT_HI):
            return None
        gx = int((lon - LON_LO) / (LON_HI - LON_LO) * (W - 1))
        gy = int((LAT_HI - lat) / (LAT_HI - LAT_LO) * (H - 1))
        return gx, gy

    # Plot tile rectangle
    def plot_rect(min_lon, min_lat, max_lon, max_lat, ch):
        sw = to_grid(min_lon, min_lat)
        ne = to_grid(max_lon, max_lat)
        if not sw or not ne:
            return
        x0, y0 = sw
        x1, y1 = ne
        for x in range(min(x0, x1), max(x0, x1) + 1):
            grid[y0][x] = ch
            grid[y1][x] = ch
        for y in range(min(y0, y1), max(y0, y1) + 1):
            grid[y][x0] = ch
            grid[y][x1] = ch

    # Mark each neighborhood with a '.'
    for name, (lon, lat) in NEIGHBORHOODS.items():
        g = to_grid(lon, lat)
        if g:
            gx, gy = g
            grid[gy][gx] = "."

    # Plot tile bbox as '#'
    plot_rect(sw_lon, sw_lat, ne_lon, ne_lat, "#")

    # Print grid
    for row in grid:
        print("  " + "".join(row))
    print(f"  lat {LAT_LO:.2f} - {LAT_HI:.2f}    lon {LON_LO:.2f} - {LON_HI:.2f}")
    print("  '#' = hero tile bbox       '.' = neighborhood reference point")

    # ---- Write JSON ----
    out = {
        "tile_name": "miami_hero_tile_v001",
        "bbox_4326_lonlat": {
            "sw": [sw_lon, sw_lat],
            "ne": [ne_lon, ne_lat],
            "center": [c_lon, c_lat],
        },
        "bbox_3857_meters": {
            "sw": [minx, miny], "ne": [maxx, maxy],
        },
        "approx_dimensions_km": {
            "ew": haversine_km(sw_lon, c_lat, ne_lon, c_lat),
            "ns": haversine_km(c_lon, sw_lat, c_lon, ne_lat),
        },
        "neighborhoods_inside_bbox": [n for _, n, ins, _, _ in ranked if ins],
        "nearest_neighborhoods_to_center_km": [
            {"name": name, "distance_km": round(d, 2), "is_inside_bbox": ins}
            for d, name, ins, _, _ in ranked[:8]
        ],
    }
    (NOTES / "hero_tile_locator.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nwrote: {NOTES / 'hero_tile_locator.json'}")


if __name__ == "__main__":
    main()
