"""Langkah 7: jalankan SQL spasial per rumah (banjir, jarak badan tol, sungai, gerbang tercepat)."""
import sys

from umum import HERE, con, jalankan_sql

# Pengali waktu OSRM (tanpa macet) menjadi waktu pagi hari kerja. Dasarnya dijelaskan di shortlist_rumah.md.
FAKTOR_MACET = 2.4   # dari data/kalibrasi_macet.csv: 12 rute, Google Maps Senin 06.30 dibagi OSRM


def main() -> None:
    faktor = float(sys.argv[1]) if len(sys.argv) > 1 else FAKTOR_MACET
    c = con()
    jalankan_sql(c, "07_spasial.sql", banjir_bernama=(HERE / "data" / "banjir_bernama.csv").as_posix(),
                 faktor_macet=faktor)
    print("rumah dihitung:", c.execute("select count(*) from k_spasial").fetchone()[0])
    print("banjir:", c.execute("select k_banjir, count(*) from k_spasial group by 1").fetchall())
    print("tol:", c.execute("select k_tol, count(*) from k_spasial group by 1").fetchall())


if __name__ == "__main__":
    main()
