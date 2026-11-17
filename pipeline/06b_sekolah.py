"""Langkah 6b: sekolah di sekitar rumah, dan jarak ke sekolah favorit.

Sumber sekolah:
  1. 13_rumah123/peta_sekolah/data/sekolah.js (peta sekolah, sudah berisi peringkat UTBK/TKA, biaya, sebutan Threads).
     Area peta itu hanya Jakarta Timur dan Bekasi bagian barat (bujur sampai 107,015).
  2. Dataset sekolah datawan-labs (parquet mentah yang sudah diunduh folder 13) untuk sekolah dalam 3 km dari rumah
     yang ada di luar area itu. Sekolah ini tidak punya peringkat.
Hanya SD, MI, SMP, MTs, SMA, MA, dan SPK (sekolah anak mulai SD Juli 2028). TK dan SMK tidak dimuat.

Tingkat favorit (dari peta sekolah folder 13):
  top  = paling favorit: SMA peringkat UTBK nasional 1 sampai 30, 3 besar SMA Kota Bekasi, SMP TKA teratas DKI
  fav  = favorit: SMA lain di daftar UTBK top 1000 atau daftar SMA terbaik Kota Bekasi, SMP dari daftar media
  ramai = tidak ada di daftar peringkat tetapi sering direkomendasikan di Threads (3 sebutan atau lebih)
SD tidak punya peringkat resmi, jadi SD paling banyak masuk "ramai".

Jarak:
  - jarak garis lurus untuk zonasi (Kota Bekasi dan Jawa Barat mengurutkan pendaftar dengan jarak garis lurus;
    DKI memakai wilayah RT dan kelurahan, bukan jarak), dihitung dengan SQL spasial
  - jarak jalan (OSRM) ke sekolah favorit dan paling favorit terdekat, untuk pengurutan
"""
from __future__ import annotations

import json
import math

import pyarrow.parquet as pq
import shapely

from umum import CACHE, ROOT, ambil, con

SEKOLAH_JS = ROOT / "13_rumah123" / "peta_sekolah" / "data" / "sekolah.js"
PARQUET = ROOT / "13_rumah123" / "peta_sekolah" / "data" / "raw" / "sekolah.parquet"
JENJANG = {"SD": "SD", "MI": "SD", "SPK SD": "SD", "SMP": "SMP", "MTs": "SMP", "SPK SMP": "SMP",
           "SMA": "SMA", "MA": "SMA", "SPK SMA": "SMA"}
OSRM = "https://router.project-osrm.org/table/v1/driving/"
SARING = """((k.k_harga = 'ya' and k.k_lt <> 'tidak' and k.k_komplek = 'ya' and k.k_mobil <> 'tidak' and k.k_carport <> 'tidak') or k.pilihan)"""


def km(a, b) -> float:
    p = math.pi / 180
    return 6371 * math.hypot((b[1] - a[1]) * p * math.cos((a[0] + b[0]) / 2 * p), (b[0] - a[0]) * p)


def peringkat(s: dict) -> str:
    if s.get("rnas"):
        return f"UTBK 2022 peringkat {s['rnas']} nasional"
    if s.get("rkota"):
        return f"peringkat {s['rkota']} SMA Kota Bekasi (UTBK)"
    if s.get("rdki"):
        return f"TKA SMP 2026 peringkat {s['rdki']} DKI"
    if s.get("sumber") == "media":
        return "daftar SMP favorit di media"
    return ""


