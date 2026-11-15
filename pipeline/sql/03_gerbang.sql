-- Gardu tol mana yang pintu masuk dengan jalur ke arah Senayan?
-- Masukan: osm_gardu, osm_tol_ruas, osm_simpang, dan hasil uji rute per gardu ({{gardu_uji}}, dari 03_gerbang.py).

CREATE OR REPLACE TABLE gardu_uji AS
WITH u AS (
    SELECT * FROM read_json('{{gardu_uji}}', format = 'array',
        columns = {node_id:'BIGINT', snap_m:'DOUBLE', pra_m:'DOUBLE', tol_m:'DOUBLE', jeda_m:'DOUBLE',
                   akhir_m:'DOUBLE', rute_m:'DOUBLE', rute_dtk:'DOUBLE', tol_dtk:'DOUBLE', lurus_m:'DOUBLE',
                   ruas_pertama:'VARCHAR'})
),
-- jenis jalan tempat gardu berdiri: ramp (motorway_link) atau badan tol (motorway)
letak AS (
    SELECT g.node_id, min(r.jenis) AS jenis_ruas     -- 'motorway' < 'motorway_link': badan tol menang kalau dua-duanya
    FROM osm_gardu g LEFT JOIN osm_tol_ruas r ON list_contains(r.nodes, g.node_id)
    GROUP BY 1
),
-- nama: nama gardu sendiri, kalau kosong pinjam gardu bernama terdekat (<= 400 m) atau simpang tol terdekat (<= 800 m)
nama AS (
    SELECT g.node_id,
           coalesce(nullif(g.nama, ''),
                    (SELECT h.nama FROM osm_gardu h WHERE h.nama <> '' AND ST_DWithin(h.geom_m, g.geom_m, 400)
                     ORDER BY ST_Distance(h.geom_m, g.geom_m) LIMIT 1),
                    (SELECT s.nama FROM osm_simpang s WHERE s.nama <> ''
                       AND ST_DWithin(ST_Transform(ST_Point(s.lon, s.lat), 'EPSG:4326', 'EPSG:32748', true), g.geom_m, 800)
                     ORDER BY ST_Distance(ST_Transform(ST_Point(s.lon, s.lat), 'EPSG:4326', 'EPSG:32748', true), g.geom_m)
                     LIMIT 1),
                    'tanpa nama') AS nama_mentah
    FROM osm_gardu g
)
SELECT g.node_id, g.lat, g.lon, g.geom, g.geom_m,
       trim(regexp_replace(regexp_replace(n.nama_mentah, '(?i)\b(gerbang\s+tol|toll\s+gate|ramp|GT)\b|\(GTO\)', '', 'g'),
                           '\s+', ' ', 'g')) AS nama,
       l.jenis_ruas,
       u.pra_m, u.tol_m, u.jeda_m, u.akhir_m, u.rute_m, u.lurus_m, u.ruas_pertama,
       round(u.rute_dtk / 60, 1) AS mnt_ke_kantor_lancar,
       round(u.tol_dtk / 60, 1) AS mnt_di_tol_lancar,
       CASE
           WHEN u.node_id IS NULL                       THEN 'rute tidak ditemukan'
           WHEN l.jenis_ruas = 'motorway'               THEN 'gardu di badan tol'
           WHEN u.pra_m > 500                           THEN 'gardu keluar (rute tidak langsung masuk tol)'
           WHEN u.jeda_m > 300                          THEN 'arah menjauh (harus keluar tol lalu masuk lagi)'
           WHEN u.rute_m > 1.5 * u.lurus_m + 4000       THEN 'arah menjauh (rute memutar)'
           WHEN u.tol_m < 1000                          THEN 'gardu keluar (rute turun dari tol dalam 1 km)'
           ELSE 'masuk, arah Senayan'
       END AS status
FROM osm_gardu g
LEFT JOIN u USING (node_id)
LEFT JOIN letak l USING (node_id)
LEFT JOIN nama n USING (node_id);

-- Satu gerbang = gardu lolos yang saling berdekatan (<= 150 m). Wakilnya gardu dengan node_id terkecil.
CREATE OR REPLACE TABLE gerbang AS
WITH lolos AS (SELECT * FROM gardu_uji WHERE status = 'masuk, arah Senayan'),
wakil AS (
    SELECT a.node_id, min(b.node_id) AS id_gerbang
    FROM lolos a JOIN lolos b ON ST_DWithin(a.geom_m, b.geom_m, 150)
    GROUP BY 1
)
SELECT l.node_id AS id_gerbang, l.nama, l.lat, l.lon, l.geom, l.geom_m, l.ruas_pertama,
       l.mnt_ke_kantor_lancar, l.mnt_di_tol_lancar, round(l.rute_m / 1000, 1) AS km_ke_kantor,
       (SELECT count(*) FROM wakil w WHERE w.id_gerbang = l.node_id) AS jumlah_gardu
FROM lolos l
WHERE l.node_id IN (SELECT id_gerbang FROM wakil WHERE node_id = id_gerbang);
