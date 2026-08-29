# S2 — Siapkan panggung demo

**Status:** `NOT STARTED` · **Estimasi:** 1,5 jam · **Claude:** ⚠️ sebagian
**Kapan:** setelah S1 (atau setelah S0 kalau S1 dibuang) · **Boleh dibuang:** ❌ tidak

---

## Kenapa fase ini ada

Rekaman ulang jauh lebih mahal daripada persiapan. Video 4 menit yang harus
diulang karena state-nya salah membuang 1 jam; fase ini 1,5 jam dan menghapus
seluruh kelas kegagalan itu.

Satu kendala fisik yang menyetir semuanya: **aneks EU butuh 174 detik** untuk
propagasi (`README` §Honest limitations). Itu 72% dari durasi video. Money-shot
harus direkam dengan **satu aturan yang di-paste — 25,5 detik terukur.**

---

## Prasyarat

- [ ] `gcloud` terautentikasi ke project `regulens-506014`
- [ ] Semua kode yang mau tampil di video **sudah ter-deploy ke Cloud Run**.
      Video merekam yang live, bukan localhost

---

## Bagian Claude

### S2.1 · Reset stack live ke state pembuka

- [ ] Jalankan seed:
      ```bash
      gcloud run jobs execute regulens-job --region asia-southeast1 --project regulens-506014 --wait
      ```
- [ ] Verifikasi state pembuka lewat API, **jangan diasumsikan**:
      ```bash
      API=https://regulens-api-babuvy7w3a-as.a.run.app
      curl -s $API/products | head -c 2000
      ```
- [ ] Ambil `product_id` produk demo, lalu:
      ```bash
      curl -s $API/products/<PRODUCT_ID>/compliance | head -c 3000
      ```
- [ ] Konfirmasi **persis** tiga hal ini, dan laporkan apa adanya kalau meleset:
      - Produk `Herbal Drink Powder` ada
      - Indonesia = **compliant**
      - Jerman = **unknown** (di UI terbaca "No rules added yet")
        ← ini shot terpenting di seluruh video. Kalau Jerman sudah punya aturan,
        seed ulang atau hapus dokumen EU-nya sebelum merekam

### S2.2 · Siapkan teks aturan cepat untuk shot live

- [ ] Buat file `docs/demo/eu-rule-for-video.txt` berisi **satu aturan EU
      terkait sodium benzoate di minuman berperisa**, dikutip verbatim dari
      korpus yang sudah ada di repo (`data/regulations/` atau
      `api/app/core/library_data.json`). **Jangan mengarang teks regulasi** —
      itu pelanggaran standing rule repo
- [ ] Isinya harus cukup untuk menghasilkan **satu** klausa 150 mg/kg, bukan 55
- [ ] Sertakan sitasi sumbernya di dalam file

### S2.3 · Ukur durasi sebenarnya

- [ ] Jalankan pengukuran terhadap teks itu:
      ```bash
      python3 scripts/measure_latency.py docs/demo/eu-rule-for-video.txt
      ```
- [ ] Catat hasilnya ke `docs/demo/timing.md`: upload → extracted → reconciled →
      impact → total
- [ ] **Kalau total > 40 detik**, catat di `timing.md` bahwa segmen itu perlu
      label "3× speed" saat editing
- [ ] Setelah pengukuran, **reset lagi** (S2.1) supaya state pembuka bersih
      untuk rekaman

### S2.4 · Daftar tab Console yang harus dibuka

- [ ] Tulis `docs/demo/console-tabs.md` berisi **URL lengkap yang bisa diklik**
      untuk tiap tab berikut, dengan project `regulens-506014` dan region
      `asia-southeast1` sudah terisi:
      1. Pub/Sub → topik `document.uploaded` → metrik / aliran pesan
      2. Cloud Run → service `regulens-worker` → tab Logs
      3. Firestore → koleksi `graph_events`, urut waktu turun
      4. Cloud Run → daftar service, memperlihatkan **4 service** hidup
      5. Cloud Build → riwayat build hijau
- [ ] Untuk tab Logs, sertakan **query filter siap tempel** yang menampilkan
      satu `trace_id` mengalir dari api ke worker. Contoh bentuknya, sesuaikan
      dengan field yang benar-benar dipakai `app/observability.py`:
      ```
      resource.type="cloud_run_revision"
      jsonPayload.trace_id="<TRACE_ID>"
      ```
- [ ] Sertakan cara mendapatkan `trace_id` terbaru dari respons upload, supaya
      saat rekaman tinggal disalin

---

## Bagian kamu (manusia)

Claude tidak bisa mengendalikan browser dan tampilan layarmu.

- [ ] Buka semua tab dari `docs/demo/console-tabs.md` **sebelum** mulai merekam
- [ ] Zoom browser 110–125% — teks harus terbaca di layar kecil
- [ ] Sembunyikan bookmark bar, tab pribadi, dan notifikasi sistem
- [ ] Mode terang (kontras lebih baik untuk rekaman)
- [ ] **Cek tidak ada yang bocor di layar**: API key, email pribadi, nama
      project lain, saldo billing
- [ ] Tutup aplikasi chat dan email

---

## Verifikasi

- [ ] State pembuka terkonfirmasi lewat `curl`, bukan lewat ingatan
- [ ] `docs/demo/eu-rule-for-video.txt` ada, verbatim, bersitasi
- [ ] `docs/demo/timing.md` memuat angka hasil ukur, bukan perkiraan
- [ ] `docs/demo/console-tabs.md` memuat URL yang benar-benar terbuka saat diklik
- [ ] Setelah pengukuran, state sudah di-reset lagi ke pembuka

---

## Selesai kalau

- [ ] Empat file/kondisi di atas siap
- [ ] Kamu bisa mulai merekam tanpa membuka satu pun tab baru
- [ ] Commit: `chore(demo): stage the recording environment with measured timings`

---

## JANGAN dikerjakan di fase ini

- [~] Mengarang teks regulasi untuk mempercepat demo. Kutip dari korpus atau
      tidak sama sekali
- [~] Memakai aneks EU 4 halaman untuk shot live. 174 detik tidak muat di video
      4 menit
- [~] Merekam dari localhost. Kriteria minta bukti Google Cloud yang terlihat