def main() -> None:
    c = con()
    rumah = c.execute(f"""select distinct t.lat, t.lon, t.lat5, t.lon5 from titik t join k_teks k using (id_rumah)
                          where t.lat is not null and {SARING}""").fetchall()

    # 1. sekolah dari peta sekolah folder 13
    teks = SEKOLAH_JS.read_text(encoding="utf-8")
    kaya = json.loads(teks[teks.index("=") + 1:].rstrip().rstrip(";").replace("NaN", "null"))
    baris, ada = [], set()
    for s in kaya:
        g = JENJANG.get(s["jenjang"])
        if not g:
            continue
        tier = s.get("tier") or ("ramai" if (s.get("threads_n") or 0) >= 3 else "")
        baris.append({"npsn": s["npsn"], "nama": s["nama"], "jenjang": s["jenjang"], "g": g, "status": s["status"],
                      "akr": s.get("akr") or "", "tier": tier, "peringkat": peringkat(s),
                      "threads_n": s.get("threads_n") or 0, "kab": s.get("kab") or "",
                      "lat": s["lat"], "lon": s["lon"], "sumber_data": "peta sekolah"})
        ada.add(s["npsn"])

    # 2. sekolah lain dalam 3 km dari rumah di luar area peta sekolah
    df = pq.read_table(PARQUET, columns=["nama", "npsn", "kabupaten", "status", "jenjang", "akreditasi",
                                         "location", "location_status"]).to_pandas()
    df = df[df.jenjang.isin(JENJANG.keys()) & (df.location_status != "not-mapped") & ~df.npsn.isin(ada)]
    titik = shapely.from_wkb(df.location.values)
    df = df.assign(lon=shapely.get_x(titik), lat=shapely.get_y(titik)).drop(columns="location")
    df = df[df.lat.between(-6.75, -6.05) & df.lon.between(106.40, 107.35)]
    tambah = 0
    for r in df.itertuples():
        if any(abs(r.lat - h[0]) < 0.03 and abs(r.lon - h[1]) < 0.03 and km((r.lat, r.lon), h[:2]) <= 3 for h in rumah):
            baris.append({"npsn": r.npsn, "nama": r.nama, "jenjang": r.jenjang, "g": JENJANG[r.jenjang],
                          "status": (r.status or "").lower(), "akr": r.akreditasi or "", "tier": "", "peringkat": "",
                          "threads_n": 0, "kab": r.kabupaten or "", "lat": round(float(r.lat), 6),
                          "lon": round(float(r.lon), 6), "sumber_data": "datawan"})
            tambah += 1
    berkas = CACHE / "_sekolah.json"
    berkas.write_text(json.dumps(baris, ensure_ascii=False), encoding="utf-8")
    c.execute(f"""
        CREATE OR REPLACE TABLE sekolah AS
        SELECT row_number() OVER () AS id_sekolah, *,
               ST_Transform(ST_Point(lon, lat), 'EPSG:4326', 'EPSG:32748', true) AS geom_m
        FROM read_json('{berkas.as_posix()}', format = 'array',
            columns = {{npsn:'VARCHAR', nama:'VARCHAR', jenjang:'VARCHAR', g:'VARCHAR', status:'VARCHAR', akr:'VARCHAR',
                       tier:'VARCHAR', peringkat:'VARCHAR', threads_n:'INTEGER', kab:'VARCHAR', lat:'DOUBLE', lon:'DOUBLE',
                       sumber_data:'VARCHAR'}})""")
    print(f"sekolah: {len(baris) - tambah} dari peta sekolah, {tambah} tambahan di luar areanya")

    # 3. jarak jalan ke sekolah favorit (top + fav), OSRM table, hasil disimpan per pasangan
    fav = c.execute("select id_sekolah, lat, lon, tier from sekolah where tier in ('top', 'fav')").fetchall()
    c.execute("""CREATE TABLE IF NOT EXISTS jalan_sekolah (lat5 BIGINT, lon5 BIGINT, id_sekolah BIGINT, npsn VARCHAR,
                 meter DOUBLE, PRIMARY KEY (lat5, lon5, npsn))""")
    npsn = dict(c.execute("select id_sekolah, npsn from sekolah").fetchall())
    belum = [h for h in rumah if not c.execute("select 1 from jalan_sekolah where lat5=? and lon5=? limit 1",
                                               [h[2], h[3]]).fetchone()]
    per = 100 - len(fav)
    for i in range(0, len(belum), per):
        kel = belum[i:i + per]
        koor = [f"{h[1]:.5f},{h[0]:.5f}" for h in kel] + [f"{s[2]:.6f},{s[1]:.6f}" for s in fav]
        data = ambil(OSRM + ";".join(koor),
                     {"sources": ";".join(map(str, range(len(kel)))),
                      "destinations": ";".join(str(len(kel) + j) for j in range(len(fav))), "annotations": "distance"},
                     kelompok="osrm_sekolah", jeda=2.0)
        if not data or data.get("code") != "Ok":
            print("  OSRM gagal untuk satu kelompok, jalankan ulang nanti")
            continue
        c.executemany("insert or replace into jalan_sekolah values (?, ?, ?, ?, ?)",
                      [(h[2], h[3], s[0], npsn[s[0]], data["distances"][a][b])
                       for a, h in enumerate(kel) for b, s in enumerate(fav)])
        print(f"  jarak jalan ke sekolah favorit: {min(i + per, len(belum))}/{len(belum)} titik rumah")
    # id_sekolah bisa berubah antar run; kunci tetapnya npsn
    c.execute("update jalan_sekolah j set id_sekolah = s.id_sekolah from sekolah s where s.npsn = j.npsn")

    # 4. ringkasan per rumah
    c.execute(f"""
        CREATE OR REPLACE TABLE k_sekolah AS
        WITH p AS (select t.id_rumah, t.lat5, t.lon5, t.geom_m from titik t join k_teks k using (id_rumah)
                   where t.lat is not null and {SARING}),
        dekat AS (
            select p.id_rumah, s.*, ST_Distance(p.geom_m, s.geom_m) AS m
            from p join sekolah s on ST_DWithin(p.geom_m, s.geom_m, 3000)
        ),
        jalan AS (
            select p.id_rumah,
                   min(j.meter) filter (s.tier = 'top') AS top_m_jalan,
                   arg_min(s.nama, j.meter) filter (s.tier = 'top') AS top_nama,
                   min(j.meter) AS fav_m_jalan,
                   arg_min(s.nama, j.meter) AS fav_nama,
                   arg_min(s.tier, j.meter) AS fav_tier
            from p join jalan_sekolah j using (lat5, lon5) join sekolah s using (npsn)
            group by 1
        )
        select p.id_rumah,
               arg_min(d.nama, d.m) filter (d.g = 'SD' and d.status = 'negeri') AS sdn_nama,
               round(min(d.m) filter (d.g = 'SD' and d.status = 'negeri')) AS sdn_m,
               count(*) filter (d.g = 'SD' and d.m <= 2000) AS n_sd_2km,
               count(*) filter (d.g = 'SD' and d.status = 'negeri' and d.m <= 2000) AS n_sdn_2km,
               count(*) filter (d.tier in ('top', 'fav') and d.m <= 2000) AS n_fav_2km,
               string_agg(d.nama || ' (' || cast(cast(round(d.m / 100) / 10 AS DECIMAL(4, 1)) AS VARCHAR) || ' km)', ', '
                          ORDER BY d.m) filter (d.tier in ('top', 'fav') and d.m <= 2000) AS fav_2km,
               round(j.top_m_jalan / 1000, 1) AS km_top_jalan, j.top_nama,
               round(j.fav_m_jalan / 1000, 1) AS km_fav_jalan, j.fav_nama, j.fav_tier
        from p left join dekat d using (id_rumah) left join jalan j using (id_rumah)
        group by p.id_rumah, j.top_m_jalan, j.top_nama, j.fav_m_jalan, j.fav_nama, j.fav_tier""")
    print(c.execute("""select count(*), count(sdn_nama), round(median(sdn_m)), round(median(km_top_jalan), 1),
                              count(*) filter (n_fav_2km > 0) from k_sekolah""").fetchone(),
          "(rumah, punya SDN dalam 3 km, median m ke SDN, median km jalan ke sekolah paling favorit, ada favorit < 2 km)")


if __name__ == "__main__":
    main()
