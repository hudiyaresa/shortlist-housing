-- Kriteria yang dibaca dari isi iklan (bukan dari peta): harga, luas tanah, komplek, akses mobil, carport, rumah baru.
-- Tiap kriteria punya tiga nilai: 'ya', 'tidak', 'belum jelas'. Hanya 'tidak' yang menggugurkan.
-- Semua pola ada di sini supaya bisa diperiksa dan diubah; contoh pemeriksaannya ada di bawah file ini.

CREATE OR REPLACE TABLE k_teks AS
WITH t AS (
    SELECT r.*,
           lower(coalesce(judul, '') || ' \n ' || coalesce(teks, '') || ' \n ' || coalesce(fitur, '') || ' \n '
                 || coalesce(lokasi, '') || ' \n ' || coalesce(catatan, '')) AS isi,
           l.carport AS r123_carport, l.garasi AS r123_garasi, l.tipe_agen, l.first_seen, l.last_seen,
           s.status AS r123_status, s.dicek AS r123_dicek
    FROM rumah r
    LEFT JOIN r123_listing l USING (id_rumah)
    LEFT JOIN r123_status s USING (id_rumah)
),
pola AS (
    SELECT *,
        -- harga iklan bukan harga rumah: over kredit, take over, hanya DP
        regexp_matches(isi, 'over\s*kredit|overkredit|oper\s*kredit|take\s*over|lanjut(kan)?\s*(cicilan|angsuran)') AS over_kredit,
        -- mobil jelas tidak bisa sampai depan rumah
        regexp_matches(isi, 'mobil\s*(tidak|tdk|ga|gak|gk|nggak|ngga|blm|belum)\s*(bisa\s*)?(masuk|lewat)'
                         || '|(tidak|tdk|ga|gak|gk|nggak|ngga|blm|belum)\s*(bisa\s*)?(masuk|muat|lewat|akses)\s*mobil'
                         || '|non\s*akses\s*mobil|parkir\s*mobil\s*(di\s*)?luar|mobil\s*parkir\s*(di\s*)?(luar|depan\s*gang)'
                         || '|motor\s*only|(hanya|cuma|khusus)\s*(bisa\s*)?(akses\s*|masuk\s*|muat\s*|lewat\s*)?(motor|mtr)\b') AS mobil_tidak,
        -- akses disebut motor saja
        regexp_matches(isi, 'akses\s*(jalan\s*|jln\s*|jl\s*)?(motor|mtr)\b|(jalan|jln|jl)\s*(motor|mtr)\b|gang\s*motor|masuk\s*gang') AS motor_saja,
        -- mobil disebut bisa
        regexp_matches(isi, '(akses|jalan|jln|jl\.?|masuk|muat|lebar|lewat|row|papasan|simpangan)[^.\n]{0,30}(mobil|mbl)\b'
                         || '|[1-9]\s*(mobil|mbl)\b|(satu|dua|tiga)\s*mobil|mobil\s*(bisa\s*)?(masuk|lewat|papasan)|row\s*jalan') AS mobil_ya,
        regexp_matches(isi, 'carport|car\s*port|carpot|carpor\b|garasi|garase|parkir(an)?\s*mobil') AS sebut_carport,
        regexp_matches(isi, '(tanpa|belum\s*ada|blm\s*ada|tidak\s*ada|tdk\s*ada|non|no)\s*(carport|car\s*port|garasi)') AS carport_tidak,
        regexp_matches(isi, 'teras|halaman\s*(depan|luas)|taman\s*depan|sisa\s*tanah|lahan\s*parkir|tanah\s*lebih') AS sebut_teras,
        -- tanda rumah baru yang dijual developer (bukan rumah bekas)
        regexp_matches(isi, 'inden|indent|ready\s*sto[ck]k?|siap\s*bangun|launching|tahap\s*(ke\s*)?[0-9]'
                         || '|(sisa|tersisa)\s*[0-9]+\s*unit|booking|free\s*(biaya|bphtb|ajb|shm)'
                         || '|mulai\s*(dari\s*)?[0-9]+\s*(jt|juta)|developer|develover|request\s*layout|custom\s*denah') AS tanda_baru,
        regexp_matches(isi, 'bebas\s*banjir|anti\s*banjir|tidak\s*(pernah\s*)?banjir|no\s*banjir|free\s*banjir') AS klaim_bebas_banjir,
        regexp_matches(isi, 'halaman\s*(depan|luas)|taman\s*depan|bisa\s*(tanam|berkebun)|taman\s*(kecil|mungil|belakang)') AS sebut_halaman
    FROM t
)
SELECT
    id_rumah,
    -- harga
    CASE WHEN rp IS NULL THEN 'tanpa harga'
         WHEN over_kredit THEN 'over kredit'
         WHEN rp < 100e6 THEN 'bukan harga rumah'
         WHEN rp <= 400e6 THEN 'sampai 400 jt'
         WHEN rp <= 500e6 THEN '400 sampai 500 jt'
         ELSE 'di atas 500 jt' END AS harga_kelas,
    CASE WHEN rp IS NULL OR over_kredit OR rp < 100e6 OR rp > 500e6 THEN 'tidak' ELSE 'ya' END AS k_harga,
    -- luas tanah
    CASE WHEN lt IS NULL THEN 'belum jelas' WHEN lt >= 36 THEN 'ya' ELSE 'tidak' END AS k_lt,
    -- cluster / komplek (penanda dari komplek.py di folder 23)
    CASE WHEN coalesce(komplek, '') <> '' THEN 'ya' ELSE 'tidak' END AS k_komplek,
    -- akses mobil
    CASE WHEN mobil_tidak THEN 'tidak'
         WHEN mobil_ya OR (sebut_carport AND NOT carport_tidak) OR coalesce(r123_carport, 0) + coalesce(r123_garasi, 0) > 0 THEN 'ya'
         WHEN motor_saja THEN 'tidak'
         ELSE 'belum jelas' END AS k_mobil,
    CASE WHEN mobil_tidak THEN 'iklan menyebut mobil tidak bisa masuk'
         WHEN mobil_ya THEN 'iklan menyebut akses mobil'
         WHEN (sebut_carport AND NOT carport_tidak) OR coalesce(r123_carport, 0) + coalesce(r123_garasi, 0) > 0 THEN 'tersirat dari carport atau garasi'
         WHEN motor_saja THEN 'iklan menyebut akses motor atau masuk gang'
         ELSE 'tidak disebut' END AS mobil_dasar,
    -- carport: ada, atau masih mungkin dibuat
    CASE WHEN mobil_tidak OR (motor_saja AND NOT mobil_ya) THEN 'tidak'
         WHEN (sebut_carport AND NOT carport_tidak) OR coalesce(r123_carport, 0) + coalesce(r123_garasi, 0) > 0 THEN 'ya'
         WHEN sebut_teras OR coalesce(lantai, 1) >= 2 OR (lt - lb / greatest(coalesce(lantai, 1), 1)) >= 12 THEN 'ya'
         ELSE 'belum jelas' END AS k_carport,
    CASE WHEN mobil_tidak OR (motor_saja AND NOT mobil_ya) THEN 'mobil tidak bisa masuk'
         WHEN (sebut_carport AND NOT carport_tidak) OR coalesce(r123_carport, 0) + coalesce(r123_garasi, 0) > 0 THEN 'ada (disebut di iklan)'
         WHEN sebut_teras THEN 'mungkin dibuat (ada teras atau halaman depan)'
         WHEN coalesce(lantai, 1) >= 2 THEN 'mungkin dibuat (rumah 2 lantai)'
         WHEN (lt - lb / greatest(coalesce(lantai, 1), 1)) >= 12 THEN 'mungkin dibuat (sisa tanah '
              || cast(round(lt - lb / greatest(coalesce(lantai, 1), 1)) AS INTEGER) || ' m2)'
         ELSE 'tidak disebut' END AS carport_dasar,
    tanda_baru AS rumah_baru,
    klaim_bebas_banjir, sebut_halaman,
    round(lt - lb / greatest(coalesce(lantai, 1), 1)) AS sisa_tanah_m2,
    -- wilayah menurut urutan yang kalian sebut
    CASE WHEN wilayah LIKE 'Jakarta%' THEN 1
         WHEN wilayah LIKE 'Pondok Gede%' OR wilayah = 'Kota Bekasi' THEN 2
         WHEN wilayah LIKE 'Bekasi (kota/kab%' OR wilayah = 'Kab. Bekasi' THEN 3
         WHEN wilayah = 'Depok' THEN 4
         ELSE 5 END AS wilayah_urut,
    -- status iklan saat terakhir dibuka oleh pipeline folder 23 (hanya rumah123)
    r123_status, r123_dicek, first_seen, last_seen
