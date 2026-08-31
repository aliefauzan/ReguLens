# ACTION PLAN — sisa pekerjaan sampai submit

> **File ini yang dibuka tiap mulai kerja.** Centang di tempat. Aturan kotak sama
> dengan `CLAUDE.md`: `[x]` hanya kalau sudah nyata dan terverifikasi, `[~]` untuk
> yang sengaja dilewati beserta alasannya.

**Deadline:** 31 Agu 2026 17:00 PDT = **1 Sep 2026 07:00 WIB**
**Track:** Collaborative Partner — *tidak berubah*
**Sisa waktu saat rencana ini dibuat:** ± 2,5 hari

| Fase | Isi | Estimasi | Kapan | Status |
|---|---|---|---|---|
| S0 | Konsistensi repo | 1 jam | 29 Agu malam | `NOT STARTED` |
| S1 | Fitur P3 Opsi A — Rencana Perbaikan | 5–7 jam | 30 Agu pagi–siang | `NOT STARTED` |
| S2 | Persiapan panggung demo | 1,5 jam | 30 Agu sore | `NOT STARTED` |
| S3 | Rekam + edit video | 4 jam | 30 Agu malam / 31 Agu pagi | `NOT STARTED` |
| S4 | Bonus: artikel + sosial | 2 jam | 31 Agu siang | `NOT STARTED` |
| S5 | Submit Devpost | 1 jam | 31 Agu sore — **JANGAN mepet** | `NOT STARTED` |

**Jalur kritis:** S0 → S2 → S3 → S5. S1 dan S4 bisa dikorbankan kalau waktu habis.
Kalau harus memilih satu untuk dibuang: **buang S1, jangan pernah buang S3.**

---

## FASE S0 — Konsistensi repo · 1 jam · 29 Agu malam

Murah, cepat, langsung menaikkan Kategori 2. Kerjakan malam ini juga.

### S0.1 · Perbaiki kotak yang bertentangan dengan kode

- [x] `plan/PROGRESS.md:43` — ubah `- [ ]` jadi `- [x]` pada
      *Secret Manager wired, no secrets in image or repo*.
      Tambahkan bukti di baris yang sama:
      `— gemini-api-key di Secret Manager, dipasang lewat --set-secrets di cloudbuild.yaml; .gitignore diaudit 29 Agu`
- [x] `plan/PROGRESS.md:47` — lima alert. Pilih **satu**:
      - kerjakan sungguhan (lihat S0.4), atau
      - ubah jadi `- [~] ... — SKIPPED: <alasan jujur>`
      **Jangan tinggalkan kosong.** Dipilih yang kedua: barisnya sekarang `[~]`
      dengan alasan — budget alert dan uptime check hidup, lima policy dengan
      pemicu sengaja tidak muat sebelum deadline.
- [x] `plan/phases/phase-6-e2e-testing.md:6` — Status `NOT STARTED` → `IN PROGRESS`,
      isi `**Started:** 23 Aug 2026`. Centang butir UC-A..F, redelivery,
      konkurensi, DLQ, walker, grounding yang sudah live-green.
      Sisakan Playwright sebagai `[~] — SKIPPED: verify_e2e.sh sudah menjadi bukti eksekusi yang setara`

### S0.2 · Samakan metadata submission

- [x] `regulens-session-summary.md:7` — tulis persis:
      `**Category:** Collaborative Partner`
      (nama konsep "Evolving Knowledge Engine" pindah ke baris tagline)

### S0.3 · README: 20 detik pertama juri

- [ ] Sisipkan blok ini **di atas judul** `# ReguLens`:
      ```markdown
      > **Demo video (4 min):** <URL — isi setelah S3>
      > **Live app:** https://regulens-web-babuvy7w3a-as.a.run.app
      > **Track:** Collaborative Partner · All Things Agentic Hackathon
      ```
- [ ] Kembali ke sini setelah S3 untuk mengisi URL video.

### S0.4 · Lima alert — opsional, hanya kalau S0.1–S0.3 selesai < 30 menit

- [ ] Buat 5 alert policy di Cloud Monitoring dan **trigger tiap satu sekali**.
      Kandidat: DLQ depth > 0, error rate API 5xx, latensi worker p95,
      kegagalan Cloud Build, budget 90%.
- [ ] Screenshot tiap alert yang benar-benar menyala — bahan untuk S3 segmen Console.
- [ ] Centang `plan/PROGRESS.md:47`.

### Kriteria selesai S0

