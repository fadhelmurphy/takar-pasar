# Takar Pasar

Pilih jenis bisnis dan daerah, lalu lihat potensi pelanggan, modal awal, biaya bulanan, laba, dan waktu balik modal. Situs statis tanpa backend, diterbitkan lewat GitHub Pages.

## Struktur

| Berkas | Isi |
|---|---|
| `index.html` | Seluruh aplikasi (HTML, CSS, JS). Punya data bawaan, lalu menimpa dengan `data/*.json` saat dimuat. |
| `data/dasar.json` | Angka bersumber yang diperbarui manual: penduduk kota, penetrasi internet APJII, UMK, pajak UMKM, pembanding omzet. Setiap angka wajib punya URL sumber. |
| `data/kecamatan.json` | Dibuat otomatis: daftar kecamatan, penduduk, dan jumlah kompetitor dari OpenStreetMap. Belum ada sampai workflow pertama dijalankan. |
| `scripts/build_data.py` | Pembuat `kecamatan.json` dari geoBoundaries, WorldPop, dan ekstrak OSM Geofabrik. |
| `scripts/validate.py` | Penjaga data. Gagal bila struktur rusak atau angka berubah lebih dari ±10%. |

## Pembaruan data

- **Otomatis, bulanan** (`update-data.yml`): membangun ulang `kecamatan.json`, memvalidasi, commit, lalu menerbitkan ulang situs.
- **Manual, tahunan** (`pengingat.yml`): membuka issue saat UMK baru (Januari), survei APJII (Agustus), dan laporan tahunan (April). Perbarui `data/dasar.json`; untuk kenaikan wajar di atas 10% tambahkan `[izinkan-lonjakan]` di pesan commit.

## Pengaturan sekali di GitHub

1. Settings → Pages → Source: **GitHub Actions**.
2. Actions → *Perbarui data kecamatan dan kompetitor* → **Run workflow** untuk membuat data kecamatan pertama.

## Lisensi data

geoBoundaries dan WorldPop: CC BY 4.0. OpenStreetMap: ODbL, © kontributor OpenStreetMap. Angka berita dan laporan: lihat URL di `data/dasar.json`.

## Batasan

Galat yang ditampilkan berasal dari ketidakpastian asumsi, belum dari perbandingan dengan omzet nyata. Asumsi biaya dan minat per jenis bisnis belum bersumber.
