"""Laporan sekali jalan: semua rumah di DKI Jakarta dengan akses mobil, sampai 800 jt, diurutkan menurut jarak ke
gerbang tol terdekat yang mengarah ke Senayan, lalu jarak ke Manggala Wanabakti.

Diminta 22 November 2026. Membaca db/shortlist.duckdb (jalankan pipeline dulu). Rumah yang belum punya hitungan
gerbang (pipeline hanya menghitung rumah yang lolos saringan isi iklan) dihitung di sini dengan cara yang sama dengan
05_waktu_tempuh.py: OSRM table ke 10 gerbang terdekat, waktu pagi = waktu lancar x faktor macet pagi. Jarak langsung
ke Manggala juga lewat OSRM (rute tercepat, boleh lewat tol). Hasil: output/ringkasan_jakarta_800jt.md dan .csv.

    ..\\.venv\\Scripts\\python ringkasan_jakarta.py [--maks-harga 800]
"""
from __future__ import annotations

import argparse
import csv
import math
import re

import duckdb

from umum import DB, HERE, KANTOR, ambil

OSRM = "https://router.project-osrm.org/table/v1/driving/"
GERBANG_PER_RUMAH = 10
MAKS_LURUS_KM = 18
OUT = HERE / "output"
CICIL = [
    ("cicil langsung ke developer", r"cicil\w*\s*(langsung\s*)?(ke\s*)?(developer|dev\b|pengembang)|in[- ]?house|"
                                    r"kredit\s*(langsung\s*)?(ke\s*)?developer|angsuran\s*(ke\s*)?developer"),
    ("syariah tanpa bank", r"syariah[^.\n]{0,30}(tanpa|non)[- ]?bank|tanpa\s*bank|non[- ]?bank|tanpa\s*bi\s*checking|"
                           r"tanpa\s*riba|tanpa\s*denda|tanpa\s*sita"),
    ("cicil pribadi / ke pemilik", r"cicil\w*\s*(pribadi|ke\s*pemilik|ke\s*owner|langsung\s*ke\s*pemilik)|"
                                   r"cicilan?\s*flat|angsuran\s*flat"),
    ("cash bertahap", r"cash\s*bertahap|cash\s*tempo|bayar\s*bertahap"),
]


def km_lurus(a, b) -> float:
    p = math.pi / 180
    return 6371 * math.hypot((b[1] - a[1]) * p * math.cos((a[0] + b[0]) / 2 * p), (b[0] - a[0]) * p)


def tabel(asal: list[tuple], tujuan: list[tuple]) -> tuple[list, list]:
    koor = ";".join(f"{lo:.6f},{la:.6f}" for la, lo in [*asal, *tujuan])
    n = len(asal)
    j = ambil(OSRM + koor, {"sources": ";".join(map(str, range(n))),
                            "destinations": ";".join(map(str, range(n, n + len(tujuan)))),
                            "annotations": "distance,duration"}, kelompok="osrm_laporan")
    return (j or {}).get("durations") or [], (j or {}).get("distances") or []


def gerbang_terdekat(titik: list[tuple], gerbang: list[tuple]) -> dict:
    """titik -> (nama, ruas, detik, meter, mnt_ke_kantor_lancar, km_ke_kantor) gerbang dengan waktu tersingkat."""
    dekat = {}
    for p in titik:
        urut = sorted((km_lurus(p, (g[2], g[3])), k) for k, g in enumerate(gerbang))[:GERBANG_PER_RUMAH]
        dekat[p] = [k for d, k in urut if d <= MAKS_LURUS_KM]
    hasil, kelompok, rumah, tuju = {}, [], [], set()
    for p in titik:
        if not dekat[p]:
            continue
        gabung = tuju | set(dekat[p])
        if rumah and len(rumah) + len(gabung) > 100:
            kelompok.append((rumah, sorted(tuju)))
            rumah, gabung = [], set(dekat[p])
        rumah.append(p)
        tuju = gabung
    if rumah:
        kelompok.append((rumah, sorted(tuju)))
    for rumah, tuju in kelompok:
        dur, dist = tabel(rumah, [(gerbang[k][2], gerbang[k][3]) for k in tuju])
        for i, p in enumerate(rumah):
            pilihan = [(dur[i][j], dist[i][j], tuju[j]) for j in range(len(tuju))
                       if tuju[j] in dekat[p] and dur and dur[i][j] is not None]
            if pilihan:
                d, m, k = min(pilihan)
                g = gerbang[k]
                hasil[p] = (g[1], g[4], d, m, g[5], g[6])
    return hasil


