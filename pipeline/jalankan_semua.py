"""Jalankan semua langkah berurutan. Permintaan ke layanan publik yang sudah pernah dijawab diambil dari cache/.

    ..\.venv\Scripts\python jalankan_semua.py            # semua langkah
    ..\.venv\Scripts\python jalankan_semua.py 4          # mulai dari langkah 4 (setelah mengubah file di data/)
"""
import subprocess
import sys

LANGKAH = ["01_muat.py", "02_ambil_osm.py", "03_gerbang.py", "04_kriteria_teks.py", "05_waktu_tempuh.py",
           "06_banjir_luar_dki.py", "06b_sekolah.py", "07_spasial.py", "08_kandidat.py", "09_hasil.py", "10_halaman.py"]

mulai = int(sys.argv[1]) if len(sys.argv) > 1 else 1
for nama in LANGKAH[mulai - 1:]:
    print(f"\n=== {nama} ===", flush=True)
    if subprocess.run([sys.executable, "-X", "utf8", nama]).returncode != 0:
        sys.exit(f"{nama} gagal, langkah berikutnya tidak dijalankan")
