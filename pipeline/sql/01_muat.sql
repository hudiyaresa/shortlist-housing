-- Muat bahan mentah ke DuckDB. Tidak ada file sumber yang diubah, semuanya hanya dibaca.
-- Dijalankan oleh 01_muat.py, yang mengisi {{galeri}}, {{rt_dki}}, {{r123_foto}}, {{r123_db}}.

INSTALL sqlite; LOAD sqlite;

-- 1. Semua rumah dari galeri (rumah123 + Threads + catatan survei + Pinhome, sudah bebas duplikat per sumber).
--    id_rumah stabil antar run: rumah123 dan Pinhome memakai nomor iklannya, sumber lain memakai potongan hash
--    tautan + teks.
CREATE OR REPLACE TABLE rumah AS
WITH mentah AS (
    SELECT *, row_number() OVER () AS urut
    FROM read_json('{{galeri}}', format = 'array', maximum_object_size = 50000000,
        columns = {bagian:'VARCHAR', sumber:'VARCHAR', judul:'VARCHAR', harga:'VARCHAR', rp:'BIGINT',
                   wilayah:'VARCHAR', lokasi:'VARCHAR', lt:'VARCHAR', lb:'VARCHAR', kt:'VARCHAR', km:'VARCHAR',
                   lantai:'VARCHAR', surat:'VARCHAR', akun:'VARCHAR', kirim:'VARCHAR', post:'VARCHAR',
                   dari:'VARCHAR', link:'VARCHAR', catatan:'VARCHAR', fitur:'VARCHAR', teks:'VARCHAR',
                   komplek:'VARCHAR', "no":'VARCHAR', lat:'DOUBLE', lon:'DOUBLE', est:'BOOLEAN', ket:'VARCHAR',
                   foto:'STRUCT(t VARCHAR, f VARCHAR)[]'})
)
SELECT
    CASE WHEN sumber = 'rumah123' THEN 'R-' || "no"
         WHEN sumber = 'Pinhome' THEN 'P-' || "no"
         ELSE (CASE WHEN sumber = 'Catatan survei' THEN 'W-' ELSE 'T-' END)
              || substr(md5(coalesce(link, '') || '|' || coalesce(teks, '')), 1, 8) END AS id_rumah,
    sumber, bagian, judul, harga AS harga_teks, rp,
    wilayah, lokasi,
    try_cast(replace(regexp_extract(lt, '[0-9]+(?:[.,][0-9]+)?'), ',', '.') AS DOUBLE) AS lt,
    try_cast(replace(regexp_extract(lb, '[0-9]+(?:[.,][0-9]+)?'), ',', '.') AS DOUBLE) AS lb,
    kt, km,
    try_cast(regexp_extract(lantai, '[0-9]+(?:[.,][0-9]+)?') AS DOUBLE) AS lantai,
    surat, akun, link, fitur, komplek,
    coalesce(nullif(post, ''), kirim) AS tanggal,
    lat, lon, est, ket AS ket_lokasi,
    len(foto) AS n_foto, foto[1].f AS foto1,
    foto AS foto_daftar,   -- t = thumbnail, f = foto asli (URL rumah123 atau path lokal folder 23)
    teks, catatan, dari, "no" AS no_sumber, kirim, urut
FROM mentah;

-- 2. Riwayat banjir per RT, BPBD DKI 2021 sampai 2024 (k = jumlah kejadian per tahun, h = jumlah hari).
CREATE OR REPLACE TABLE rt_dki AS
SELECT row_number() OVER () AS id_rt, kel, kec, rw, rt,
       k[1] AS k2021, k[2] AS k2022, k[3] AS k2023, k[4] AS k2024,
       tot AS kejadian, toth AS hari, kelas,
       ST_GeomFromText(g) AS geom,
       ST_Transform(ST_GeomFromText(g), 'EPSG:4326', 'EPSG:32748', true) AS geom_m
FROM read_json('{{rt_dki}}', format = 'array', maximum_object_size = 50000000,
     columns = {g:'VARCHAR', kel:'VARCHAR', kec:'VARCHAR', rw:'VARCHAR', rt:'VARCHAR',
                k:'INTEGER[]', h:'INTEGER[]', tot:'INTEGER', toth:'INTEGER', kelas:'VARCHAR'});
CREATE INDEX IF NOT EXISTS rt_dki_rtree ON rt_dki USING RTREE (geom_m);

-- 3. Status iklan rumah123 saat terakhir dibuka oleh 23_galeri_rumah/rumah123_foto.py.
CREATE OR REPLACE TABLE r123_status AS
SELECT 'R-' || id AS id_rumah, status, cek AS dicek
FROM read_json('{{r123_status}}', format = 'array', columns = {id:'VARCHAR', status:'VARCHAR', cek:'VARCHAR'});

-- 4. Kolom rumah123 yang tidak ada di galeri: carport, garasi, jenis agen, kapan pertama dan terakhir terlihat.
ATTACH '{{r123_db}}' AS r123 (TYPE sqlite, READ_ONLY);
CREATE OR REPLACE TABLE r123_listing AS
SELECT 'R-' || id AS id_rumah, first_seen, last_seen, posted,
       try_cast(json_extract_string(row_json, '$.carport') AS INTEGER) AS carport,
       try_cast(json_extract_string(row_json, '$.garasi') AS INTEGER) AS garasi,
       json_extract_string(row_json, '$.tipe_agen') AS tipe_agen,
       json_extract_string(row_json, '$.agen') AS agen,
       json_extract_string(row_json, '$.kantor') AS kantor,
       json_extract_string(row_json, '$.kelurahan') AS kelurahan,
       json_extract_string(row_json, '$.kota') AS kota,
       json_extract_string(row_json, '$.pin_presisi') AS pin_presisi
FROM r123.listing;
CREATE OR REPLACE TABLE r123_harga AS SELECT 'R-' || id AS id_rumah, tanggal, harga FROM r123.harga;
DETACH r123;
