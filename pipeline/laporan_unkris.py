"""Laporan sekali jalan: rumah di Jatiwaringin dan Jatibening, plus semua rumah dalam 5 km jalan dari Unkris.

Diminta 22 November 2026 untuk menyusun ulang daftar survei di sekitar Unkris dan LRT Jatibening Baru. Membaca
db/shortlist.duckdb (jalankan pipeline dulu), jarak dihitung lewat jalan (OSRM table, jawaban di-cache), bukan garis
lurus. Hasil: output/sekitar_unkris.md dan output/sekitar_unkris.csv.

    ..\\.venv\\Scripts\\python laporan_unkris.py [--km 5] [--maks-harga 860]
"""
from __future__ import annotations

import argparse
import csv
import math
import re

import duckdb

from umum import DB, HERE, ambil

UNKRIS = (-6.2633722, 106.9074161)        # Universitas Krisnadwipayana, Jaticempaka (Nominatim)
LRT_JB = (-6.2577476, 106.9279199)        # Stasiun LRT Jatibening Baru (OpenStreetMap, railway=station)
OSRM = "https://router.project-osrm.org/table/v1/driving/"
SEBUT = r"jati\s*waringin|jati\s*bening|unkris|krisnadwipayana|lrt\s*jati\s*bening"
OUT = HERE / "output"


def km_lurus(a, b) -> float:
    p = math.pi / 180
    return 6371 * math.hypot((b[1] - a[1]) * p * math.cos((a[0] + b[0]) / 2 * p), (b[0] - a[0]) * p)


def jarak_jalan(asal: tuple, titik: list[tuple]) -> list[tuple]:
    """(km, menit lancar) dari asal ke tiap titik; 99 tujuan per permintaan."""
    hasil = []
    for i in range(0, len(titik), 99):
        bagian = titik[i:i + 99]
        koor = ";".join(f"{lo:.6f},{la:.6f}" for la, lo in [asal, *bagian])
        j = ambil(OSRM + koor, {"sources": "0", "annotations": "distance,duration"}, kelompok="osrm_laporan")
        d, t = (j or {}).get("distances", [[None]])[0][1:], (j or {}).get("durations", [[None]])[0][1:]
        hasil += [(round(x / 1000, 1) if x is not None else None, round(y / 60) if y is not None else None)
                  for x, y in zip(d or [None] * len(bagian), t or [None] * len(bagian))]
    return hasil


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--km", type=float, default=5.0)
    ap.add_argument("--maks-harga", type=float, default=860)
    a = ap.parse_args()
    c = duckdb.connect(str(DB), read_only=True)
    rows = c.execute(f"""
        select id_rumah, sumber, rp / 1e6 jt, lt, lb, kt, lokasi, komplek, k_komplek, k_mobil, k_carport, k_banjir,
               ketepatan, lat, lon, status, gugur_karena, yang_perlu_dicek, cicil_pribadi, link, judul,
               lower(coalesce(lokasi, '') || ' ' || coalesce(judul, '') || ' ' || coalesce(teks, '')) t
        from kandidat
        where duplikat_dari is null and dicoret is null and coalesce(r123_status, '') <> 'hilang'
          and (rp is null or rp <= {a.maks_harga} * 1e6)
    """).fetchall()
    calon = []
    for r in rows:
        dekat = r[13] is not None and km_lurus(UNKRIS, (r[13], r[14])) <= a.km + 1.5
        sebut = re.search(SEBUT, r[-1]) is not None
        if dekat or sebut:
            calon.append(r)
    titik = [(r[13], r[14]) for r in calon if r[13] is not None]
    ke_unkris = dict(zip(titik, jarak_jalan(UNKRIS, titik)))
    ke_lrt = dict(zip(titik, jarak_jalan(LRT_JB, titik)))
    hasil = []
    for r in calon:
        p = (r[13], r[14]) if r[13] is not None else None
        ku, mu = ke_unkris.get(p, (None, None)) if p else (None, None)
        kl, ml = ke_lrt.get(p, (None, None)) if p else (None, None)
        nama_area = re.search(r"jati\s*waringin|jati\s*bening", (r[6] or "").lower())
        if not ((ku is not None and ku <= a.km) or nama_area):
            continue
        sebut = sorted(set(m.group(0).replace(" ", "") for m in re.finditer(r"unkris|krisnadwipayana|lrt\s*jati\s*bening", r[-1])))
        hasil.append({
            "harga_jt": round(r[2]) if r[2] else None, "lt": r[3], "lb": r[4], "kt": r[5], "lokasi": r[6],
            "komplek": r[7] or ("ya" if r[8] in ("ya", "diterima") else ""), "k_komplek": r[8], "mobil": r[9],
            "carport": r[10], "banjir": r[11], "titik": r[12], "km_unkris": ku, "mnt_unkris": mu,
            "km_lrt_jatibening": kl, "status": r[15], "gugur_karena": r[16], "perlu_dicek": r[17],
            "cicil_pribadi": r[18], "sebut": ", ".join(sebut), "sumber": r[1], "link": (r[19] or "").split(" | ")[0],
            "id_rumah": r[0],
        })
    hasil.sort(key=lambda x: (x["harga_jt"] is None, x["harga_jt"] or 0, x["km_unkris"] or 99))
    kolom = list(hasil[0].keys()) if hasil else []
    with open(OUT / "sekitar_unkris.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, kolom, delimiter=";")
        w.writeheader()
        w.writerows(hasil)

    def sel(v):
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        return "" if v is None else str(v).replace("|", "/")
    md = [f"# Rumah sekitar Unkris dan LRT Jatibening Baru", "",
          f"Dibuat dari db/shortlist.duckdb. Isinya rumah yang lokasinya Jatiwaringin atau Jatibening, ditambah semua rumah "
          f"yang jarak jalannya dari Unkris paling jauh {a.km:g} km (OSRM, tanpa macet). Harga sampai {a.maks_harga:g} jt, "
          f"rumah yang dicoret dan iklan rumah123 yang sudah hilang tidak ikut. Titik bertanda ~ masih perkiraan, jadi "
          f"jaraknya juga perkiraan.", "",
          "| Harga | LT/LB | Lokasi | Komplek | Mobil | Ke Unkris | Ke LRT JB | Status | Iklan |", "|---|---|---|---|---|---|---|---|---|"]
    for h in hasil:
        est = "~" if h["titik"] == "perkiraan" else ""
        md.append(f"| {sel(h['harga_jt'])} jt | {sel(h['lt'])}/{sel(h['lb'])} | {sel(h['lokasi'])[:45]} | {sel(h['komplek'])[:30]} "
                  f"| {sel(h['mobil'])} | {est}{sel(h['km_unkris'])} km | {est}{sel(h['km_lrt_jatibening'])} km | "
                  f"{sel(h['status'])}{(': ' + sel(h['gugur_karena'])) if h['gugur_karena'] else ''} | {h['link']} |")
    (OUT / "sekitar_unkris.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(len(calon), "calon,", len(hasil), "rumah ->", OUT / "sekitar_unkris.md")


if __name__ == "__main__":
    main()