- [ ] `grep -n "^- \[ \]" plan/PROGRESS.md` tidak lagi memunculkan baris yang
      sebenarnya sudah jadi.
- [ ] Tidak ada dua file di `plan/` yang menyatakan status berbeda untuk fase yang sama.
- [ ] Commit: `docs(plan): reconcile checkboxes with what is actually deployed`

---

## FASE S1 — Rencana Perbaikan (P3 Opsi A) · 5–7 jam · 30 Agu pagi–siang

**Tujuan:** mengubah agent dari *pemberi tahu* menjadi *penyiap keputusan*, tanpa
menyentuh pipeline, guardrail, atau mutasi apa pun. **Baca-saja. Risiko nol.**

**Boleh dibatalkan** kalau jam 14:00 tanggal 30 belum jalan. Video lebih penting.

### S1.1 · Backend — satu endpoint baca-saja

- [x] `GET /products/{id}/remediation` di `api/app/` (ikuti pola router yang ada).
- [x] Kumpulkan dari Firestore, **tanpa panggilan model**:
      - tiap requirement yang gagal, per pasar
      - batas tiap pasar untuk substansi yang sama, dalam satu satuan
      - **angka target lintas pasar** = batas paling ketat di antara pasar produk
      - klausa yang dikutip verbatim + `clause_id` + tautan passage
        (`/documents/{doc_id}?cite={clause_id}` — sudah ada dari pekerjaan 29 Agu)
      - tanggal berlaku tiap klausa
      - bahan yang **tidak dicek** dan alasannya (nama tak dikenal / tanpa jumlah /
        tanpa satuan) — pakai `GET /substances/resolve` yang sudah ada
- [x] Model respons Pydantic. Tak ada field yang dikarang: kalau tak ada angka
      target karena satu pasar belum punya aturan, katakan itu, jangan diam.
- [x] Test: produk dengan 2 pasar berbeda batas → target = yang paling ketat;
      produk tanpa pelanggaran → respons kosong yang eksplisit, bukan 404.

### S1.2 · Frontend — satu halaman

- [x] `web/app/products/[id]/remediation/page.tsx`
- [x] Tombol **"Siapkan rencana perbaikan"** di kartu alert pada halaman produk
      dan di banner "What changed on its own".
- [x] Isi halaman, urutan ini:
      1. Satu kalimat besar: *"Turunkan natrium benzoat ke ≤150 mg/kg dan produk ini diterima di Jerman dan Indonesia."*
      2. Tabel per pasar: batas · sumber · tanggal berlaku · penanda paling ketat
      3. Kutipan verbatim tiap klausa, tiap satu tertaut ke passage-nya
      4. Blok "Yang tidak kami cek" — jujur, jangan disembunyikan
      5. Tombol **Print / Save as PDF** (`window.print()` + `@media print`) —
         cukup, tak perlu generator PDF
- [x] `data-testid` di tiap blok utama.

### S1.3 · Pembingkaian Collaborative Partner — **jangan dilewat**

- [x] Halaman harus berkata di bagian atas, dengan kalimat sejenis:
      *"This is a draft for you to check, not an action we took."*
- [x] **JANGAN** kirim email, **JANGAN** ubah state produk, **JANGAN** aksi otonom
      keluar sistem. Menambah risiko, tidak menambah nilai di track ini.

### Kriteria selesai S1

- [x] `pytest -q` hijau, `ruff` bersih, `tsc` bersih, `next build` hijau
- [x] `bash scripts/verify_local.sh` masih hijau dari stack yang diwipe
- [x] Terlihat benar di browser untuk produk demo, light dan dark, lebar HP
- [x] Deploy ke Cloud Run dan **dicek di URL live** — video merekam yang live
- [x] Update `plan/PROGRESS.md`: baris Session log + centang di phase 7
- [x] Commit: `feat: draft a remediation plan the user can approve`

---

## FASE S2 — Persiapan panggung demo · 1,5 jam · 30 Agu sore

Jangan mulai merekam sebelum fase ini selesai. Rekaman ulang lebih mahal daripada
persiapan.

### S2.1 · Reset ke state awal cerita

- [ ] Reset stack live:
      ```bash
      gcloud run jobs execute regulens-job --region asia-southeast1 --wait
      ```
- [ ] Verifikasi state pembuka **persis** seperti ini:
      - Produk `Herbal Drink Powder` ada
      - Indonesia = **Meets the rules**
      - Jerman = **No rules added yet** ← ini shot terpenting di seluruh video
- [ ] Siapkan file aturan EU untuk di-upload saat rekaman.

