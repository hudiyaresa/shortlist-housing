"""Langkah 10: halaman web dari hasil.

  output/index.html      shortlist_rumah.md sebagai halaman (dipakai GitHub Pages)
  output/kandidat.html   tabel rumah yang belum gugur, bisa disaring dan diurutkan
"""
from __future__ import annotations

import csv
import html
import json
import re

from umum import HERE, OUT

CSS = """
:root{--bg:#fff;--fg:#1f2328;--mut:#59636e;--line:#d1d9e0;--acc:#0969da;--soft:#f6f8fa}
@media (prefers-color-scheme:dark){:root{--bg:#0d1117;--fg:#e6edf3;--mut:#9198a1;--line:#3d444d;--acc:#4493f8;--soft:#161b22}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.6 system-ui,Segoe UI,Arial,sans-serif}
main{max-width:920px;margin:0 auto;padding:20px 16px 60px}
nav{position:sticky;top:0;background:var(--soft);border-bottom:1px solid var(--line);padding:9px 16px;font-size:14px;z-index:5}
nav a{margin-right:16px}a{color:var(--acc)}
h1{font-size:28px;line-height:1.25;margin:18px 0 8px}h2{font-size:21px;margin:34px 0 8px;padding-top:8px;border-top:1px solid var(--line)}
h3{font-size:17px;margin:24px 0 6px}p,li{overflow-wrap:anywhere}
.tw{overflow-x:auto;margin:10px 0}table{border-collapse:collapse;font-size:14px;min-width:100%}
th,td{border:1px solid var(--line);padding:5px 8px;text-align:left;vertical-align:top}th{background:var(--soft)}
code,pre{font-family:ui-monospace,Consolas,monospace;font-size:13.5px;background:var(--soft);border-radius:4px}
code{padding:1px 4px}pre{padding:10px 12px;overflow-x:auto}pre code{padding:0;background:none}
input,select{font:inherit;padding:5px 8px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);margin:0 8px 8px 0}
th.s{cursor:pointer;white-space:nowrap}.ok{color:#1a7f37;font-weight:600}.cek{color:#bc4c00}
"""
NAV = ('<nav><a href="index.html">Shortlist</a><a href="peta_shortlist.html">Peta</a>'
       '<a href="kandidat.html">Tabel kandidat</a><a href="kandidat.csv">kandidat.csv</a></nav>')


