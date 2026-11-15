-- Tabel akhir: satu baris per rumah, satu kolom per kriteria, dan status akhirnya.
-- Nilai kriteria: 'ya', 'tidak', 'belum jelas'. Rumah yang gugur di saringan isi iklan tidak dihitung petanya
-- (k_tol dan k_banjir = 'tidak dihitung').

CREATE OR REPLACE TABLE google_cek AS
SELECT * FROM read_csv('{{google_cek}}', delim = ';', quote = '', header = true,
    columns = {id_rumah:'VARCHAR', mnt_gerbang_google:'INTEGER', mnt_kantor_google:'INTEGER'});

CREATE OR REPLACE TABLE kandidat AS
WITH g AS (
    SELECT r.id_rumah, r.sumber, r.judul, r.rp, k.harga_kelas, r.lt, r.lb, r.lantai, r.kt, r.km, r.surat,
           r.lokasi, r.komplek, r.wilayah, k.wilayah_urut,
           coalesce(s.ketepatan, t.ketepatan) AS ketepatan, coalesce(s.lat, t.lat) AS lat, coalesce(s.lon, t.lon) AS lon,
           coalesce(s.sumber_titik, t.sumber_titik) AS sumber_titik,
           k.k_harga, k.k_lt, k.k_komplek, k.k_mobil, k.mobil_dasar, k.k_carport, k.carport_dasar,
           coalesce(s.k_tol, 'tidak dihitung') AS k_tol,
           s.gerbang, s.ruas_tol, s.mnt_gerbang_lancar, s.mnt_gerbang_pagi, s.km_gerbang,
           s.mnt_gerbang_ke_kantor_lancar, s.km_gerbang_ke_kantor,
           coalesce(s.k_banjir, 'tidak dihitung') AS k_banjir, s.banjir_dasar, s.banjir_kode_sumber, s.di_dki,
           s.inarisk, s.jarak_air_m, s.beda_tinggi_m,
           s.jarak_badan_tol_m, s.nama_tol_terdekat, s.bising_tol,
           k.rumah_baru, k.klaim_bebas_banjir, k.sebut_halaman, k.sisa_tanah_m2,
           r.tanggal, k.r123_status, k.r123_dicek, k.duplikat_dari, k.koreksi,
           -- rumah baru dari developer: reputasinya tidak bisa dibuktikan dari data, jadi selalu 'belum jelas'
           CASE WHEN k.rumah_baru THEN 'belum jelas' ELSE 'ya' END AS k_developer,
           gc.mnt_gerbang_google, gc.mnt_kantor_google,
           r.akun, r.link, r.n_foto, r.foto1, r.teks, r.catatan, r.dari, r.no_sumber
    FROM rumah r
    JOIN k_teks k USING (id_rumah)
    LEFT JOIN google_cek gc USING (id_rumah)
    LEFT JOIN titik t USING (id_rumah)
    LEFT JOIN k_spasial s USING (id_rumah)
),
h AS (
    SELECT *,
        list_filter([
            CASE WHEN k_harga = 'tidak' THEN 'harga (' || harga_kelas || ')' END,
            CASE WHEN k_lt = 'tidak' THEN 'luas tanah di bawah 36 m2' END,
            CASE WHEN k_komplek = 'tidak' THEN 'bukan di cluster atau komplek' END,
            CASE WHEN k_mobil = 'tidak' THEN 'mobil tidak sampai depan rumah' END,
            CASE WHEN k_carport = 'tidak' AND k_mobil <> 'tidak' THEN 'carport tidak ada dan tidak mungkin dibuat' END,
            CASE WHEN k_tol = 'tidak' THEN 'lebih dari 25 menit ke gerbang tol arah Senayan' END,
            CASE WHEN k_banjir = 'tidak' THEN 'ada catatan banjir' END
        ], lambda x: x IS NOT NULL) AS gugur,
        list_filter([
            CASE WHEN k_lt = 'belum jelas' THEN 'luas tanah tidak ditulis' END,
            CASE WHEN k_mobil = 'belum jelas' THEN 'akses mobil tidak disebut' END,
            CASE WHEN k_carport = 'belum jelas' THEN 'carport tidak disebut' END,
            CASE WHEN k_banjir = 'belum jelas' THEN 'banjir belum jelas' END,
            CASE WHEN k_developer = 'belum jelas' THEN 'rumah baru, reputasi developer belum terbukti' END,
            CASE WHEN ketepatan = 'perkiraan' THEN 'lokasi masih perkiraan' END,
            CASE WHEN ketepatan = 'tidak ada' OR lat IS NULL THEN 'tidak ada titik lokasi' END
        ], lambda x: x IS NOT NULL) AS perlu_cek
    FROM g
)
SELECT *,
    CASE WHEN len(gugur) > 0 THEN 'gugur'
         WHEN duplikat_dari IS NOT NULL THEN 'duplikat'
         WHEN len(perlu_cek) > 0 THEN 'perlu dicek'
         ELSE 'lolos semua' END AS status,
    array_to_string(gugur, '; ') AS gugur_karena,
    array_to_string(perlu_cek, '; ') AS yang_perlu_dicek,
    CASE wilayah_urut WHEN 1 THEN 'Jakarta' WHEN 2 THEN 'Pondok Gede, Jatiasih, Kota Bekasi'
         WHEN 3 THEN 'Bekasi lain (kabupaten atau belum jelas)' WHEN 4 THEN 'Depok' ELSE 'Bogor, Tangerang, lainnya' END AS kelompok_wilayah