### S2.2 · Siapkan dokumen cepat untuk shot live

- [ ] Siapkan **teks satu aturan** untuk di-paste (bukan aneks 4 halaman).
      Terukur 25,5 detik upload→re-evaluated; aneks 174 detik tidak muat.
- [ ] Uji sekali penuh dari upload sampai Jerman berubah merah. Catat detiknya.
- [ ] Kalau lebih dari 40 detik, siapkan rencana "3× speed" untuk segmen itu.

### S2.3 · Siapkan tab Google Cloud Console

Buka semua **sebelum** merekam, satu tab masing-masing:

- [ ] Pub/Sub → topik `document.uploaded` → metrik/aliran pesan
- [ ] Cloud Run → `regulens-worker` → Logs, sudah difilter ke `trace_id`
- [ ] Firestore → koleksi `graph_events` → urut waktu turun
- [ ] Cloud Run → daftar service, memperlihatkan **4 service** hidup
- [ ] (kalau S0.4 dikerjakan) Cloud Monitoring → alert yang menyala

> Segmen Console adalah yang paling sering dilewatkan peserta lain dan diminta
> eksplisit oleh kriteria. **Jangan potong segmen ini kalau kehabisan durasi** —
> potong bagian arsitektur.

### S2.4 · Kebersihan layar

- [ ] Zoom browser 110–125%, teks terbaca di layar kecil
- [ ] Sembunyikan bookmark bar, tab pribadi, notifikasi, nama akun pribadi
- [ ] Tidak ada API key, nama proyek pribadi, atau email yang terlihat di Console
- [ ] Mode terang (kontras lebih baik untuk rekaman)

---

## FASE S3 — Rekam + edit video · 4 jam · 30 Agu malam / 31 Agu pagi

**Fase yang tidak boleh gagal.** Kalau semua fase lain batal dan ini jadi,
submission tetap hidup.

### S3.1 · Naskah — tulis dulu, baru rekam

- [ ] Tulis narasi lengkap dalam bahasa Inggris. **Jangan improvisasi** —
      4 menit habis lebih cepat dari dugaan.
- [ ] Baca keras sambil menghitung waktu. Target **3:40**, sisakan margin.

Alokasi durasi:

| Waktu | Segmen | Yang harus terlihat |
|---|---|---|
| 0:00–0:30 | Masalah | Satu produk, dua negara. Dua angka: **150 vs 400 mg/kg** |
| 0:30–1:00 | State awal | Indonesia lulus · **Jerman "belum ada aturan", bukan "lulus"** |
| 1:00–1:30 | Aturan masuk | Upload/paste aturan EU, lalu **tutup tab**. Katakan: "nobody is watching this" |
| 1:30–2:30 | **Google Cloud** | Pub/Sub, log worker dengan `trace_id`, `graph_events` bertambah, 4 service Cloud Run |
| 2:30–3:15 | Jawaban berubah sendiri | Jerman merah tanpa diminta · Disagreements dua sisi · Ask dengan sitasi · Jepang **menolak** |
| 3:15–4:00 | Arsitektur + kolaborasi | `docs/architecture.png` · review queue: sumber lemah **tidak mengubah apa pun** · (kalau S1 jadi) rencana perbaikan yang menunggu persetujuan |

### S3.2 · Aturan rekaman

- [ ] Rekam layar penuh, minimal 1080p
- [ ] **Tanpa potongan diam-diam.** Percepat pakai label **"3× speed"** yang
      terlihat di layar. Kriteria menyebut "unedited execution proof"
- [ ] Angka latensi disebut jujur: *"a single rule lands in about 25 seconds; a
      55-clause annex takes about three minutes, and we publish the measurement"*
- [ ] Bahasa Inggris. Kalau narasi bukan Inggris, **wajib** subtitle Inggris

### S3.3 · Publikasi

- [ ] Upload ke YouTube, **Public** atau **Unlisted yang tidak butuh login**
- [ ] Judul: `ReguLens — an agent that tells you what a new regulation just broke`
- [ ] Durasi ≤ 4:00 — **cek angkanya, jangan diperkirakan**
- [ ] Tonton sekali penuh sebagai orang asing. Apakah masalahnya jelas dalam
      30 detik pertama? Kalau tidak, ulang segmen pembuka saja.
- [ ] Isi URL video ke README (S0.3)

---

## FASE S4 — Bonus · 2 jam · 31 Agu siang · **+0.4 poin**

Return tertinggi per jam di seluruh rencana. 0,4 dari skala 6 ≈ 7% skor total.

