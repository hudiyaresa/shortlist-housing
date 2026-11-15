"""Langkah 1: muat galeri rumah, poligon RT banjir DKI, dan data rumah123 ke db/shortlist.duckdb."""
import json

from umum import CACHE, GALERI, R123_DB, R123_FOTO, RT_DKI, con, jalankan_sql


def main() -> None:
    c = con()
    # rumah123_foto.json berbentuk {id: {...}}; diratakan dulu supaya bisa dibaca sebagai tabel
    status = [{"id": k, "status": v.get("status"), "cek": v.get("cek")}
              for k, v in json.loads(R123_FOTO.read_text(encoding="utf-8")).items()]
    rata = CACHE / "_r123_status.json"
    rata.write_text(json.dumps(status), encoding="utf-8")
    jalankan_sql(c, "01_muat.sql", galeri=GALERI.as_posix(), rt_dki=RT_DKI.as_posix(),
                 r123_status=rata.as_posix(), r123_db=R123_DB.as_posix())
    for t in ("rumah", "rt_dki", "r123_status", "r123_listing", "r123_harga"):
        print(f"{t:14s}", c.execute(f"select count(*) from {t}").fetchone()[0])
    print("id unik:", c.execute("select count(distinct id_rumah), count(*) from rumah").fetchone())
    print(c.execute("select sumber, count(*), count(*) filter (rp <= 500e6) from rumah group by 1").fetchall())


if __name__ == "__main__":
    main()
