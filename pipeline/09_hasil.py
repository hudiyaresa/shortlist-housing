"""Langkah 9: tulis file hasil dari tabel `kandidat`.

  output/kandidat.csv         semua rumah, satu kolom per kriteria (tanpa isi iklan, tanpa catatan pribadi)
  output/foto/                thumbnail foto post Threads untuk rumah yang lolos kriteria harga (maks 3 per rumah)
  output/corong.csv           berapa rumah yang tersisa dan gugur di tiap kriteria
  output/gerbang_tol.csv      gerbang tol yang terbukti pintu masuk ke arah Senayan
  output/peta_shortlist.html  peta Leaflet satu file, bisa dibuka langsung di browser

shortlist_rumah.md ditulis tangan dari hasil run 15 November 2026. Kalau data berubah, angka di sana perlu
dicocokkan lagi dengan kandidat.csv dan corong.csv.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import PureWindowsPath

from PIL import Image

from umum import GALERI_OUT, HERE, OCR_FOTO, OUT, con

# Nomor rumah di shortlist_rumah.md, peta, dan tabel dihitung ulang tiap run (hitung_nomor):
#   1. rumah yang lolos semua kriteria di wilayah kalian (Jakarta, Pondok Gede, Jatiasih, Kota Bekasi), urut waktu ke
#      gerbang tol (angka Google Maps kalau sudah dicek, selain itu model)
#   2. cadangan yang dipilih tangan (CADANGAN), urut seperti di daftar
#   3. rumah kiriman kalian (data/pilihan.csv) yang belum bernomor, urut seperti di file itu
# Rumah di data/dicoret.csv dan iklan ganda tidak diberi nomor, jadi rumah di bawahnya otomatis naik.
CADANGAN = ["T-911ec913", "T-6db17fd0", "T-38b721b8", "T-975592fb", "T-8692d453"]
NOMOR: dict[str, int] = {}

NAMA = {"T-553d3b77": "Kansa Residence, Kramat Jati", "R-hos16335281": "Mini cluster Kemangsari, Jaticempaka",
        "T-13703e88": "Cluster Prima Pedurenan 5, Jatiluhur", "T-0b921701": "Pondok Indah Jatisari, Jatiasih",
        "R-hos19252497": "Dukuh Zamrud, Kota Legenda", "T-911ec913": "Kodau V Ambarapura, Jatimekar",
        "T-6db17fd0": "Komplek Bintara Jaya", "T-38b721b8": "Raisya Pro Residence 9, Kranggan",
        "T-975592fb": "Raisya Pro Residence 11, Jatimurni", "T-8692d453": "Cluster kecil di Cilangkap",
        "T-3c78d524": "Cluster Aldira 2, Jatisari", "T-a1892808": "Cluster mini di Kalisari",
        "T-46ef6797": "Cluster Arsa 2, Pesanggrahan", "T-bf7661b0": "Lavender Crown Residence IV, Jatiasih",
        "T-ae7e9090": "Komplek Alastua, Semanan", "T-ccab0a9b": "Cluster di Pekayon",
        "T-15a345ee": "AS Cluster Jatisari", "T-6489b9a9": "Kavling Azzahra 1, Cilangkap",
        "T-12f53c23": "Rumah indent di Cipayung", "T-3fa7085b": "Jl. Sonton, Lenteng Agung",
        "T-97341809": "Rumah di Pondok Kelapa, Duren Sawit"}

KOLOM = """id_rumah, status, kelompok_wilayah,
    CASE sumber WHEN 'Threads' THEN 'Threads' ELSE sumber END AS sumber,
    cast(rp / 1e6 AS INTEGER) AS harga_jt, harga_kelas, lt AS luas_tanah_m2, lb AS luas_bangunan_m2, lantai, surat,
    coalesce(nullif(komplek, ''), '') AS komplek, lokasi, ketepatan AS ketepatan_lokasi, sumber_titik,
    round(lat, 5) AS lat, round(lon, 5) AS lon,
    k_harga, k_lt, k_komplek, k_mobil, mobil_dasar, k_carport, carport_dasar, k_tol, k_banjir, k_developer,
    gerbang AS gerbang_tol, ruas_tol, mnt_gerbang_pagi AS menit_ke_gerbang_pagi, mnt_gerbang_lancar AS menit_ke_gerbang_tanpa_macet,
    km_gerbang AS km_ke_gerbang, mnt_gerbang_google AS menit_ke_gerbang_google, mnt_kantor_google AS menit_ke_kantor_google,
    banjir_dasar, banjir_kode_sumber, round(inarisk, 2) AS indeks_bahaya_banjir_bnpb,
    cast(jarak_badan_tol_m AS INTEGER) AS jarak_badan_tol_m, nama_tol_terdekat, bising_tol,
    gugur_karena, yang_perlu_dicek, duplikat_dari, koreksi AS koreksi_manual,
    tanggal AS tanggal_iklan, r123_dicek AS rumah123_terakhir_dicek,
    cicil_pribadi, pilihan AS pilihan_kalian, km_ke_manggala,
    sdn_nama AS sd_negeri_terdekat, cast(sdn_m AS INTEGER) AS m_ke_sd_negeri, n_sd_2km, n_sdn_2km,
    n_fav_2km AS n_sekolah_favorit_2km, fav_2km AS sekolah_favorit_2km,
    km_top_jalan AS km_ke_sekolah_paling_favorit, top_nama AS sekolah_paling_favorit_terdekat,
    km_fav_jalan AS km_ke_sekolah_favorit, fav_nama AS sekolah_favorit_terdekat, link"""


DIBUAT = "20 November 2026"
GALERI_PUBLIK = "https://hudiyaresa.github.io/house-listing-gallery/#map"
HP = re.compile(r"(?<![0-9A-Za-z])(?:\+?62|0)8\d[\d\s.\-]{7,13}\d(?![0-9A-Za-z])")
# di foto, nomor sering ditulis renggang ("+62 812 ..."), jadi polanya dibuat lebih longgar
HP_FOTO = re.compile(r"(?:\+?62[\s.\-]?|0)8\d[\d\s.\-]{6,13}\d")
MAKS_FOTO = 3      # foto per rumah di tabel dan peta
FOTO_PX = 360      # sisi terpanjang thumbnail yang disalin ke output/foto/


def pilih_foto(c) -> dict[str, list[str]]:
    """id_rumah -> sampai MAKS_FOTO alamat foto, untuk rumah yang lolos kriteria harga.

    rumah123: alamat thumbnail di CDN rumah123 (tidak disalin). Threads: thumbnail galeri folder 23 dikecilkan ke
    output/foto/. Foto Threads yang menurut OCR memuat nomor HP dibuang, foto yang penuh tulisan (brosur) ditaruh
    paling belakang, dan foto yang belum di-OCR tidak dipakai. Foto dari catatan survei tidak pernah dipakai.
    """
    ocr: dict[tuple[str, ...], tuple[bool, int]] = {}
    if OCR_FOTO.exists():
        for baris in OCR_FOTO.read_text(encoding="utf-8").splitlines():
            if baris.strip():
                o = json.loads(baris)
                ada_hp = bool(HP_FOTO.search(o.get("text") or ""))
                ocr[PureWindowsPath(o["path"]).parts[-2:]] = (ada_hp, o.get("lines") or 0)   # kunci: (kode post, file)
    tujuan = OUT / "foto"
    tujuan.mkdir(parents=True, exist_ok=True)
    hasil: dict[str, list[str]] = {}
    dipakai: set[str] = set()
    buang_hp = belum_ocr = 0
    for id_rumah, sumber, daftar in c.execute("""
            SELECT r.id_rumah, r.sumber, r.foto_daftar FROM rumah r JOIN kandidat k USING (id_rumah)
            WHERE k.k_harga = 'ya' AND k.duplikat_dari IS NULL AND len(r.foto_daftar) > 0
              AND r.sumber <> 'Catatan survei' ORDER BY r.id_rumah""").fetchall():
        if sumber == "rumah123":
            hasil[id_rumah] = [f["t"] for f in daftar[:MAKS_FOTO] if (f["t"] or "").startswith("https://")]
            continue
        calon = []
        for urut, f in enumerate(daftar):
            info = ocr.get(PureWindowsPath(f["f"] or "").parts[-2:])   # kunci: (kode post, nama file)
            if info is None:
                belum_ocr += 1
            elif info[0]:
                buang_hp += 1
            else:
                calon.append((info[1] > 5, urut, f["t"]))
        pilih = []
        for _, _, kecil in sorted(calon)[:MAKS_FOTO]:
            asal = GALERI_OUT / kecil
            if not asal.exists():
                continue
            nama = asal.name
            if not (tujuan / nama).exists():
                with Image.open(asal) as im:
                    im = im.convert("RGB")
                    im.thumbnail((FOTO_PX, FOTO_PX))
                    im.save(tujuan / nama, "JPEG", quality=72, optimize=True)
            dipakai.add(nama)
            pilih.append("foto/" + nama)
        if pilih:
            hasil[id_rumah] = pilih
    for lama in tujuan.glob("*.jpg"):      # foto rumah yang sudah tidak ada di daftar
        if lama.name not in dipakai:
            lama.unlink()
    print(f"foto: {len(hasil)} rumah berfoto, {len(dipakai)} thumbnail Threads di output/foto "
          f"({sum(p.stat().st_size for p in tujuan.glob('*.jpg')) / 1e6:.1f} MB), "
          f"{buang_hp} foto dibuang karena memuat nomor HP, {belum_ocr} belum di-OCR")
    return hasil


def tulis_csv(nama: str, cur, foto: dict[str, list[str]] | None = None) -> int:
    # nomor HP yang terbawa dari teks iklan tidak ditulis ke file hasil
    baris = [[HP.sub("[nomor]", x) if isinstance(x, str) else x for x in r] for r in cur.fetchall()]
    kepala = [d[0] for d in cur.description]
    if foto is not None:               # kolom pertama = id_rumah
        kepala.append("foto")
        baris = [r + [" | ".join(foto.get(r[0], []))] for r in baris]
    with open(OUT / nama, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(kepala)
        w.writerows(baris)
    return len(baris)


def hitung_nomor(c) -> dict[str, int]:
    """Isi NOMOR (id_rumah -> nomor). Lihat penjelasan di atas CADANGAN."""
    NOMOR.clear()
    aktif = {r[0] for r in c.execute(
        "SELECT id_rumah FROM kandidat WHERE duplikat_dari IS NULL AND status <> 'dicoret'").fetchall()}
    urut = [r[0] for r in c.execute("""
        SELECT id_rumah FROM kandidat
        WHERE status = 'lolos semua' AND wilayah_urut <= 2 AND duplikat_dari IS NULL
        ORDER BY coalesce(mnt_gerbang_google, mnt_gerbang_pagi), mnt_gerbang_pagi, rp""").fetchall()]
    urut += [i for i in CADANGAN if i in aktif]
    kode = [b.split(";")[0] for b in (HERE / "data" / "pilihan.csv").read_text(encoding="utf-8").splitlines()[1:] if b]
    rows = c.execute("SELECT id_rumah, link FROM kandidat WHERE pilihan AND duplikat_dari IS NULL").fetchall()
    for k in kode:
        cocok = [i for i, ln in rows if k in (ln or "")]
        if not cocok:
            print(f"pilihan {k}: belum ada di data")
        elif cocok[0] in aktif:
            urut.append(cocok[0])
    for i in urut:
        if i in aktif and i not in NOMOR:
            NOMOR[i] = len(NOMOR) + 1
    return NOMOR


def main() -> None:
    OUT.mkdir(exist_ok=True)
    c = con(read_only=True)
    hitung_nomor(c)
    foto = pilih_foto(c)
    n = tulis_csv("kandidat.csv", c.execute(f"""
        SELECT {KOLOM} FROM kandidat
        ORDER BY CASE status WHEN 'lolos semua' THEN 1 WHEN 'perlu dicek' THEN 2 WHEN 'duplikat' THEN 3 ELSE 4 END,
                 wilayah_urut, mnt_gerbang_pagi NULLS LAST, rp, id_rumah"""), foto)
    print("kandidat.csv:", n, "baris")
    tulis_csv("corong.csv", c.execute("SELECT urut, tahap, sisa, gugur_sendiri FROM corong ORDER BY urut"))
    tulis_csv("gerbang_tol.csv", c.execute("""
        SELECT nama, ruas_pertama AS ruas_tol, round(lat, 5) AS lat, round(lon, 5) AS lon, km_ke_kantor,
               mnt_ke_kantor_lancar AS menit_ke_kantor_tanpa_macet, jumlah_gardu
        FROM gerbang ORDER BY nama"""))

    # ---- data peta ----
    kol = [d[0] for d in c.execute(f"SELECT {KOLOM} FROM kandidat LIMIT 0").description]
    rumah = []
    for r in c.execute(f"""SELECT {KOLOM} FROM kandidat
                           WHERE (k_harga = 'ya' OR pilihan) AND lat IS NOT NULL AND duplikat_dari IS NULL
                             AND NOT (sumber = 'Catatan survei' AND coalesce(link, '') = '')""").fetchall():
        d = dict(zip(kol, r))
        rumah.append({
            "id": d["id_rumah"], "no": NOMOR.get(d["id_rumah"]), "st": d["status"], "wil": d["kelompok_wilayah"],
            "sb": d["sumber"], "jt": d["harga_jt"], "lt": d["luas_tanah_m2"], "lb": d["luas_bangunan_m2"],
            "srt": d["surat"], "nm": NAMA.get(d["id_rumah"]) or HP.sub("[nomor]", (d["komplek"] or d["lokasi"] or ""))[:70],
            "lok": HP.sub("[nomor]", d["lokasi"] or "")[:80],
            "tp": d["ketepatan_lokasi"], "la": d["lat"], "lo": d["lon"],
            "gt": d["gerbang_tol"], "mg": d["menit_ke_gerbang_pagi"], "mgg": d["menit_ke_gerbang_google"],
            "mk": d["menit_ke_kantor_google"], "bj": d["k_banjir"], "bd": d["banjir_dasar"],
            "tol": d["jarak_badan_tol_m"], "cp": d["carport_dasar"], "mb": d["mobil_dasar"],
            "gg": d["gugur_karena"], "pc": d["yang_perlu_dicek"], "ln": (d["link"] or "").split(" | ")[0],
            "ft": foto.get(d["id_rumah"], []),
            "pl": bool(d["pilihan_kalian"]), "cc": d["cicil_pribadi"] or "", "kmk": d["km_ke_manggala"],
            "sdn": d["sd_negeri_terdekat"], "msdn": d["m_ke_sd_negeri"], "kmt": d["km_ke_sekolah_paling_favorit"],
            "tn": d["sekolah_paling_favorit_terdekat"], "kmf": d["km_ke_sekolah_favorit"],
            "fn": d["sekolah_favorit_terdekat"],
        })
    gerbang = [{"nm": r[0], "la": round(r[1], 5), "lo": round(r[2], 5), "ruas": r[3]}
               for r in c.execute("SELECT nama, lat, lon, ruas_pertama FROM gerbang").fetchall()]
    tol = [json.loads(r[0])["coordinates"] for r in c.execute("""
        SELECT ST_AsGeoJSON(ST_ReducePrecision(ST_Simplify(geom, 0.00015), 0.00001))
        FROM osm_tol_ruas WHERE jenis = 'motorway'""").fetchall()]
    banjir = [{"g": json.loads(r[0])["coordinates"], "k": r[1], "n": r[2]} for r in c.execute("""
        SELECT ST_AsGeoJSON(ST_ReducePrecision(ST_SimplifyPreserveTopology(geom, 0.00008), 0.00001)),
               kejadian, 'RT ' || rt || '/RW ' || rw || ' ' || kel
        FROM rt_dki WHERE kejadian > 0 AND ST_GeometryType(geom) = 'POLYGON'
          AND ST_X(ST_Centroid(geom)) > 106.82 AND ST_Y(ST_Centroid(geom)) < -6.15""").fetchall()]
    # sekolah: semua yang dalam 2,5 km dari rumah yang tampil (belum gugur atau pilihan kalian), plus semua sekolah favorit
    tampil = [(h["la"], h["lo"]) for h in rumah if h["st"] != "gugur" or h["pl"]]
    sekolah = []
    for r in c.execute("""SELECT nama, g, jenjang, status, akr, tier, peringkat, lat, lon FROM sekolah""").fetchall():
        if r[5] in ("top", "fav") or any(abs(r[7] - a) < 0.02 and abs(r[8] - b) < 0.02 for a, b in tampil):
            sekolah.append({"nm": r[0], "g": r[1], "j": r[2], "n": r[3] == "negeri", "a": r[4] or "", "t": r[5] or "",
                            "pk": r[6] or "", "la": round(r[7], 5), "lo": round(r[8], 5)})
    data = {"rumah": rumah, "gerbang": gerbang, "tol": tol, "banjir": banjir, "sekolah": sekolah,
            "galeri": GALERI_PUBLIK, "n_galeri": c.execute("SELECT count(*) FROM rumah").fetchone()[0],
            "dibuat": DIBUAT}
    templat = (HERE / "peta_templat.html").read_text(encoding="utf-8")
    (OUT / "peta_shortlist.html").write_text(
        templat.replace("/*DATA*/null", json.dumps(data, ensure_ascii=False, separators=(",", ":"))), encoding="utf-8")
    print(f"peta_shortlist.html: {len(sekolah)} sekolah,", end=" ")
    print(f"{len(rumah)} rumah, {len(gerbang)} gerbang, {len(tol)} ruas tol, {len(banjir)} RT banjir,",
          round((OUT / "peta_shortlist.html").stat().st_size / 1e6, 2), "MB")


if __name__ == "__main__":
    main()
