#!/usr/bin/env python3
"""
Membuat data/kecamatan.json untuk Takar Pasar. Dijalankan oleh GitHub Actions (update-data.yml), bukan oleh pengguna.

Sumber:
  - Batas wilayah: geoBoundaries gbOpen IDN ADM1/ADM2/ADM3 (CC BY 4.0), diambil lewat API geoBoundaries.
  - Penduduk: WorldPop 2020 1 km (CC BY 4.0), lalu diskalakan ke total nasional di data/dasar.json.
  - Kompetitor: ekstrak OpenStreetMap Indonesia dari Geofabrik (ODbL), dihitung per kecamatan.

Contoh:
  python scripts/build_data.py                       # penduduk + kompetitor
  python scripts/build_data.py --skip-osm            # penduduk saja
  python scripts/build_data.py --prov Banten         # uji cepat satu provinsi
"""
import argparse, datetime as dt, json, os, subprocess, sys
import requests
import geopandas as gpd
import pandas as pd
from rasterstats import zonal_stats

GB_API = "https://www.geoboundaries.org/api/current/gbOpen/IDN/{lvl}/"
WORLDPOP = "https://data.worldpop.org/GIS/Population/Global_2000_2020_1km/2020/IDN/idn_ppp_2020_1km_Aggregated.tif"
GEOFABRIK = "https://download.geofabrik.de/asia/indonesia-latest.osm.pbf"
CACHE = "cache"

# Harus sama dengan kunci jenis bisnis lokal di index.html
OSM_FILTERS = {
    "kafe": ["n/amenity=cafe", "w/amenity=cafe"],
    "makan": ["n/amenity=restaurant,fast_food,food_court", "w/amenity=restaurant,fast_food,food_court"],
    "barber": ["n/shop=hairdresser", "w/shop=hairdresser"],
    "laundry": ["n/shop=laundry,dry_cleaning", "w/shop=laundry,dry_cleaning"],
    "gym": ["n/leisure=fitness_centre", "w/leisure=fitness_centre"],
    "les": ["n/amenity=prep_school,language_school", "w/amenity=prep_school,language_school"],
}