def ke_kantor(titik: list[tuple]) -> dict:
    hasil = {}
    for i in range(0, len(titik), 99):
        bagian = titik[i:i + 99]
        dur, dist = tabel(bagian, [KANTOR])
        for k, p in enumerate(bagian):
            if dur and dur[k][0] is not None:
                hasil[p] = (dur[k][0], dist[k][0])
    return hasil


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--maks-harga", type=float, default=800)
    a = ap.parse_args()
    c = duckdb.connect(str(DB), read_only=True)
    faktor = float(c.execute("select nilai from parameter where nama = 'faktor_macet_pagi'").fetchall()[0][0])
    gerbang = c.execute("select id_gerbang, nama, lat, lon, ruas_pertama, mnt_ke_kantor_lancar, km_ke_kantor "
                        "from gerbang").fetchall()
    rows = c.execute(f"""
        select id_rumah, sumber, rp / 1e6, lt, lb, kt, lantai, surat, lokasi, wilayah, komplek, k_komplek, k_carport,
               ketepatan, lat, lon, gerbang, ruas_tol, mnt_gerbang_lancar, km_gerbang, mnt_gerbang_ke_kantor_lancar,
               km_gerbang_ke_kantor, status, gugur_karena, k_banjir, cicil_pribadi, rumah_baru, link,
               lower(coalesce(judul, '') || ' ' || coalesce(teks, '') || ' ' || coalesce(catatan, '')) t, judul
        from kandidat
        where duplikat_dari is null and dicoret is null and coalesce(r123_status, '') <> 'hilang'
          and rp <= {a.maks_harga} * 1e6 and k_mobil = 'ya'
          and (wilayah like 'Jakarta%' or (di_dki and wilayah = 'Belum jelas'))
    """).fetchall()
    kurang = sorted({(r[14], r[15]) for r in rows if r[14] is not None and r[16] is None})
    hitung = gerbang_terdekat(kurang, gerbang)
    langsung = ke_kantor(sorted({(r[14], r[15]) for r in rows if r[14] is not None}))
    hasil = []
    for r in rows:
        p = (r[14], r[15]) if r[14] is not None else None
        if r[16] is not None:
            nama, ruas, mnt_l, km_g, mnt_kk, km_kk = r[16], r[17], r[18], r[19], r[20], r[21]
        elif p in hitung:
            nama, ruas, d, m, mnt_kk, km_kk = hitung[p]
            mnt_l, km_g = round(d / 60, 1), round(m / 1000, 1)
        else:
            nama = ruas = mnt_l = km_g = mnt_kk = km_kk = None
        lg = langsung.get(p)
        teks = r[28] or ""
        cicil = [n for n, pola in CICIL if re.search(pola, teks)]
        # kolom cicil_pribadi pipeline: '', 'cash bertahap ke penjual', 'cicil langsung tanpa bunga (disebut di iklan)'
        if (r[25] or "").startswith("cicil langsung tanpa bunga"):
            cicil.insert(0, "cicil langsung tanpa bunga")
        elif (r[25] or "").startswith("cash bertahap"):
            cicil.append("cash bertahap")
        if r[10]:
            komplek = r[10]
        elif r[11] in ("ya", "diterima"):
            komplek = "cluster/komplek"
        else:
            komplek = "tidak" if r[11] == "tidak" else "belum jelas"
        hasil.append({
            "harga_jt": round(r[2]), "lt": r[3], "lb": r[4], "kt": r[5], "lantai": r[6], "surat": r[7],
            "lokasi": r[8], "wilayah": r[9], "cluster_komplek": komplek,
            "carport": r[12], "rumah_baru": "ya" if r[26] else "", "cicil": ", ".join(dict.fromkeys(cicil)),
            "gerbang_tol": nama, "ruas_tol": ruas, "km_ke_gerbang": km_g,
            "mnt_ke_gerbang_pagi": round(mnt_l * faktor) if mnt_l is not None else None,
            "km_ke_manggala_lewat_gerbang": round(km_g + km_kk, 1) if km_g is not None and km_kk is not None else None,
            "km_ke_manggala_rute_osrm": round(lg[1] / 1000, 1) if lg else None,
            "mnt_ke_manggala_pagi": round(lg[0] / 60 * faktor) if lg else None,
            "titik": r[13], "banjir": r[24], "status_shortlist": r[22], "gugur_karena": r[23], "sumber": r[1],
            "link": (r[27] or "").split(" | ")[0], "judul": r[29], "id_rumah": r[0],
        })
    hasil.sort(key=lambda x: (x["km_ke_gerbang"] is None, x["km_ke_gerbang"] or 0, x["km_ke_manggala_rute_osrm"] or 99))
    with open(OUT / "ringkasan_jakarta_800jt.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, list(hasil[0].keys()), delimiter=";")
        w.writeheader()
        w.writerows(hasil)

    def sel(v):
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        return "" if v is None else str(v).replace("|", "/")
    n_cicil = sum(1 for h in hasil if h["cicil"] and h["cicil"] != "cash bertahap")
    md = ["# Rumah di Jakarta dengan akses mobil, sampai 800 jt", "",
          f"{len(hasil)} rumah dari db/shortlist.duckdb, diurutkan menurut jarak jalan ke gerbang tol terdekat yang "
          f"rutenya menerus ke Senayan, lalu jarak ke Manggala Wanabakti. Menit pagi = waktu OSRM tanpa macet x "
          f"{faktor:g} (faktor dari 12 rute Google Maps, 15 November). Titik bertanda ~ masih perkiraan dari teks iklan. "
          f"Kolom cicil diisi dari teks iklan: {n_cicil} rumah menyebut cicilan langsung ke penjual atau developer, "
          f"syariah tanpa bank, atau cicilan flat. \"Cash bertahap\" sering hanya pilihan standar di formulir situs iklan, "
          f"jadi tanyakan dulu. Ini bahan diskusi "
          f"keluarga, bukan penilaian properti.", "",
          "| # | Harga | LT/LB | Lokasi | Cluster/komplek | Gerbang tol (km, menit pagi) | Ke Manggala (km, menit pagi) | Cicil | Status | Iklan |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for i, h in enumerate(hasil, 1):
        est = "~" if h["titik"] == "perkiraan" else ""
        g = f"{sel(h['gerbang_tol'])} ({est}{sel(h['km_ke_gerbang'])} km, {sel(h['mnt_ke_gerbang_pagi'])} mnt)" if h["gerbang_tol"] else ""
        m = f"{est}{sel(h['km_ke_manggala_rute_osrm'])} km, {sel(h['mnt_ke_manggala_pagi'])} mnt" if h["km_ke_manggala_rute_osrm"] else ""
        st = sel(h["status_shortlist"]) + (f": {sel(h['gugur_karena'])}" if h["gugur_karena"] else "")
        md.append(f"| {i} | {h['harga_jt']} jt | {sel(h['lt'])}/{sel(h['lb'])} | {sel(h['lokasi'])[:40]} | "
                  f"{sel(h['cluster_komplek'])[:30]} | {g} | {m} | {sel(h['cicil'])} | {st} | {h['link']} |")
    (OUT / "ringkasan_jakarta_800jt.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(len(rows), "rumah;", len(kurang), "titik baru dihitung gerbangnya;", len(hitung), "dapat gerbang ->",
          OUT / "ringkasan_jakarta_800jt.md")


if __name__ == "__main__":
    main()
