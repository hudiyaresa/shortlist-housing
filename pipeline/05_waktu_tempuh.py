"""Langkah 5: waktu tempuh mobil lewat jalan dari tiap rumah ke gerbang tol arah Senayan.

Memakai layanan `table` server OSRM publik (router.project-osrm.org): satu permintaan berisi beberapa titik rumah
dan gerbang-gerbang terdekatnya, paling banyak 100 titik. Jawaban disimpan di cache/osrm_table, dan hasil per pasangan
(titik rumah, gerbang) masuk tabel `waktu_gerbang`, jadi titik yang sudah pernah dihitung tidak diminta lagi.

OSRM menghitung waktu tanpa macet. Faktor macet pagi ada di tabel `parameter` (lihat sql/06_parameter.sql).
Yang dihitung hanya rumah yang lolos saringan isi iklan (harga, luas tanah, komplek, akses mobil, carport).
"""
from __future__ import annotations

import math

from umum import DB, HERE, ambil, con, jalankan_sql

OSRM = "https://router.project-osrm.org/table/v1/driving/"
MAKS_TITIK = 100
GERBANG_PER_RUMAH = 10      # gerbang terdekat (garis lurus) yang dihitung untuk tiap titik rumah
MAKS_LURUS_KM = 18          # gerbang yang lebih jauh dari ini tidak mungkin terjangkau 25 menit


def km(a, b) -> float:
    p = math.pi / 180
    return 6371 * math.hypot((b[1] - a[1]) * p * math.cos((a[0] + b[0]) / 2 * p), (b[0] - a[0]) * p)


def main() -> None:
    c = con()
    jalankan_sql(c, "05_titik.sql", lokasi_manual=(HERE / "data" / "lokasi_manual.csv").as_posix())
    c.execute("""CREATE TABLE IF NOT EXISTS waktu_gerbang (
                     lat5 BIGINT, lon5 BIGINT, id_gerbang BIGINT, detik DOUBLE, meter DOUBLE,
                     PRIMARY KEY (lat5, lon5, id_gerbang))""")
    gerbang = c.execute("select id_gerbang, lat, lon from gerbang").fetchall()
    # titik unik milik rumah yang lolos saringan isi iklan dan belum punya hasil
    titik = c.execute("""
        select distinct t.lat5, t.lon5
        from titik t join k_teks k using (id_rumah)
        where t.lat is not null
          and ((k.k_harga = 'ya' and k.k_lt <> 'tidak' and k.k_komplek = 'ya' and k.k_mobil <> 'tidak' and k.k_carport <> 'tidak') or k.pilihan)
          and not exists (select 1 from waktu_gerbang w where w.lat5 = t.lat5 and w.lon5 = t.lon5)
        order by round(t.lon5 / 5000), t.lat5""").fetchall()
    print(f"{len(titik)} titik rumah belum punya waktu tempuh, {len(gerbang)} gerbang")

    # gerbang terdekat per titik
    dekat = {}
    for la, lo in titik:
        p = (la / 1e5, lo / 1e5)
        urut = sorted(((km(p, (g[1], g[2])), g[0]) for g in gerbang))[:GERBANG_PER_RUMAH]
        dekat[(la, lo)] = [gid for d, gid in urut if d <= MAKS_LURUS_KM]
    pos = {g[0]: (g[1], g[2]) for g in gerbang}

    # susun kelompok: rumah + gabungan gerbangnya <= 100 titik
    kelompok, rumah, tujuan = [], [], set()
    for t in titik:
        if not dekat[t]:
            c.execute("insert or ignore into waktu_gerbang values (?, ?, -1, null, null)", [t[0], t[1]])
            continue
        gabung = tujuan | set(dekat[t])
        if rumah and len(rumah) + 1 + len(gabung) > MAKS_TITIK:
            kelompok.append((rumah, sorted(tujuan)))
            rumah, gabung = [], set(dekat[t])
        rumah.append(t)
        tujuan = gabung
    if rumah:
        kelompok.append((rumah, sorted(tujuan)))

    for i, (rumah, tujuan) in enumerate(kelompok, 1):
        koordinat = [f"{lo / 1e5:.5f},{la / 1e5:.5f}" for la, lo in rumah] + \
                    [f"{pos[g][1]:.6f},{pos[g][0]:.6f}" for g in tujuan]
        url = OSRM + ";".join(koordinat)
        data = ambil(url, {"sources": ";".join(str(x) for x in range(len(rumah))),
                           "destinations": ";".join(str(len(rumah) + x) for x in range(len(tujuan))),
                           "annotations": "duration,distance"}, kelompok="osrm_table", jeda=2.0)
        if not data or data.get("code") != "Ok":
            print(f"  kelompok {i} gagal, dilewati (jalankan ulang untuk mencoba lagi)")
            continue
        baris = []
        for a, t in enumerate(rumah):
            for b, g in enumerate(tujuan):
                if g in dekat[t]:
                    baris.append((t[0], t[1], g, data["durations"][a][b], data["distances"][a][b]))
        c.executemany("insert or replace into waktu_gerbang values (?, ?, ?, ?, ?)", baris)
        print(f"  kelompok {i}/{len(kelompok)}: {len(rumah)} titik rumah x {len(tujuan)} gerbang")
    print("pasangan tersimpan:", c.execute("select count(*) from waktu_gerbang").fetchone()[0])


if __name__ == "__main__":
    main()
