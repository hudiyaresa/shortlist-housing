"""Langkah 6: bahan banjir untuk semua titik rumah, terutama di luar DKI (data BPBD per RT hanya ada untuk DKI).

Tiga bahan diambil dari layanan publik dan disimpan:
  1. Indeks bahaya banjir InaRISK BNPB (raster 100 m, nilai 0 sampai 1; kosong = di luar zona bahaya).
     https://gis.bnpb.go.id/server/rest/services/inarisk/INDEKS_BAHAYA_BANJIR/ImageServer
  2. Ketinggian tanah di titik rumah (Open-Meteo Elevation, DEM Copernicus 90 m).
  3. Ketinggian tanah di titik terdekat pada sungai/kali terdekat, untuk beda tinggi rumah terhadap sungai.
Jarak ke sungai sendiri dihitung dengan SQL spasial (sql/07_spasial.sql) dari data OSM.

Tabel: `inarisk` dan `elevasi`, keduanya dengan kunci titik (lat5, lon5 = derajat x 1e5).
"""
from __future__ import annotations

import json

from umum import ambil, con

INARISK = "https://gis.bnpb.go.id/server/rest/services/inarisk/INDEKS_BAHAYA_BANJIR/ImageServer/getSamples"
ELEV = "https://api.open-meteo.com/v1/elevation"
SARING = """k.k_harga = 'ya' and k.k_lt <> 'tidak' and k.k_komplek = 'ya' and k.k_mobil <> 'tidak' and k.k_carport <> 'tidak'"""


def potong(daftar: list, n: int):
    for i in range(0, len(daftar), n):
        yield daftar[i:i + n]


def main() -> None:
    c = con()
    c.execute("CREATE TABLE IF NOT EXISTS inarisk (lat5 BIGINT, lon5 BIGINT, indeks DOUBLE, PRIMARY KEY (lat5, lon5))")
    c.execute("CREATE TABLE IF NOT EXISTS elevasi (lat5 BIGINT, lon5 BIGINT, mdpl DOUBLE, PRIMARY KEY (lat5, lon5))")

    # titik rumah yang lolos saringan isi iklan
    rumah = c.execute(f"""select distinct t.lat5, t.lon5 from titik t join k_teks k using (id_rumah)
                          where t.lat is not null and {SARING}""").fetchall()
    # titik terdekat di sungai/kali/saluran terdekat (SQL spasial), untuk beda tinggi
    c.execute(f"""
        CREATE OR REPLACE TABLE titik_sungai AS
        WITH p AS (select distinct t.lat5, t.lon5, t.geom_m from titik t join k_teks k using (id_rumah)
                   where t.lat is not null and {SARING}),
        dekat AS (
            select p.lat5, p.lon5, s.way_id, s.jenis, s.nama, ST_Distance(p.geom_m, s.geom_m) AS jarak_m,
                   ST_Transform(ST_EndPoint(ST_ShortestLine(p.geom_m, s.geom_m)), 'EPSG:32748', 'EPSG:4326', true) AS g,
                   row_number() over (partition by p.lat5, p.lon5 order by ST_Distance(p.geom_m, s.geom_m)) AS urut
            from p join osm_sungai s on ST_DWithin(p.geom_m, s.geom_m, 3000)
        )
        select lat5, lon5, way_id, jenis, nama, jarak_m,
               cast(round(ST_Y(g) * 1e5) AS BIGINT) AS s_lat5, cast(round(ST_X(g) * 1e5) AS BIGINT) AS s_lon5
        from dekat where urut = 1""")
    sungai = c.execute("select distinct s_lat5, s_lon5 from titik_sungai").fetchall()

    # 1. InaRISK, 40 titik per permintaan
    belum = [t for t in rumah if not c.execute("select 1 from inarisk where lat5=? and lon5=?", t).fetchone()]
    for kel in potong(belum, 40):
        geom = {"points": [[lo / 1e5, la / 1e5] for la, lo in kel], "spatialReference": {"wkid": 4326}}
        data = ambil(INARISK, {"geometry": json.dumps(geom), "geometryType": "esriGeometryMultipoint",
                               "returnFirstValueOnly": "true", "f": "json"}, kelompok="inarisk", jeda=2.0)
        if not data or "samples" not in data:
            print("  InaRISK tidak menjawab untuk satu kelompok, dilewati")
            continue
        for s in data["samples"]:
            la, lo = kel[s["locationId"]]
            nilai = float(s["value"]) if s.get("value") not in (None, "", "NoData") else None
            c.execute("insert or replace into inarisk values (?, ?, ?)", [la, lo, nilai])
    # 2 dan 3. ketinggian tanah, 100 titik per permintaan
    semua = set(rumah) | set(sungai)
    belum = [t for t in sorted(semua) if not c.execute("select 1 from elevasi where lat5=? and lon5=?", t).fetchone()]
    for kel in potong(belum, 100):
        data = ambil(ELEV, {"latitude": ",".join(f"{la / 1e5:.5f}" for la, lo in kel),
                            "longitude": ",".join(f"{lo / 1e5:.5f}" for la, lo in kel)}, kelompok="elevasi", jeda=1.5)
        if not data or "elevation" not in data:
            print("  layanan ketinggian tidak menjawab untuk satu kelompok, dilewati")
            continue
        c.executemany("insert or replace into elevasi values (?, ?, ?)",
                      [(la, lo, e) for (la, lo), e in zip(kel, data["elevation"])])
    print("inarisk:", c.execute("select count(*), count(indeks) from inarisk").fetchone(),
          "| elevasi:", c.execute("select count(*) from elevasi").fetchone()[0])


if __name__ == "__main__":
    main()
