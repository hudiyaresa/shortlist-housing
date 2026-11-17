-- Kriteria dari peta untuk rumah yang lolos saringan isi iklan: banjir, jarak ke badan tol, sungai, gerbang tol.
-- Semua jarak dihitung di UTM 48S (EPSG:32748), satuannya meter.
-- Masukan: titik, k_teks, rt_dki, osm_tol_ruas, osm_sungai, titik_sungai, elevasi, inarisk, waktu_gerbang, gerbang,
--          data/banjir_bernama.csv ({{banjir_bernama}}), dan faktor macet pagi ({{faktor_macet}}).

CREATE OR REPLACE TABLE parameter AS
SELECT * FROM (VALUES
    ('faktor_macet_pagi',   {{faktor_macet}}, 'pengali waktu OSRM (tanpa macet) menjadi waktu berangkat kerja pagi'),
    ('maks_menit_gerbang',  25.0, 'batas waktu tempuh ke gerbang tol arah Senayan, menit'),
    ('tol_sangat_dekat_m', 150.0, 'jarak ke badan tol yang dianggap sangat dekat (bising)'),
    ('tol_dekat_m',        300.0, 'jarak ke badan tol yang dianggap dekat'),
    ('inarisk_tinggi',     0.666, 'indeks bahaya banjir InaRISK di atas ini = kelas tinggi'),
    ('inarisk_sedang',     0.333, 'indeks bahaya banjir InaRISK di atas ini = kelas sedang')
) AS t(nama, nilai, keterangan);

CREATE OR REPLACE TABLE banjir_bernama AS
SELECT * FROM read_csv('{{banjir_bernama}}', delim = ';', quote = '', header = true, all_varchar = true);

