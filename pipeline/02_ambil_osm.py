"""Ambil jaringan tol dan sungai dari OpenStreetMap (Overpass), lalu muat ke DuckDB.

Tabel yang dibuat:
  osm_tol_ruas   badan jalan tol (highway=motorway) dan ramp (motorway_link), satu baris per ruas
  osm_gardu      gardu tol (barrier=toll_booth), satu baris per gardu
  osm_sungai     sungai, kali, saluran besar (waterway=river/canal/stream)

Jalankan ulang hanya kalau ingin data OSM terbaru: hapus folder cache/overpass dulu.
"""
from __future__ import annotations

import json

from umum import BBOX, CACHE, ambil, con

OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
KOTAK = ",".join(str(x) for x in BBOX)

Q_TOL = f"""[out:json][timeout:180];
(way["highway"~"^(motorway|motorway_link)$"]({KOTAK});
 node["barrier"="toll_booth"]({KOTAK});
 node["highway"="motorway_junction"]({KOTAK}););
out geom;"""
Q_SUNGAI = f"""[out:json][timeout:240];
way["waterway"~"^(river|canal|stream)$"]({KOTAK});
out geom;"""


def overpass(q: str) -> dict:
    for url in OVERPASS:
        data = ambil(url, kelompok="overpass", post=q, jeda=5, timeout=300)
        if data and data.get("elements"):
            return data
    raise SystemExit("Overpass tidak menjawab. Coba lagi nanti.")


def wkt_garis(geom: list[dict]) -> str:
    return "LINESTRING (" + ", ".join(f"{p['lon']} {p['lat']}" for p in geom) + ")"


def main() -> None:
    tol = overpass(Q_TOL)["elements"]
    sungai = overpass(Q_SUNGAI)["elements"]
    ruas, gardu, simpang = [], [], []
    for e in tol:
        t = e.get("tags", {})
        if e["type"] == "way" and len(e.get("geometry", [])) >= 2:
            ruas.append({"way_id": e["id"], "jenis": t.get("highway"), "nama": t.get("name", ""),
                         "ref": t.get("ref", ""), "oneway": t.get("oneway", ""), "toll": t.get("toll", ""),
                         "nodes": e.get("nodes", []), "wkt": wkt_garis(e["geometry"])})
        elif e["type"] == "node" and t.get("barrier") == "toll_booth":
            gardu.append({"node_id": e["id"], "nama": t.get("name", ""), "lat": e["lat"], "lon": e["lon"],
                          "operator": t.get("operator", "")})
        elif e["type"] == "node":
            simpang.append({"node_id": e["id"], "nama": t.get("name", ""), "ref": t.get("ref", ""),
                            "lat": e["lat"], "lon": e["lon"]})
    air = [{"way_id": e["id"], "jenis": e["tags"].get("waterway"), "nama": e["tags"].get("name", ""),
            "wkt": wkt_garis(e["geometry"])} for e in sungai if len(e.get("geometry", [])) >= 2]

    tmp = CACHE / "overpass"
    for nama, isi in (("ruas", ruas), ("gardu", gardu), ("simpang", simpang), ("air", air)):
        (tmp / f"_{nama}.json").write_text(json.dumps(isi), encoding="utf-8")

    c = con()
    c.execute(f"""
        CREATE OR REPLACE TABLE osm_tol_ruas AS
        SELECT way_id, jenis, nama, ref, oneway, toll, nodes,
               ST_GeomFromText(wkt) AS geom,
               ST_Transform(ST_GeomFromText(wkt), 'EPSG:4326', 'EPSG:32748', true) AS geom_m
        FROM read_json('{(tmp / "_ruas.json").as_posix()}', format='array',
                       columns={{way_id:'BIGINT', jenis:'VARCHAR', nama:'VARCHAR', ref:'VARCHAR', oneway:'VARCHAR',
                                toll:'VARCHAR', nodes:'BIGINT[]', wkt:'VARCHAR'}});
        CREATE OR REPLACE TABLE osm_gardu AS
        SELECT node_id, nama, operator, lat, lon, ST_Point(lon, lat) AS geom,
               ST_Transform(ST_Point(lon, lat), 'EPSG:4326', 'EPSG:32748', true) AS geom_m
        FROM read_json('{(tmp / "_gardu.json").as_posix()}', format='array',
                       columns={{node_id:'BIGINT', nama:'VARCHAR', lat:'DOUBLE', lon:'DOUBLE', operator:'VARCHAR'}});
        CREATE OR REPLACE TABLE osm_simpang AS
        SELECT node_id, nama, ref, lat, lon
        FROM read_json('{(tmp / "_simpang.json").as_posix()}', format='array',
                       columns={{node_id:'BIGINT', nama:'VARCHAR', ref:'VARCHAR', lat:'DOUBLE', lon:'DOUBLE'}});
        CREATE OR REPLACE TABLE osm_sungai AS
        SELECT way_id, jenis, nama, ST_GeomFromText(wkt) AS geom,
               ST_Transform(ST_GeomFromText(wkt), 'EPSG:4326', 'EPSG:32748', true) AS geom_m
        FROM read_json('{(tmp / "_air.json").as_posix()}', format='array',
                       columns={{way_id:'BIGINT', jenis:'VARCHAR', nama:'VARCHAR', wkt:'VARCHAR'}});
    """)
    for t in ("osm_tol_ruas", "osm_gardu", "osm_simpang", "osm_sungai"):
        print(t, c.execute(f"select count(*) from {t}").fetchone()[0])
    print(c.execute("select jenis, count(*), round(sum(ST_Length(geom_m))/1000) km from osm_tol_ruas group by 1").fetchall())
    print(c.execute("select jenis, count(*), round(sum(ST_Length(geom_m))/1000) km from osm_sungai group by 1").fetchall())


if __name__ == "__main__":
    main()
