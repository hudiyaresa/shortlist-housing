"""Langkah 3: pilih gardu tol yang benar-benar pintu MASUK dengan jalur ke arah Senayan.

OpenStreetMap mencampur gardu masuk, gardu keluar, dan gardu di badan tol dari semua arah. Untuk tiap gardu,
script ini meminta rute mobil dari titik gardu ke Kementerian Kehutanan (Manggala Wanabakti) ke server OSRM publik,
lalu mencocokkan tiap potongan rute dengan ruas tol di OSM. Sebuah gardu dihitung "mengarah ke Senayan" kalau:

  1. gardu ada di ramp (motorway_link), bukan di badan tol;
  2. rute dari gardu langsung berada di jalan tol (paling jauh 500 m dari gardu);
  3. rute tetap di jalan tol tanpa keluar lalu masuk lagi (jeda non-tol lebih dari 300 m = putar balik);
  4. panjang rute tidak lebih dari 1,5 x jarak lurus + 4 km (gardu yang arahnya menjauh akan gagal di sini);
  5. bagian tol dari rute itu minimal 1 km (gardu keluar hanya menyisakan ramp pendek).

Hasil: tabel `gardu_uji` (semua gardu dengan angka ujinya) dan `gerbang` (gardu yang lolos, digabung per 150 m).
Aturannya ada di sql/03_gerbang.sql supaya bisa diperiksa dan diubah.
"""
from __future__ import annotations

import json
import math

from umum import CACHE, KANTOR, ambil, con, jalankan_sql

OSRM = "https://router.project-osrm.org/route/v1/driving/{lon1:.6f},{lat1:.6f};{lon2:.6f},{lat2:.6f}"


def km(a: tuple[float, float], b: tuple[float, float]) -> float:
    p = math.pi / 180
    x = (b[1] - a[1]) * p * math.cos((a[0] + b[0]) / 2 * p)
    y = (b[0] - a[0]) * p
    return 6371 * math.hypot(x, y)


def urai_polyline(teks: str) -> list[tuple[int, int]]:
    """Polyline OSRM (presisi 5) menjadi daftar (lat, lon) dalam satuan 1e-5 derajat."""
    titik, i, lat, lon = [], 0, 0, 0
    while i < len(teks):
        for sumbu in (0, 1):
            geser = hasil = 0
            while True:
                b = ord(teks[i]) - 63
                i += 1
                hasil |= (b & 0x1F) << geser
                geser += 5
                if b < 0x20:
                    break
            d = ~(hasil >> 1) if hasil & 1 else hasil >> 1
            if sumbu == 0:
                lat += d
            else:
                lon += d
        titik.append((lat, lon))
    return titik


def titik_tol() -> set[tuple[int, int]]:
    """Semua titik sudut ruas tol dan ramp dari OSM, dibulatkan ke 1e-5 derajat (sekitar 1 m)."""
    s: set[tuple[int, int]] = set()
    for r in json.loads((CACHE / "overpass" / "_ruas.json").read_text(encoding="utf-8")):
        for pasangan in r["wkt"][12:-1].split(", "):
            lon, lat = pasangan.split(" ")
            s.add((round(float(lat) * 1e5), round(float(lon) * 1e5)))
    return s


def di_tol(geom: str, tol: set[tuple[int, int]]) -> bool:
    """Potongan rute dihitung jalan tol kalau minimal 70% titik sudutnya berimpit (selisih <= 1e-5 derajat)
    dengan titik sudut ruas tol di OSM. Server OSRM publik tidak mengirim kelas jalan, jadi dicocokkan sendiri.
    Jalan biasa di bawah atau di samping tol layang punya titik sudut sendiri, jadi tidak ikut terhitung."""
    titik = urai_polyline(geom)
    if not titik:
        return False
    kena = sum(1 for la, lo in titik
               if any((la + a, lo + b) in tol for a in (-1, 0, 1) for b in (-1, 0, 1)))
    return kena / len(titik) >= 0.7


def uji(lat: float, lon: float, tol_set: set[tuple[int, int]]) -> dict | None:
    url = OSRM.format(lon1=lon, lat1=lat, lon2=KANTOR[1], lat2=KANTOR[0])
    data = ambil(url, {"steps": "true", "overview": "false"}, kelompok="osrm_gardu", jeda=1.1)
    if not data or data.get("code") != "Ok":
        return None
    rute = data["routes"][0]
    potong = [(s["distance"], s["duration"], di_tol(s.get("geometry", ""), tol_set), s.get("name", ""), s.get("ref", ""))
              for s in rute["legs"][0]["steps"] if s["distance"] > 0]
    # jarak sebelum masuk tol, panjang tol, jeda non-tol terpanjang di tengah, sisa setelah tol terakhir
    pra = tol = jeda_maks = jeda = 0.0
    t_tol = 0.0
    mulai = False
    nama_tol = ""
    for d, t, m, nama, ref in potong:
        if m:
            if not mulai:
                mulai = True
            if not nama_tol and nama.lower().startswith("jalan tol"):
                nama_tol = nama
            jeda_maks, jeda = max(jeda_maks, jeda), 0.0
            tol += d
            t_tol += t
        elif not mulai:
            pra += d
        else:
            jeda += d
    return {"snap_m": data["waypoints"][0]["distance"], "pra_m": pra, "tol_m": tol, "jeda_m": jeda_maks,
            "akhir_m": jeda, "rute_m": rute["distance"], "rute_dtk": rute["duration"], "tol_dtk": t_tol,
            "lurus_m": km((lat, lon), KANTOR) * 1000, "ruas_pertama": nama_tol}


def main() -> None:
    c = con(read_only=True)
    gardu = c.execute("select node_id, lat, lon from osm_gardu order by node_id").fetchall()
    c.close()      # database tidak dikunci selama menunggu jawaban server rute
    hasil = []
    tol_set = titik_tol()
    for i, (nid, lat, lon) in enumerate(gardu, 1):
        h = uji(lat, lon, tol_set)
        if h:
            hasil.append({"node_id": nid, **h})
        if i % 50 == 0:
            print(f"  {i}/{len(gardu)} gardu diuji")
    berkas = CACHE / "_gardu_uji.json"
    berkas.write_text(json.dumps(hasil), encoding="utf-8")
    c = con()
    jalankan_sql(c, "03_gerbang.sql", gardu_uji=berkas.as_posix())
    print(c.execute("select status, count(*) from gardu_uji group by 1 order by 2 desc").fetchall())
    print("gerbang arah Senayan:", c.execute("select count(*) from gerbang").fetchone()[0])


if __name__ == "__main__":
    main()