CREATE OR REPLACE TABLE k_spasial AS
WITH p AS (
    SELECT t.*, lower(coalesce(r.judul, '') || ' | ' || coalesce(r.lokasi, '') || ' | ' || coalesce(r.komplek, '')) AS nama_lokasi,
           lower(coalesce(r.teks, '')) AS badan_iklan
    FROM titik t JOIN k_teks k USING (id_rumah) JOIN rumah r USING (id_rumah)
    WHERE t.lat IS NOT NULL
      AND ((k.k_harga = 'ya' AND k.k_lt <> 'tidak' AND k.k_komplek = 'ya' AND k.k_mobil <> 'tidak' AND k.k_carport <> 'tidak') OR k.pilihan)
),
-- RT tempat titik berada (DKI saja). Kalau titik jatuh di celah antar poligon, pakai RT terdekat dalam 60 m.
rt_isi AS (
    SELECT p.id_rumah, r.kel, r.kec, r.rw, r.rt, r.kejadian, r.hari, r.kelas,
           row_number() OVER (PARTITION BY p.id_rumah ORDER BY ST_Distance(r.geom_m, p.geom_m), r.kejadian DESC) AS urut
    FROM p JOIN rt_dki r ON ST_DWithin(r.geom_m, p.geom_m, 60)
),
-- RT di sekitar titik: berapa yang tercatat banjir, dan RT banjir terdekat
rt_sekitar AS (
    SELECT p.id_rumah,
           count(*) FILTER (ST_DWithin(r.geom_m, p.geom_m, 500)) AS n_rt_500,
           count(*) FILTER (r.kejadian > 0 AND ST_DWithin(r.geom_m, p.geom_m, 500)) AS n_banjir_500,
           count(*) FILTER (r.kejadian > 0 AND ST_DWithin(r.geom_m, p.geom_m, 150)) AS n_banjir_150,
           round(min(ST_Distance(r.geom_m, p.geom_m)) FILTER (r.kejadian > 0)) AS rt_banjir_terdekat_m
    FROM p JOIN rt_dki r ON ST_DWithin(r.geom_m, p.geom_m, 1500)
    GROUP BY 1
),
-- badan jalan tol terdekat (motorway) dan ramp terdekat (motorway_link)
tol AS (
    SELECT p.id_rumah,
           round(min(ST_Distance(p.geom_m, t.geom_m)) FILTER (t.jenis = 'motorway')) AS jarak_badan_tol_m,
           arg_min(t.nama, ST_Distance(p.geom_m, t.geom_m)) FILTER (t.jenis = 'motorway') AS nama_tol_terdekat,
           round(min(ST_Distance(p.geom_m, t.geom_m))) AS jarak_tol_atau_ramp_m
    FROM p JOIN osm_tol_ruas t ON ST_DWithin(p.geom_m, t.geom_m, 6000)
    GROUP BY 1
),
-- sungai/kali terdekat dan beda tinggi tanah rumah terhadap titik sungai itu
sungai AS (
    SELECT p.id_rumah, s.jenis AS jenis_air, nullif(s.nama, '') AS nama_air, round(s.jarak_m) AS jarak_air_m,
           e1.mdpl AS tinggi_rumah_m, round(e1.mdpl - e2.mdpl, 1) AS beda_tinggi_m
    FROM p JOIN titik_sungai s USING (lat5, lon5)
    LEFT JOIN elevasi e1 ON e1.lat5 = p.lat5 AND e1.lon5 = p.lon5
    LEFT JOIN elevasi e2 ON e2.lat5 = s.s_lat5 AND e2.lon5 = s.s_lon5
),
-- perumahan yang pernah diberitakan banjir: cocok di judul/lokasi/nama komplek, atau hanya disebut di badan iklan
bernama AS (
    SELECT p.id_rumah,
           string_agg(DISTINCT b.nama || ' (' || b.kejadian || coalesce(', sampai ' || b.tinggi_maks_cm || ' cm', '') || ')', '; ')
               FILTER (b.tingkat = 'perumahan' AND regexp_matches(p.nama_lokasi, b.pola)) AS banjir_nama_utama,
           string_agg(DISTINCT b.nama || ' (' || b.kejadian || ')', '; ')
               FILTER (NOT (b.tingkat = 'perumahan' AND regexp_matches(p.nama_lokasi, b.pola))) AS banjir_nama_lain,
           string_agg(DISTINCT b.sumber, ' ') AS banjir_kode_sumber
    FROM p JOIN banjir_bernama b ON regexp_matches(p.nama_lokasi, b.pola) OR regexp_matches(p.badan_iklan, b.pola)
    GROUP BY 1
),
-- gerbang tol arah Senayan dengan waktu tempuh terpendek
gerbang_cepat AS (
    SELECT p.id_rumah,
           arg_min(g.id_gerbang, w.detik) AS id_gerbang,
           arg_min(g.nama, w.detik) AS gerbang,
           arg_min(g.ruas_pertama, w.detik) AS ruas_tol,
           round(min(w.detik) / 60, 1) AS mnt_gerbang_lancar,
           round(arg_min(w.meter, w.detik) / 1000, 1) AS km_gerbang,
           arg_min(g.mnt_ke_kantor_lancar, w.detik) AS mnt_gerbang_ke_kantor_lancar,
           arg_min(g.km_ke_kantor, w.detik) AS km_gerbang_ke_kantor
    FROM p JOIN waktu_gerbang w USING (lat5, lon5) JOIN gerbang g USING (id_gerbang)
    WHERE w.detik IS NOT NULL
    GROUP BY 1
),
gabung AS (
    SELECT p.id_rumah, p.lat, p.lon, p.ketepatan, p.sumber_titik,
           (ri.id_rumah IS NOT NULL) AS di_dki,
           ri.kel, ri.kec, ri.rw, ri.rt, ri.kejadian AS rt_kejadian, ri.hari AS rt_hari,
           rs.n_rt_500, rs.n_banjir_500, rs.n_banjir_150, rs.rt_banjir_terdekat_m,
           i.indeks AS inarisk,
           s.jenis_air, s.nama_air, s.jarak_air_m, s.tinggi_rumah_m, s.beda_tinggi_m,
           b.banjir_nama_utama, b.banjir_nama_lain, b.banjir_kode_sumber,
           t.jarak_badan_tol_m, t.nama_tol_terdekat, t.jarak_tol_atau_ramp_m,
           g.id_gerbang, g.gerbang, g.ruas_tol, g.mnt_gerbang_lancar, g.km_gerbang,
           g.mnt_gerbang_ke_kantor_lancar, g.km_gerbang_ke_kantor,
           round(g.mnt_gerbang_lancar * (SELECT nilai FROM parameter WHERE nama = 'faktor_macet_pagi'), 0) AS mnt_gerbang_pagi
    FROM p
    LEFT JOIN rt_isi ri ON ri.id_rumah = p.id_rumah AND ri.urut = 1
    LEFT JOIN rt_sekitar rs ON rs.id_rumah = p.id_rumah
    LEFT JOIN inarisk i ON i.lat5 = p.lat5 AND i.lon5 = p.lon5
    LEFT JOIN sungai s ON s.id_rumah = p.id_rumah
    LEFT JOIN bernama b ON b.id_rumah = p.id_rumah
    LEFT JOIN tol t ON t.id_rumah = p.id_rumah
    LEFT JOIN gerbang_cepat g ON g.id_rumah = p.id_rumah
)
SELECT *,
    -- BANJIR: 'ya' = tidak ada tanda banjir di data, 'tidak' = ada catatan banjir, 'belum jelas' = perlu dicek
    CASE
        WHEN banjir_nama_utama IS NOT NULL THEN 'tidak'
        WHEN di_dki AND ketepatan <> 'perkiraan' AND rt_kejadian > 0 THEN 'tidak'
        WHEN di_dki AND ketepatan <> 'perkiraan' AND n_banjir_150 > 0 THEN 'belum jelas'
        WHEN di_dki AND ketepatan <> 'perkiraan' THEN 'ya'
        WHEN di_dki AND n_banjir_500 >= 0.5 * n_rt_500 THEN 'tidak'
        WHEN di_dki AND n_banjir_500 = 0 AND banjir_nama_lain IS NULL THEN 'ya'
        WHEN di_dki THEN 'belum jelas'
        WHEN ketepatan <> 'perkiraan' AND inarisk > (SELECT nilai FROM parameter WHERE nama = 'inarisk_tinggi') THEN 'tidak'
        WHEN inarisk > (SELECT nilai FROM parameter WHERE nama = 'inarisk_sedang') THEN 'belum jelas'
        WHEN banjir_nama_lain IS NOT NULL THEN 'belum jelas'
        WHEN jarak_air_m <= 150 AND beda_tinggi_m < 3 THEN 'belum jelas'
        ELSE 'ya'
    END AS k_banjir,
    CASE
        WHEN banjir_nama_utama IS NOT NULL THEN 'perumahan ini pernah diberitakan banjir: ' || banjir_nama_utama
        WHEN di_dki AND ketepatan <> 'perkiraan' AND rt_kejadian > 0
            THEN 'RT ' || rt || '/RW ' || rw || ' ' || kel || ' tercatat ' || rt_kejadian || ' kejadian banjir 2021 sampai 2024 (BPBD DKI)'
        WHEN di_dki AND ketepatan <> 'perkiraan' AND n_banjir_150 > 0
            THEN 'RT ' || rt || '/RW ' || rw || ' ' || kel || ' tanpa catatan, tetapi ' || n_banjir_150 || ' RT dalam 150 m tercatat banjir (BPBD DKI)'
        WHEN di_dki AND ketepatan <> 'perkiraan'
            THEN 'RT ' || rt || '/RW ' || rw || ' ' || kel || ' tanpa catatan banjir 2021 sampai 2024 (BPBD DKI); RT banjir terdekat '
                 || coalesce(cast(cast(rt_banjir_terdekat_m AS INTEGER) AS VARCHAR) || ' m', 'lebih dari 1,5 km')
        WHEN di_dki
            THEN 'titik perkiraan: ' || n_banjir_500 || ' dari ' || n_rt_500 || ' RT dalam 500 m tercatat banjir 2021 sampai 2024 (BPBD DKI)'
                 || coalesce('; iklan menyebut ' || banjir_nama_lain, '')
        ELSE 'luar DKI: indeks bahaya banjir BNPB ' || coalesce(replace(cast(round(inarisk, 2) AS VARCHAR), '.', ','), 'tidak ada (di luar zona bahaya)')
             || coalesce('; ' || coalesce(nama_air, jenis_air) || ' ' || cast(cast(jarak_air_m AS INTEGER) AS VARCHAR) || ' m, rumah '
                         || replace(cast(beda_tinggi_m AS VARCHAR), '.', ',') || ' m di atasnya', '')
             || coalesce('; iklan menyebut ' || banjir_nama_lain, '')
             || CASE WHEN ketepatan = 'perkiraan' THEN ' (titik perkiraan)' ELSE '' END
    END AS banjir_dasar,
    -- WAKTU ke gerbang tol arah Senayan
    CASE WHEN mnt_gerbang_pagi IS NULL THEN 'tidak'
         WHEN mnt_gerbang_pagi <= (SELECT nilai FROM parameter WHERE nama = 'maks_menit_gerbang') THEN 'ya'
         ELSE 'tidak' END AS k_tol,
    -- jarak ke badan tol (bukan kriteria wajib)
    CASE WHEN jarak_badan_tol_m < (SELECT nilai FROM parameter WHERE nama = 'tol_sangat_dekat_m') THEN 'sangat dekat'
         WHEN jarak_badan_tol_m < (SELECT nilai FROM parameter WHERE nama = 'tol_dekat_m') THEN 'dekat'
         ELSE 'cukup jauh' END AS bising_tol
FROM gabung;
