"""Langkah 8: gabungkan semua kriteria menjadi tabel `kandidat` dan hitung berapa rumah gugur di tiap kriteria."""
from umum import HERE, con, jalankan_sql


def main() -> None:
    c = con()
    jalankan_sql(c, "08_kandidat.sql", google_cek=(HERE / "data" / "google_cek.csv").as_posix())
    for r in c.execute("select tahap, sisa, gugur_sendiri from corong order by urut").fetchall():
        print(f"{r[1]:5d}  {r[0]}" + (f"  (gugur di kriteria ini: {r[2]})" if r[2] is not None else ""))
    print(c.execute("select status, count(*) from kandidat group by 1 order by 2 desc").fetchall())


if __name__ == "__main__":
    main()