FROM h;

-- Berapa rumah yang gugur di tiap kriteria.
-- "sendiri" = gagal di kriteria itu tanpa melihat kriteria lain (dihitung dari rumah yang lolos kriteria harga).
-- "berurutan" = sisa rumah setelah kriteria itu diterapkan sesudah kriteria-kriteria di atasnya.
CREATE OR REPLACE TABLE corong AS
WITH a AS (SELECT * FROM kandidat WHERE duplikat_dari IS NULL)
SELECT 1 AS urut, 'Semua rumah yang terkumpul' AS tahap, count(*) AS sisa, NULL::BIGINT AS gugur_sendiri FROM a
UNION ALL SELECT 2, 'Harga sampai 500 jt (bukan over kredit, harga ditulis)', count(*) FILTER (k_harga = 'ya'),
                 count(*) FILTER (k_harga = 'tidak') FROM a
UNION ALL SELECT 3, 'Luas tanah minimal 36 m2', count(*) FILTER (k_harga = 'ya' AND k_lt <> 'tidak'),
                 count(*) FILTER (k_harga = 'ya' AND k_lt = 'tidak') FROM a
UNION ALL SELECT 4, 'Di dalam cluster, one gate, atau komplek',
                 count(*) FILTER (k_harga = 'ya' AND k_lt <> 'tidak' AND k_komplek = 'ya'),
                 count(*) FILTER (k_harga = 'ya' AND k_komplek = 'tidak') FROM a
UNION ALL SELECT 5, 'Mobil sampai depan rumah',
                 count(*) FILTER (k_harga = 'ya' AND k_lt <> 'tidak' AND k_komplek = 'ya' AND k_mobil <> 'tidak'),
                 count(*) FILTER (k_harga = 'ya' AND k_mobil = 'tidak') FROM a
UNION ALL SELECT 6, 'Carport ada atau mungkin dibuat',
                 count(*) FILTER (k_harga = 'ya' AND k_lt <> 'tidak' AND k_komplek = 'ya' AND k_mobil <> 'tidak' AND k_carport <> 'tidak'),
                 count(*) FILTER (k_harga = 'ya' AND k_carport = 'tidak' AND k_mobil <> 'tidak') FROM a
UNION ALL SELECT 7, 'Paling lama 25 menit ke gerbang tol arah Senayan (pagi)',
                 count(*) FILTER (k_tol = 'ya'), count(*) FILTER (k_tol = 'tidak') FROM a
UNION ALL SELECT 8, 'Tidak ada catatan banjir',
                 count(*) FILTER (k_tol = 'ya' AND k_banjir <> 'tidak'), count(*) FILTER (k_tol <> 'tidak dihitung' AND k_banjir = 'tidak') FROM a
UNION ALL SELECT 9, 'Lolos semua dan tidak ada yang belum jelas', count(*) FILTER (status = 'lolos semua'), NULL FROM a
ORDER BY 1;