def sebaris(t: str) -> str:
    """Markdown dalam satu baris: kode, tebal, tautan, dan alamat web polos."""
    simpan: list[str] = []

    def taruh(m: re.Match) -> str:
        simpan.append(m.group(0))
        return f"\x00{len(simpan) - 1}\x00"

    t = html.escape(t, quote=False)
    t = re.sub(r"`([^`]+)`", lambda m: taruh(re.match(r".*", "<code>" + m.group(1) + "</code>")), t)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
               lambda m: taruh(re.match(r".*", f'<a href="{m.group(2)}">{m.group(1)}</a>')), t)
    t = re.sub(r"https?://[^\s<)]+", lambda m: taruh(re.match(r".*", f'<a href="{m.group(0)}">{m.group(0)}</a>')), t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
    return re.sub(r"\x00(\d+)\x00", lambda m: simpan[int(m.group(1))], t)


def tabel(baris: list[str]) -> str:
    sel = [[c.strip() for c in b.strip().strip("|").split("|")] for b in baris]
    kepala, isi = sel[0], sel[2:]
    h = "".join(f"<th>{sebaris(c)}</th>" for c in kepala)
    b = "".join("<tr>" + "".join(f"<td>{sebaris(c)}</td>" for c in r) + "</tr>" for r in isi)
    return f'<div class="tw"><table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'


def md_ke_html(md: str) -> str:
    out: list[str] = []
    daftar: str | None = None          # 'ul' atau 'ol' yang sedang terbuka
    baris = md.split("\n")
    i = 0

    def tutup() -> None:
        nonlocal daftar
        if daftar:
            out.append(f"</li></{daftar}>")
            daftar = None

    while i < len(baris):
        b = baris[i]
        polos = b.strip()
        menjorok = b.startswith("   ")
        if polos.startswith("```"):
            j = i + 1
            while j < len(baris) and not baris[j].strip().startswith("```"):
                j += 1
            out.append("<pre><code>" + html.escape("\n".join(baris[i + 1:j])) + "</code></pre>")
            i = j + 1
            continue
        if not polos:
            i += 1
            continue
        if polos.startswith("|"):
            j = i
            while j < len(baris) and baris[j].strip().startswith("|"):
                j += 1
            if not (daftar and menjorok):
                tutup()
            out.append(tabel(baris[i:j]))
            i = j
            continue
        m = re.match(r"(#{1,3}) (.*)", polos)
        if m and not menjorok:
            tutup()
            n = len(m.group(1))
            out.append(f"<h{n}>{sebaris(m.group(2))}</h{n}>")
            i += 1
            continue
        m = re.match(r"(-|\d+\.) (.*)", polos)
        if m and not menjorok:
            jenis = "ul" if m.group(1) == "-" else "ol"
            if daftar == jenis:
                out.append("</li>")
            else:
                tutup()
                out.append(f"<{jenis}>")
                daftar = jenis
            out.append("<li>" + sebaris(m.group(2)))
            i += 1
            continue
        if daftar and menjorok:
            out.append("<p>" + sebaris(polos) + "</p>")
            i += 1
            continue
        tutup()
        j = i
        while j < len(baris) and baris[j].strip() and not re.match(r"(#{1,3} |\||```|- |\d+\. )", baris[j].strip()):
            j += 1
        out.append("<p>" + sebaris(" ".join(x.strip() for x in baris[i:j])) + "</p>")
        i = max(j, i + 1)
    tutup()
    return "\n".join(out)


def halaman(judul: str, isi: str, skrip: str = "") -> str:
    return (f'<!doctype html><html lang="id"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1"><title>{judul}</title>'
            f"<style>{CSS}</style></head><body>{NAV}<main>{isi}</main>{skrip}</body></html>")


def main() -> None:
    md = (HERE / "shortlist_rumah.md").read_text(encoding="utf-8")
    (OUT / "index.html").write_text(halaman("Shortlist rumah untuk disurvei", md_ke_html(md)), encoding="utf-8")

    with open(OUT / "kandidat.csv", encoding="utf-8-sig", newline="") as f:
        semua = list(csv.DictReader(f))
    pakai = ["status", "kelompok_wilayah", "harga_jt", "luas_tanah_m2", "komplek", "lokasi", "ketepatan_lokasi",
             "gerbang_tol", "menit_ke_gerbang_pagi", "k_banjir", "banjir_dasar", "jarak_badan_tol_m", "k_mobil",
             "k_carport", "k_developer", "yang_perlu_dicek", "sumber", "link"]
    baris = [[r[k] for k in pakai] for r in semua
             if r["status"] in ("lolos semua", "perlu dicek") and r["sumber"] != "Catatan survei"]
    isi = ("<h1>Rumah yang belum gugur</h1><p>Semua rumah yang lolos semua kriteria wajib atau masih perlu dicek. "
           "Daftar lengkap termasuk yang gugur ada di <a href=\"kandidat.csv\">kandidat.csv</a>. "
           "Klik judul kolom untuk mengurutkan.</p>"
           '<input id="cari" placeholder="cari komplek atau lokasi" size="28">'
           '<select id="st"><option value="">semua status</option><option>lolos semua</option><option>perlu dicek</option></select>'
           '<select id="wil"><option value="">semua wilayah</option></select> <span id="jml"></span>'
           '<div class="tw"><table id="t"><thead></thead><tbody></tbody></table></div>')
    skrip = "<script>const K=" + json.dumps(pakai) + ";const B=" + json.dumps(baris, ensure_ascii=False) + """;
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const nama={status:'Status',kelompok_wilayah:'Wilayah',harga_jt:'Harga (jt)',luas_tanah_m2:'LT',komplek:'Komplek',lokasi:'Lokasi di iklan',
ketepatan_lokasi:'Titik',gerbang_tol:'Gerbang tol',menit_ke_gerbang_pagi:'Menit ke gerbang',k_banjir:'Banjir',banjir_dasar:'Dasar banjir',
jarak_badan_tol_m:'Badan tol (m)',k_mobil:'Mobil',k_carport:'Carport',k_developer:'Developer',yang_perlu_dicek:'Perlu dicek',sumber:'Sumber',link:'Iklan'};
let urut=8,naik=true;
[...new Set(B.map(r=>r[1]))].sort().forEach(w=>document.getElementById('wil').insertAdjacentHTML('beforeend','<option>'+esc(w)+'</option>'));
document.querySelector('#t thead').innerHTML='<tr>'+K.map((k,i)=>'<th class="s" data-i="'+i+'">'+nama[k]+'</th>').join('')+'</tr>';
function gambar(){
  const c=document.getElementById('cari').value.toLowerCase(),s=document.getElementById('st').value,w=document.getElementById('wil').value;
  const angka=[2,3,8,11].includes(urut);
  const r=B.filter(x=>(!s||x[0]===s)&&(!w||x[1]===w)&&(!c||(x[4]+' '+x[5]).toLowerCase().includes(c)))
    .sort((a,b)=>{let p=a[urut],q=b[urut];if(angka){p=p===''?1e9:+p;q=q===''?1e9:+q;return naik?p-q:q-p}return naik?String(p).localeCompare(q):String(q).localeCompare(p)});
  document.getElementById('jml').textContent=r.length+' rumah';
  document.querySelector('#t tbody').innerHTML=r.map(x=>'<tr>'+x.map((v,i)=>{
    if(K[i]==='link')return '<td>'+(v?'<a href="'+esc(v.split(' | ')[0])+'" target="_blank" rel="noopener">buka</a>':'')+'</td>';
    if(K[i]==='status')return '<td class="'+(v==='lolos semua'?'ok':'cek')+'">'+esc(v)+'</td>';
    return '<td>'+esc(v)+'</td>'}).join('')+'</tr>').join('');
}
document.querySelectorAll('th.s').forEach(t=>t.onclick=()=>{const i=+t.dataset.i;naik=urut===i?!naik:true;urut=i;gambar()});
['cari','st','wil'].forEach(i=>document.getElementById(i).oninput=gambar);gambar();</script>"""
    (OUT / "kandidat.html").write_text(halaman("Tabel kandidat rumah", isi, skrip), encoding="utf-8")
    print("index.html dan kandidat.html ditulis,", len(baris), "rumah di tabel")


if __name__ == "__main__":
    main()
