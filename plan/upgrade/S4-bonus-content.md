# S4 — Artikel + post sosial (bonus +0.4)

**Status:** `NOT STARTED` · **Estimasi:** 2 jam · **Claude:** ⚠️ sebagian
**Kapan:** setelah S3 · **Boleh dibuang:** ✅ ya, tapi ini return tertinggi per jam

---

## Kenapa fase ini ada

Rules memberi bonus Stage Three, maksimum 0.6:

| Bonus | Nilai |
|---|---|
| Published content | **+0.2** |
| Social media promotion | **+0.2** |
| Model Google AI tambahan (Gemma/Veo/Lyria) | +0.2 masing-masing |

Skor akhir berskala 1–6. **0.4 poin ≈ 7% skor total, untuk 2 jam kerja.**
Tidak ada pekerjaan lain di seluruh rencana yang mendekati rasio ini.

Bahannya sudah jadi: `plan/PROGRESS.md` §Decisions taken sudah berbentuk artikel.

---

## Prasyarat

- [ ] S3 selesai — klip 30 detik momen flip tersedia untuk post sosial

---

## Bagian Claude

### S4.1 · Artikel — `docs/blog/ungrounded-answer.md` · **+0.2**

- [ ] Judul: **"An agent may not present an ungrounded answer as a grounded one"**
- [ ] Panjang 600–900 kata. Bahasa Inggris
- [ ] Struktur:

  1. **Kejadiannya.** Query agent ditanya tentang negara yang belum punya
     regulasi terserap. Ia menulis *"there is no information available"* — dan
     **melampirkan kartu sitasi** untuk klausa yang sempat dibacanya. Jawaban
     kembali dengan `refusal: false`, kalimat penyangkalan berdiri di atas bukti.
  2. **Kenapa ini berbahaya, bukan sekadar jelek.** Sitasi adalah janji. Kartu
     sitasi di bawah kalimat "tidak ada informasi" mengajari pembaca bahwa
     sitasi tidak berarti apa-apa.
  3. **Kenapa perbaikan berbasis prompt tidak cukup.** Menyuruh model "katakan
     dengan jelas kalau tidak tahu" menghasilkan kalimat, dan kalimat harus
     diinterpretasi oleh kode yang tidak bisa menginterpretasi.
  4. **Perbaikannya.** Satu token yang bisa dicek: `INSUFFICIENT_EVIDENCE`.
     Kode bertipe mengubahnya jadi penolakan biasa. **Satu token bisa
     diverifikasi; satu kalimat yang menjelaskan dirinya sendiri tidak.**
  5. **Konteks yang lebih besar.** Aturan yang sama berlaku di seluruh sistem:
     kode deterministik memiliki setiap mutasi, model mengusulkan. Sebutkan
     guardrail dan rumus keyakinan sebagai penerapan lain dari prinsip yang sama.
  6. **Penutup.** Ini ditemukan oleh E2E terdeploy dalam hitungan menit setelah
     agent query dipasang. Nilai dari menjalankan E2E melawan sistem nyata.

- [ ] Sertakan potongan kode nyata dari repo, jangan pseudo-code
- [ ] Sertakan link ke repo dan ke video (dari S3)
- [ ] **Jangan mengarang metrik.** Semua angka yang dikutip harus ada di
      `plan/PROGRESS.md` atau README

### S4.2 · Post sosial — `docs/blog/social-post.md` · **+0.2**

- [ ] Dua versi: LinkedIn (±150 kata) dan X (≤280 karakter, boleh utas 3 tweet)
- [ ] Isi: masalah dalam satu kalimat → momen flip → link video → link repo
- [ ] Sebutkan stack-nya: Gemini 3.5 · Google ADK · Cloud Run · Pub/Sub · Firestore
- [ ] Tag hackathon
- [ ] Instruksi menyisipkan klip 30 detik momen flip

---

## Bagian kamu (manusia)

Menerbitkan adalah tindakan keluar yang mengatasnamakan kamu. Claude menyiapkan
teksnya; **kamu yang menekan publish.**

- [ ] Terbitkan artikel di Medium / dev.to / LinkedIn Article
- [ ] **Simpan URL-nya**
- [ ] Post ke LinkedIn atau X dengan klip 30 detik
- [ ] **Simpan URL-nya**
- [ ] Kirim kedua URL ke Claude

### Setelah terbit — bagian Claude lagi

- [ ] Catat kedua URL di `docs/blog/published-urls.md` — dipakai di form Devpost
      fase S5
- [ ] Commit: `docs(blog): publish the grounding write-up and social post`

---

## Verifikasi

- [ ] Artikel bisa dibuka **tanpa login** — uji di mode incognito
- [ ] Post sosial publik
- [ ] Setiap klaim teknis di artikel bisa ditunjuk padanannya di repo
- [ ] `docs/blog/published-urls.md` memuat kedua URL

---

## Selesai kalau

- [ ] Dua URL tersimpan dan siap ditempel ke form Devpost
- [ ] `plan/PROGRESS.md` Session log ditambah satu baris

---

## JANGAN dikerjakan di fase ini

- [~] Integrasi Gemma untuk mengejar +0.2 ketiga — menyentuh jalur ekstraksi dua
      hari sebelum deadline berisiko merusak yang stabil. Ambil hanya kalau
      S0–S5 seluruhnya sudah beres lebih awal
- [~] Claude menerbitkan atas namamu. Publikasi adalah keputusanmu
- [~] Melebih-lebihkan hasil di post sosial. Angka yang dikutip harus yang terukur
