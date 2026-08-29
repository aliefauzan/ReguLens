# Rencana Upgrade — diurut per poin-skor per jam

Konteks: deadline **31 Agu 17:00 PDT = 1 Sep 07:00 WIB**. Track tetap
**Collaborative Partner** (alasan di [`JUDGE-ASSESSMENT.md`](JUDGE-ASSESSMENT.md)).

Estimasi total P0→P2 ≈ **7 jam**. P3 ≈ **5–7 jam** tambahan.

| Prioritas | Isi | Estimasi | Dampak skor |
|---|---|---|---|
| **P0** | Video + form Devpost | 4–5 jam | dari **0** (gugur) ke **3.85–4.30** |
| **P1** | Bonus konten + sosial | 2 jam | **+0.4** dari 0.6 maksimal |
| **P2** | Konsistensi repo | 1 jam | Kategori 2: 4.5 → 4.7 |
| **P3** | Agent yang menyiapkan tindakan | 5–7 jam | Kategori 1: 4.0 → 4.5 |

---

## P0 — Existensial. Tanpa ini submission gugur.

Registrasi Devpost **sudah selesai**. Yang tersisa dua hal.

### P0.1 · Video demo ~4 menit, bahasa Inggris

Struktur yang direkomendasikan, dibingkai untuk **Collaborative Partner**:

| Waktu | Isi | Kenapa |
|---|---|---|
| 0:00–0:30 | Masalah: satu produk, dua negara, dua batas berbeda. Tampilkan dua angka: **150 vs 400 mg/kg** | Kriteria minta "problem overview & value proposition" |
| 0:30–1:00 | Produk sudah ada. Indonesia **lulus**. Jerman **"belum ada aturan" — bukan "lulus"**. Tekankan ini | Membuktikan agent menolak menebak. Nilai CP tertinggi |
| 1:00–1:30 | Upload aturan EU. **Tutup tab.** Katakan "tidak ada yang menonton" | Bukti eksekusi background |
| 1:30–2:30 | **Google Cloud Console**: aliran pesan Pub/Sub, log Cloud Run worker dengan `trace_id`, dokumen `graph_events` bertambah di Firestore | Kriteria menyebut ini eksplisit. Bagian yang paling sering dilewatkan peserta lain |
| 2:30–3:15 | Buka lagi: Jerman merah **sendiri**. Halaman Disagreements, dua aturan dikutip verbatim. Ask → sitasi nyata. Tanya Jepang → **menolak** | Money-shot + kejujuran |
| 3:15–4:00 | Diagram arsitektur. Tiga agent di tempatnya, edge "impact: no model call". Review queue: sumber lemah masuk antrean dan **tidak mengubah apa pun** | Kolaborasi manusia–agent, penutup track |

**Trik latensi.** Aneks EU butuh 174 detik. Untuk shot live pakai **satu aturan
yang di-paste (25,5 detik terukur)**. Hasil aneks ditunjukkan sebagai hasil jadi,
angkanya disebut jujur. Jangan potong diam-diam — kriteria minta "unedited
execution proof". Percepat dengan label **"3× speed"** di layar; itu diterima,
memotong sunyi-sunyi tidak.

**Wajib:** bahasa Inggris atau subtitle Inggris. Maksimum 4 menit. Unggah ke
YouTube/Vimeo publik, jangan unlisted-yang-butuh-login.

### P0.2 · Form submission Devpost

- Deskripsi teks: fitur, teknologi, sumber data, temuan, pembelajaran.
  Bahannya sudah ada di `regulens-session-summary.md` dan README.
- Hosted URL: `https://regulens-web-babuvy7w3a-as.a.run.app`
- Repo: `https://github.com/aliefauzan/ReguLens` — pastikan publik.
- Diagram: `docs/architecture.png`.
- **Jangan submit di jam terakhir.** Submit draf lebih dulu, revisi setelahnya.

---

## P1 — Bonus termurah di seluruh daftar. +0.4 poin, ~2 jam.

Skala akhir 1–6, jadi 0,4 poin ≈ **7% skor total**. Tidak ada pekerjaan lain di
daftar ini yang sebanding.

### P1.1 · Published content — **+0.2** (~90 menit)

Satu tulisan devlog. Bahannya sudah jadi: `plan/PROGRESS.md` §Decisions taken
sudah berbentuk artikel.

Judul yang saya sarankan:
**"An agent may not present an ungrounded answer as a grounded one"**

Isi: insiden 29 Agu — query agent menulis "there is no information available"
sambil **melampirkan kartu sitasi** klausa yang dibacanya, sehingga jawaban
kembali `refusal: false`. Perbaikannya satu token yang bisa dicek
(`INSUFFICIENT_EVIDENCE`) yang diubah kode bertipe menjadi penolakan biasa.
Pelajarannya: **satu token bisa diverifikasi, satu kalimat yang menjelaskan
dirinya sendiri tidak.**

Terbitkan di Medium / dev.to / LinkedIn Article. Simpan URL-nya — dimasukkan ke
form Devpost.