### S4.1 · Artikel — +0.2

- [ ] Judul: **"An agent may not present an ungrounded answer as a grounded one"**
- [ ] Isi: insiden 29 Agu — agent menulis *"there is no information available"*
      sambil melampirkan kartu sitasi, sehingga `refusal: false`. Perbaikan:
      satu token yang bisa dicek (`INSUFFICIENT_EVIDENCE`) yang diubah kode
      bertipe menjadi penolakan biasa.
      Pelajaran: **satu token bisa diverifikasi, satu kalimat yang menjelaskan
      dirinya sendiri tidak.**
- [ ] 600–900 kata. Bahan mentah: `plan/PROGRESS.md` §Decisions taken
- [ ] Terbitkan di Medium / dev.to / LinkedIn Article. **Simpan URL**

### S4.2 · Sosial — +0.2

- [ ] Satu post LinkedIn atau X, sisipkan klip 30 detik momen flip
- [ ] Tag hackathon. **Simpan URL**

---

## FASE S5 — Submit · 1 jam · 31 Agu sore · **JANGAN MEPET**

- [ ] Submit **draf** lebih dulu, revisi belakangan. Devpost mengizinkan edit
      sampai deadline; yang tidak diizinkan adalah submit setelah deadline.
- [ ] Isi form:
      - [ ] Kategori: **Collaborative Partner**
      - [ ] Video URL (S3)
      - [ ] Hosted URL: `https://regulens-web-babuvy7w3a-as.a.run.app`
      - [ ] Repo: `https://github.com/aliefauzan/ReguLens` — **cek benar publik**
      - [ ] Diagram arsitektur: `docs/architecture.png`
      - [ ] Deskripsi teks: fitur, teknologi, sumber data, temuan, pembelajaran
      - [ ] URL artikel (S4.1) dan URL sosial (S4.2) di kolom bonus
- [ ] Verifikasi terakhir, dari komputer lain / mode incognito:
      - [ ] Web live buka dan berfungsi
      - [ ] Repo terbaca tanpa login
      - [ ] Video bisa diputar tanpa login
      - [ ] README menampilkan video + live link di baris pertama
- [ ] Kalau tim: pastikan komposisi peserta di Devpost benar. Hadiah
      **Individual/Hobbyist ($10.000 ×2)** punya syarat berbeda dari track utama.
- [ ] Terakhir: update `plan/PROGRESS.md` — Session log + phase 7 → `COMPLETE`

---

## Kalau waktu habis — urutan membuang

1. **Buang S4.2** (sosial) — kehilangan 0,2
2. **Buang S1** (Rencana Perbaikan) — kehilangan ±0,5 di kriteria 40%
3. **Buang S4.1** (artikel) — kehilangan 0,2
4. **Buang S0.4** (lima alert) — sudah opsional sejak awal
5. **Persingkat S3 jadi 3 menit** — durasi lebih pendek diterima, ketiadaan video tidak

**Tidak pernah dibuang:** S0.1–S0.3, S2, S3, S5.

---

## Yang sudah diputuskan untuk TIDAK dikerjakan

- [~] Pindah ke track Taskmaster — **SKIPPED**: rubrik identik di semua track,
      jadi pindah bernilai 0 poin dan menambah risiko. Alasan lengkap di
      [`JUDGE-ASSESSMENT.md`](JUDGE-ASSESSMENT.md)
- [~] Auth / multi-tenant — **SKIPPED**: tidak dinilai di Collaborative Partner,
      dan README sudah jujur menyatakannya
- [~] Playwright shell formal — **SKIPPED**: `verify_e2e.sh` sudah menjadi bukti
      eksekusi yang setara atau lebih baik untuk juri
- [~] Mengejar target latensi 90 detik — **SKIPPED**: sudah dijelaskan dengan
      angka terukur dan reproducible; kejujuran terukur menang atas angka bagus
      tanpa bukti
- [x] Integrasi Gemma — **dikerjakan 31 Agu, dan bukan di jalur ekstraksi.**
      Kekhawatiran di atas benar, jadi Gemma dipasang di tempat yang tidak bisa
      merusak yang stabil: fitur baru `country discovery` (`gemma-4-31b-it` lewat
      Gemini Developer API, gratis). Kalau discovery gagal, pipeline lama tidak
      tersentuh. Terverifikasi di produksi — lihat `plan/PROD-VERIFICATION.md` C1–C6
      dan `plan/phases/phase-9-country-discovery.md`.
