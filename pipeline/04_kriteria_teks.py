"""Langkah 4: kriteria dari isi iklan (harga, luas tanah, komplek, akses mobil, carport) plus koreksi manual."""
from umum import HERE, con, jalankan_sql


def main() -> None:
    c = con()
    jalankan_sql(c, "04_kriteria_teks.sql", koreksi_manual=(HERE / "data" / "koreksi_manual.csv").as_posix(),
                 pilihan=(HERE / "data" / "pilihan.csv").as_posix(),
                 dicoret=(HERE / "data" / "dicoret.csv").as_posix())
    print("harga:", c.execute("select harga_kelas, count(*) from k_teks group by 1 order by 2 desc").fetchall())
    print("lolos saringan isi iklan:", c.execute("""select count(*) from k_teks where k_harga = 'ya' and k_lt <> 'tidak'
        and k_komplek = 'ya' and k_mobil <> 'tidak' and k_carport <> 'tidak'""").fetchone()[0])


if __name__ == "__main__":
    main()
