"""Langkah 1: muat galeri rumah, poligon RT banjir DKI, dan data rumah123 ke db/shortlist.duckdb."""
import json
import re

from umum import CACHE, GALERI, HERE, R123_DB, R123_FOTO, RT_DKI, con, jalankan_sql


def pertahankan_id(c) -> None:
    """Jaga id rumah123 yang sudah dipakai di file isian tangan.

    Rumah yang diiklankan berkali-kali jadi satu kartu di galeri, dan iklan utamanya bisa berganti saat ada iklan
    ganda baru. id_rumah mengikuti iklan utama, jadi ikut berganti. Id yang sudah ditulis di data/*.csv atau di
    NOMOR (09_hasil.py) tetap dipakai selama iklan lamanya masih ada di daftar tautan kartu itu.
    """
    berkas = [*sorted((HERE / "data").glob("*.csv")), HERE / "09_hasil.py"]
    teks = "".join(f.read_text(encoding="utf-8") for f in berkas)
    dipakai = set(re.findall(r"R-hos[0-9]+", teks))
    ada = {r[0] for r in c.execute("SELECT id_rumah FROM rumah").fetchall()}
    for lama in sorted(dipakai - ada):
        kartu = c.execute("SELECT id_rumah FROM rumah WHERE sumber = 'rumah123' AND contains(link, ?)",
                          [f"-{lama[2:]}/"]).fetchall()
        if len(kartu) == 1 and kartu[0][0] not in dipakai:
            c.execute("UPDATE rumah SET id_rumah = ? WHERE id_rumah = ?", [lama, kartu[0][0]])
            print(f"id dipertahankan: {lama} (iklan utama di galeri sekarang {kartu[0][0]})")
        else:
            print(f"id di file isian tangan tidak ada lagi di galeri: {lama}")


def main() -> None:
    c = con()
    # rumah123_foto.json berbentuk {id: {...}}; diratakan dulu supaya bisa dibaca sebagai tabel
    status = [{"id": k, "status": v.get("status"), "cek": v.get("cek")}
              for k, v in json.loads(R123_FOTO.read_text(encoding="utf-8")).items()]
    rata = CACHE / "_r123_status.json"
    rata.write_text(json.dumps(status), encoding="utf-8")
    jalankan_sql(c, "01_muat.sql", galeri=GALERI.as_posix(), rt_dki=RT_DKI.as_posix(),
                 r123_status=rata.as_posix(), r123_db=R123_DB.as_posix())
    pertahankan_id(c)
    for t in ("rumah", "rt_dki", "r123_status", "r123_listing", "r123_harga"):
        print(f"{t:14s}", c.execute(f"select count(*) from {t}").fetchone()[0])
    print("id unik:", c.execute("select count(distinct id_rumah), count(*) from rumah").fetchone())
    print(c.execute("select sumber, count(*), count(*) filter (rp <= 500e6) from rumah group by 1").fetchall())


if __name__ == "__main__":
    main()