### P1.2 · Social media promotion — **+0.2** (~30 menit)

Satu post LinkedIn atau X. Sisipkan klip 30 detik momen flip. Tag hackathon.
Simpan URL-nya.

### P1.3 · Model Google tambahan — +0.2, **tidak direkomendasikan sekarang**

Gemma/Veo/Lyria masing-masing +0.2. Slot `prefilter_sections` memang sengaja
dikosongkan (keputusan 22 Agu) dan Gemma cocok mengisinya — bonus **dan**
memotong 125 detik ekstraksi. Tapi dua hari sebelum deadline ini berisiko
merusak jalur yang sudah stabil. **Ambil hanya jika P0–P3 sudah beres.**

---

## P2 — Konsistensi repo. ~1 jam, langsung mengangkat Kategori 2.

Juri membaca repo. Kontradiksi di dalam repo yang menjual disiplin dokumentasi
lebih merugikan daripada pekerjaan yang belum selesai.

1. **`plan/PROGRESS.md:43`** → centang `[x] Secret Manager wired`. Ini sudah nyata:
   `cloudbuild.yaml` memakai `--set-secrets`, secret `gemini-api-key` ada,
   `.gitignore` sudah diaudit 29 Agu.
2. **`plan/phases/phase-6-e2e-testing.md:6`** → Status `NOT STARTED` → `IN PROGRESS`,
   isi tanggal Started. UC-A..F, redelivery, konkurensi, DLQ, walker, grounding
   semuanya sudah live-green — kotaknya yang tertinggal.
3. **`plan/PROGRESS.md:47`** (5 alert) → kalau tidak sempat dikerjakan, ubah jadi
   `[~] — SKIPPED: <alasan>`. **Kotak kosong dibaca sebagai lalai; `[~]` dibaca
   sebagai keputusan.** Aturan ini kamu tulis sendiri di CLAUDE.md.
4. **`plan/PROGRESS.md:42`** (push trigger) → sudah ada catatan miring, tapi
   tegaskan: manual trigger adalah pilihan, bukan kekurangan, kalau memang begitu.
5. **`regulens-session-summary.md:7`** → samakan penulisan kategori dengan track
   Devpost resmi: `Collaborative Partner`.
6. **README baris pertama** → taruh **link video** dan **link hosted app** di atas
   judul. Juri membuka README selama 20 detik.

---

## P3 — Mengangkat kriteria 40%. Pilih **satu**, jangan dua.

### Opsi A — Agent yang menyiapkan tindakan · **DIREKOMENDASIKAN**

Jawaban langsung atas kritik "agent berhenti di notifikasi", dan dibingkai persis
untuk Collaborative Partner: **agent menyiapkan pekerjaan sampai tinggal
disetujui manusia — bukan bertindak sendiri.**

Setelah alert muncul, tambahkan satu tombol: **"Siapkan rencana perbaikan"**.
Menghasilkan satu dokumen berisi:

- Angka target lintas pasar — `≤150 mg/kg aman di Jerman dan Indonesia`
- Batas per pasar dengan pasar paling ketat ditandai
- Klausa yang dikutip verbatim + tautan ke passage-nya
- Tanggal berlaku tiap aturan
- Bahan yang tidak dicek dan alasannya (jujur, bukan disembunyikan)

**Kenapa ini murah:** semua datanya sudah ada di Firestore. Ini satu endpoint
baca-saja + satu halaman render. Tidak menyentuh pipeline, tidak menyentuh
guardrail, tidak ada mutasi baru — jadi risikonya mendekati nol.

**Kenapa ini mahal nilainya:** mengubah agent dari *pemberi tahu* menjadi
*penyiap keputusan*. Itu tepat kata yang ada di kriteria 40%.

**Jangan** buat ia mengirim email atau mengubah state produk. Aksi otonom
keluar-sistem tidak dinilai lebih tinggi di track ini dan menambah risiko.

### Opsi B — Scheduled watcher

Cloud Scheduler → Pub/Sub → re-evaluasi berkala, supaya kata "living twin"
berhenti bertentangan dengan README.

Lebih murah dari Opsi A secara kode, tapi **lebih lemah nilainya**: ia hanya
menjalankan ulang yang sudah ada, tidak menghasilkan output baru yang bisa
ditunjukkan di video. Ambil hanya jika waktu tinggal 2 jam dan Opsi A tak muat.

### Opsi C — Gemma prefilter

Lihat P1.3. Terakhir dalam antrean.

---

## Ringkasan keputusan

| Keputusan | Pilihan | Alasan |
|---|---|---|
| Track | **Tetap Collaborative Partner** | Rubrik identik di semua track; pindah = 0 poin, tambah risiko |
| Video | Satu aturan di-paste untuk live shot | 25,5s muat di 4 menit; aneks 174s tidak |
| P3 | **Opsi A** | Risiko nol, menjawab kritik terbesar, pas dengan track |
| Gemma | Tunda | +0,2 lebih murah didapat dari blog post |
| Auth | Tidak dikerjakan | Tidak dinilai di track ini |
