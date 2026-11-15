"""Hal yang dipakai semua script: lokasi file, koneksi DuckDB, dan pengambil data web yang menyimpan hasil.

Semua permintaan ke layanan publik lewat `ambil()`: hasilnya disimpan di cache/ (satu file per permintaan)
supaya run berikutnya tidak meminta ulang, dan ada jeda di antara permintaan yang benar-benar dikirim.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import duckdb
import requests

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DB = HERE / "db" / "shortlist.duckdb"
CACHE = HERE / "cache"
OUT = HERE / "output"
SQL = HERE / "sql"

GALERI = ROOT / "23_galeri_rumah" / "data" / "galeri_items.json"
R123_FOTO = ROOT / "23_galeri_rumah" / "data" / "rumah123_foto.json"
R123_DB = ROOT / "13_rumah123" / "output" / "rumah123.db"
RT_DKI = ROOT / "13_rumah123" / "peta" / "data" / "rt_dki.wkb.json"

# Kementerian Kehutanan, Gedung Manggala Wanabakti, Senayan
KANTOR = (-6.2062, 106.8001)
# Kotak Jabodetabek untuk data OpenStreetMap: selatan, barat, utara, timur
BBOX = (-6.75, 106.40, -6.05, 107.35)

UA = {"User-Agent": "shortlist-rumah/1.0 (analisa pribadi, permintaan berjeda dan disimpan)"}
_terakhir: dict[str, float] = {}


def con(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    DB.parent.mkdir(exist_ok=True)
    c = duckdb.connect(str(DB), read_only=read_only)
    c.execute("INSTALL spatial; LOAD spatial;")
    return c


def jalankan_sql(c: duckdb.DuckDBPyConnection, nama: str, **ganti: str) -> None:
    """Jalankan satu file di sql/. `{{kunci}}` di dalam file diganti dengan nilai yang diberikan."""
    teks = (SQL / nama).read_text(encoding="utf-8")
    for k, v in ganti.items():
        teks = teks.replace("{{" + k + "}}", str(v))
    c.execute(teks)


def ambil(url: str, params: dict | None = None, *, kelompok: str, jeda: float = 1.1, post: str | None = None,
          timeout: int = 120, ulang: int = 3) -> dict | list | None:
    """GET (atau POST kalau `post` diisi) yang hasil JSON-nya disimpan di cache/<kelompok>/<hash>.json."""
    kunci = hashlib.sha1(json.dumps([url, params, post], sort_keys=True).encode()).hexdigest()[:20]
    berkas = CACHE / kelompok / f"{kunci}.json"
    if berkas.exists():
        return json.loads(berkas.read_text(encoding="utf-8"))
    berkas.parent.mkdir(parents=True, exist_ok=True)
    host = url.split("/")[2]
    for coba in range(ulang):
        tunggu = jeda - (time.time() - _terakhir.get(host, 0))
        if tunggu > 0:
            time.sleep(tunggu)
        try:
            if post is None:
                r = requests.get(url, params=params, headers=UA, timeout=timeout)
            else:
                r = requests.post(url, data={"data": post}, headers=UA, timeout=timeout)
            _terakhir[host] = time.time()
            if r.status_code in (429, 502, 503, 504):
                print(f"  {host} menjawab {r.status_code}, menunggu {15 * (coba + 1)} detik")
                time.sleep(15 * (coba + 1))
                continue
            r.raise_for_status()
            data = r.json()
            berkas.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            return data
        except (requests.RequestException, ValueError) as e:
            _terakhir[host] = time.time()
            print(f"  gagal ({coba + 1}/{ulang}) {host}: {str(e)[:120]}")
            time.sleep(10 * (coba + 1))
    return None
