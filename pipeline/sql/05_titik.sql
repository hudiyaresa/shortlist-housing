-- Satu titik terbaik per rumah, dengan tingkat ketepatannya.
-- Urutan yang dipakai: lokasi manual (data/lokasi_manual.csv) > pin penjual rumah123 > titik perkiraan dari galeri.
-- lokasi_manual.csv diisi untuk kandidat yang lolos saringan awal: titik komplek dicari dari nama komplek, nama jalan,
-- atau patokan di iklan. Kolom `sumber` mencatat dari mana titik itu didapat.

CREATE OR REPLACE TABLE lokasi_manual AS
SELECT * FROM read_csv('{{lokasi_manual}}', delim = ';', quote = '', header = true,
    columns = {id_rumah:'VARCHAR', lat:'DOUBLE', lon:'DOUBLE', tingkat:'VARCHAR', sumber:'VARCHAR'});

CREATE OR REPLACE TABLE titik AS
WITH pilih AS (
    SELECT r.id_rumah,
           coalesce(m.lat, r.lat) AS lat,
           coalesce(m.lon, r.lon) AS lon,
           CASE WHEN m.id_rumah IS NOT NULL THEN m.tingkat
                WHEN r.est = false THEN 'tepat'
                WHEN r.lat IS NULL THEN 'tidak ada'
                ELSE 'perkiraan' END AS ketepatan,
           CASE WHEN m.id_rumah IS NOT NULL THEN m.sumber
                ELSE coalesce(r.ket_lokasi, 'tidak ada titik') END AS sumber_titik
    FROM rumah r LEFT JOIN lokasi_manual m USING (id_rumah)
)
SELECT *,
       cast(round(lat * 1e5) AS BIGINT) AS lat5, cast(round(lon * 1e5) AS BIGINT) AS lon5,
       ST_Point(lon, lat) AS geom,
       ST_Transform(ST_Point(lon, lat), 'EPSG:4326', 'EPSG:32748', true) AS geom_m
FROM pilih;
