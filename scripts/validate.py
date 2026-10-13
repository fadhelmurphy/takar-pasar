#!/usr/bin/env python3
"""
Pemeriksa data sebelum terbit. Gagal (exit 1) bila struktur rusak, angka di luar akal sehat,
atau angka berubah lebih dari batas dibanding versi sebelumnya di git.

  python scripts/validate.py                 # bandingkan dengan HEAD
  python scripts/validate.py --base HEAD~1   # bandingkan dengan commit lain
  IZINKAN_LONJAKAN=1 python scripts/validate.py   # lewati batas perubahan (mis. saat UMK tahun baru)
"""
import argparse, json, os, subprocess, sys

errors, warns = [], []


def err(msg):
    errors.append(msg)


def load_git(path, base):
    try:
        raw = subprocess.run(["git", "show", f"{base}:{path}"], capture_output=True, check=True).stdout
        return json.loads(raw)
    except Exception:
        return None


def check_dasar(d, prev, limit):
    for key in ["diperbarui", "penduduk", "internet", "upah", "pembanding", "pajak"]:
        if key not in d:
            err(f"dasar.json: kunci '{key}' hilang")
    if errors:
        return
    p = d["penduduk"]
    if not 2.5e8 <= p["nasional"] <= 3.2e8:
        err(f"penduduk nasional tidak wajar: {p['nasional']}")
    names = set()
    for prov, kota, pop in p["kota"]:
        names.add(kota)
        if not 5e4 <= pop <= 1.5e7:
            err(f"penduduk {kota} tidak wajar: {pop}")
    for k, v in d["internet"]["wilayah"].items():
        if not 0.3 <= v <= 1:
            err(f"penetrasi internet {k} di luar 0,3–1: {v}")
    if "Nasional" not in d["internet"]["wilayah"]:
        err("penetrasi internet Nasional hilang")
    for kota, v in d["upah"]["kota"].items():
        if not 1.5e6 <= v <= 1.2e7:
            err(f"upah {kota} tidak wajar: {v}")
        if kota not in names:
            warns.append(f"upah {kota} tidak ada di daftar kota penduduk")
    if not d["upah"].get("url"):
        err("upah: URL sumber wajib diisi")
    pj = d["pajak"]
    if not (0 < pj["tarif"] < 0.05 and 0 <= pj["bebas_per_tahun"] <= 5e9):
        err(f"pajak tidak wajar: {pj}")
    for k, b in d["pembanding"].items():
        if not (b["pendapatan"] > 0 and 0 < b["gerai_awal"] <= b["gerai_akhir"] * 2 and b.get("url")):
            err(f"pembanding {k} tidak lengkap atau tidak wajar")

    if prev and limit is not None:
        def jump(label, a, b):
            if a and abs(b - a) / a > limit:
                err(f"{label} berubah {100 * (b - a) / a:+.1f}% (batas ±{limit * 100:.0f}%). Set IZINKAN_LONJAKAN=1 bila memang benar.")
        jump("penduduk nasional", prev["penduduk"]["nasional"], d["penduduk"]["nasional"])
        for kota, v in d["upah"]["kota"].items():
            jump(f"upah {kota}", prev["upah"]["kota"].get(kota), v)
        for k, v in d["internet"]["wilayah"].items():
            jump(f"internet {k}", prev["internet"]["wilayah"].get(k), v)


def check_kecamatan(d, prev, limit):
    if d.get("v") is None or not isinstance(d.get("wilayah"), list):
        err("kecamatan.json: struktur tidak dikenali")
        return
    n = sum(len(w["kec"]) for w in d["wilayah"])
    total = sum(k["pop"] for w in d["wilayah"] for k in w["kec"])
    if n < 1000 and not os.environ.get("UJI_SEBAGIAN"):
        err(f"kecamatan terlalu sedikit: {n} (Indonesia punya lebih dari 7.000)")
    for w in d["wilayah"]:
        for k in w["kec"]:
            if k["pop"] < 0 or k["pop"] > 3e6:
                err(f"penduduk {k['n']}, {w['k']} tidak wajar: {k['pop']}")
            if len(k.get("bb", [])) != 4:
                err(f"bounding box {k['n']} rusak")
    if prev and limit is not None:
        pn = sum(len(w["kec"]) for w in prev.get("wilayah", []))
        pt = sum(k["pop"] for w in prev.get("wilayah", []) for k in w["kec"])
        if pn and abs(n - pn) / pn > limit:
            err(f"jumlah kecamatan berubah {pn} → {n}")
        if pt and abs(total - pt) / pt > limit:
            err(f"total penduduk kecamatan berubah {100 * (total - pt) / pt:+.1f}%")
        pc = sum(sum((k.get("comp") or {}).values()) for w in prev.get("wilayah", []) for k in w["kec"])
        nc = sum(sum((k.get("comp") or {}).values()) for w in d["wilayah"] for k in w["kec"])
        if pc and nc < pc * (1 - limit):
            err(f"total kompetitor OSM turun tajam {pc} → {nc}")
    print(f"kecamatan.json: {n} kecamatan, total penduduk {total:,.0f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="HEAD")
    ap.add_argument("--limit", type=float, default=0.10)
    a = ap.parse_args()
    limit = None if os.environ.get("IZINKAN_LONJAKAN") else a.limit

    with open("data/dasar.json", encoding="utf8") as f:
        check_dasar(json.load(f), load_git("data/dasar.json", a.base), limit)
    if os.path.exists("data/kecamatan.json"):
        with open("data/kecamatan.json", encoding="utf8") as f:
            check_kecamatan(json.load(f), load_git("data/kecamatan.json", a.base), limit)

    for w in warns:
        print("peringatan:", w)
    if errors:
        print("\nVALIDASI GAGAL:")
        for e in errors:
            print(" -", e)
        sys.exit(1)
    print("Validasi lolos.")


if __name__ == "__main__":
    main()