FROM pola;

-- Koreksi manual: hasil membaca iklan satu per satu untuk kandidat yang lolos saringan awal.
-- Tiap baris data/koreksi_manual.csv menimpa satu kolom dan mencatat alasannya.
CREATE OR REPLACE TABLE koreksi_manual AS
SELECT * FROM read_csv('{{koreksi_manual}}', delim = ';', quote = '', header = true, all_varchar = true);

ALTER TABLE k_teks ADD COLUMN duplikat_dari VARCHAR;
ALTER TABLE k_teks ADD COLUMN koreksi VARCHAR;
UPDATE k_teks SET k_komplek = m.nilai FROM koreksi_manual m WHERE m.id_rumah = k_teks.id_rumah AND m.kolom = 'k_komplek';
UPDATE k_teks SET k_mobil = m.nilai, mobil_dasar = m.alasan FROM koreksi_manual m WHERE m.id_rumah = k_teks.id_rumah AND m.kolom = 'k_mobil';
UPDATE k_teks SET k_lt = m.nilai FROM koreksi_manual m WHERE m.id_rumah = k_teks.id_rumah AND m.kolom = 'k_lt';
UPDATE rumah SET lt = cast(m.nilai AS DOUBLE) FROM koreksi_manual m WHERE m.id_rumah = rumah.id_rumah AND m.kolom = 'lt';
UPDATE rumah SET lb = cast(m.nilai AS DOUBLE) FROM koreksi_manual m WHERE m.id_rumah = rumah.id_rumah AND m.kolom = 'lb';
UPDATE k_teks SET k_lt = CASE WHEN cast(m.nilai AS DOUBLE) >= 36 THEN 'ya' ELSE 'tidak' END FROM koreksi_manual m WHERE m.id_rumah = k_teks.id_rumah AND m.kolom = 'lt';
UPDATE k_teks SET k_carport = m.nilai, carport_dasar = m.alasan FROM koreksi_manual m WHERE m.id_rumah = k_teks.id_rumah AND m.kolom = 'k_carport';
UPDATE k_teks SET wilayah_urut = cast(m.nilai AS INTEGER) FROM koreksi_manual m WHERE m.id_rumah = k_teks.id_rumah AND m.kolom = 'wilayah_urut';
UPDATE k_teks SET duplikat_dari = m.nilai FROM koreksi_manual m WHERE m.id_rumah = k_teks.id_rumah AND m.kolom = 'duplikat';
UPDATE k_teks SET rumah_baru = (m.nilai = 'ya') FROM koreksi_manual m WHERE m.id_rumah = k_teks.id_rumah AND m.kolom = 'rumah_baru';
UPDATE k_teks SET koreksi = x.semua
FROM (SELECT id_rumah, string_agg(kolom || ': ' || alasan, ' | ') AS semua FROM koreksi_manual GROUP BY 1) x
WHERE x.id_rumah = k_teks.id_rumah;