def download(url, path):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    print("unduh", url, flush=True)
    with requests.get(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(path + ".part", "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    os.replace(path + ".part", path)
    return path


def boundaries(lvl):
    meta = requests.get(GB_API.format(lvl=lvl), timeout=60).json()
    path = download(meta["gjDownloadURL"], f"{CACHE}/idn_{lvl}.geojson")
    gdf = gpd.read_file(path)[["shapeName", "geometry"]].to_crs(4326)
    return gdf.rename(columns={"shapeName": lvl})


def attach_parent(child, parent, name):
    """Beri nama wilayah induk berdasarkan titik dalam (representative point) tiap poligon anak."""
    pts = child.copy()
    pts["geometry"] = child.geometry.representative_point()
    joined = gpd.sjoin(pts, parent[[name, "geometry"]], how="left", predicate="within")
    joined = joined[~joined.index.duplicated(keep="first")]
    child[name] = joined[name]
    return child


def kota_label(name):
    n = (name or "").strip()
    if n.lower().startswith(("kota ", "kabupaten ", "kab. ", "kab ")):
        return n.replace("Kabupaten ", "Kab. ")
    return n


def osm_counts(kec, osm_date_out):
    pbf = download(GEOFABRIK, f"{CACHE}/indonesia.osm.pbf")
    out = {}
    for biz, flt in OSM_FILTERS.items():
        sel = f"{CACHE}/{biz}.osm.pbf"
        gj = f"{CACHE}/{biz}.geojsonseq"
        subprocess.run(["osmium", "tags-filter", "-O", "-o", sel, pbf, *flt], check=True)
        subprocess.run(["osmium", "export", "-O", "-f", "geojsonseq", "-o", gj, sel], check=True)
        pts = gpd.read_file(gj)
        if pts.empty:
            out[biz] = pd.Series(0, index=kec.index)
            continue
        pts["geometry"] = pts.geometry.representative_point()
        hit = gpd.sjoin(pts[["geometry"]], kec[["geometry"]], how="inner", predicate="within")
        out[biz] = hit.groupby("index_right").size().reindex(kec.index, fill_value=0)
        print(biz, int(out[biz].sum()), "tempat", flush=True)
    stamp = dt.datetime.fromtimestamp(os.path.getmtime(pbf), dt.timezone.utc).date().isoformat()
    osm_date_out.append(stamp)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-osm", action="store_true")
    ap.add_argument("--prov", help="batasi ke satu provinsi (untuk uji)")
    ap.add_argument("--out", default="data/kecamatan.json")
    a = ap.parse_args()
    os.makedirs(CACHE, exist_ok=True)

    adm1, adm2, kec = boundaries("ADM1"), boundaries("ADM2"), boundaries("ADM3")
    adm2 = attach_parent(adm2, adm1, "ADM1")
    kec = attach_parent(kec, adm2, "ADM2")
    kec = kec.merge(adm2[["ADM2", "ADM1"]].drop_duplicates("ADM2"), on="ADM2", how="left")
    kec = kec.dropna(subset=["ADM1", "ADM2"]).reset_index(drop=True)
    if a.prov:
        kec = kec[kec["ADM1"].str.lower() == a.prov.lower()].reset_index(drop=True)
        if kec.empty:
            sys.exit(f"Provinsi {a.prov!r} tidak ditemukan. Contoh: {sorted(adm1['ADM1'])[:6]}")

    tif = download(WORLDPOP, f"{CACHE}/worldpop_2020_1km.tif")
    stats = zonal_stats(kec, tif, stats=["sum"], all_touched=False)
    kec["pop"] = [s["sum"] or 0 for s in stats]
    miss = kec["pop"] <= 0
    if miss.any():
        again = zonal_stats(kec[miss], tif, stats=["sum"], all_touched=True)
        kec.loc[miss, "pop"] = [s["sum"] or 0 for s in again]

    with open("data/dasar.json", encoding="utf8") as f:
        nasional = json.load(f)["penduduk"]["nasional"]
    if not a.prov:
        scale = nasional / kec["pop"].sum()
        print(f"skala WorldPop 2020 ke total nasional: {scale:.4f}", flush=True)
        kec["pop"] *= scale

    osm_date = []
    counts = {} if a.skip_osm else osm_counts(kec, osm_date)

    groups = {}
    for i, r in kec.iterrows():
        minx, miny, maxx, maxy = r.geometry.bounds
        item = {"n": r["ADM3"].strip(), "pop": int(round(r["pop"])),
                "bb": [round(miny, 4), round(minx, 4), round(maxy, 4), round(maxx, 4)]}
        if counts:
            item["comp"] = {b: int(counts[b].iloc[i]) for b in counts}
        groups.setdefault((r["ADM1"].strip(), kota_label(r["ADM2"])), []).append(item)

    old = {}
    if os.path.exists(a.out):
        with open(a.out, encoding="utf8") as f:
            old = json.load(f)
    wilayah = [{"p": p, "k": k, "kec": sorted(v, key=lambda x: x["n"])} for (p, k), v in sorted(groups.items())]
    data = {
        "v": 2,
        "diperbarui": dt.date.today().isoformat(),
        "src": "geoBoundaries (CC BY 4.0), WorldPop 2020 diskalakan ke total nasional (CC BY 4.0)" + ("" if a.skip_osm else ", OpenStreetMap (ODbL)"),
        "popQ": "0.15",
        "osm_tanggal": osm_date[0] if osm_date else old.get("osm_tanggal"),
        "wilayah": wilayah,
    }
    if a.skip_osm and old:  # pertahankan hitungan kompetitor lama
        prev = {(w["p"], w["k"], k["n"]): k.get("comp") for w in old.get("wilayah", []) for k in w["kec"]}
        for w in wilayah:
            for k in w["kec"]:
                c = prev.get((w["p"], w["k"], k["n"]))
                if c:
                    k["comp"] = c
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"selesai: {a.out} {os.path.getsize(a.out)/1e6:.2f} MB, {sum(len(w['kec']) for w in wilayah)} kecamatan")


if __name__ == "__main__":
    main()
