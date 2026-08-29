# S5 — Teks submission Devpost

**Status:** `NOT STARTED` · **Estimasi:** 1 jam · **Claude:** ⚠️ sebagian
**Kapan:** terakhir · **Boleh dibuang:** ❌ tidak — tanpa ini tidak ada submission

---

## Kenapa fase ini ada

Rules meminta *"Text description covering features, functionality, technologies,
data sources, findings, and learnings"*. Enam hal, dan **findings/learnings**
adalah yang paling sering diisi asal-asalan padahal repo ini justru paling kaya
di sana — `plan/PROGRESS.md` §Decisions taken berisi belasan temuan nyata.

Claude menulis teksnya. **Kamu yang mengisi form** — mengisi form adalah
tindakan atas nama akunmu.

---

## Prasyarat

- [ ] S3 selesai — URL video ada
- [ ] S4 selesai kalau dikerjakan — URL artikel dan sosial ada

---

## Bagian Claude

### S5.1 · Naskah submission — `docs/submission-text.md`

Tulis dalam **bahasa Inggris**, siap tempel ke Devpost, dengan enam bagian:

- [ ] **Problem & value proposition** (±150 kata)
      Eksportir kecil menghadapi banyak yurisdiksi sekaligus. Angka nyata:
      sodium benzoate di minuman berperisa — EU 150 mg/kg, BPOM 400 mg/kg.
      Tidak ada tim hukum untuk memantaunya.

- [ ] **What it does** (±200 kata)
      Core loop dari README. Tekankan yang membedakan: **verdict berubah tanpa
      user meminta**, penolakan jujur saat tidak ada data, dan pasar tanpa
      aturan **tidak** terbaca seperti pasar yang lulus.

- [ ] **How it works — technologies** (±250 kata)
      - Gemini 3.5-flash, lewat Gemini API **atau** Vertex AI (dua jalur, satu env var)
      - Google ADK: tiga agent yang benar-benar jalan — Extraction, Reconciliation
        (hanya di titik judge), Query (memilih tool retrieval-nya sendiri).
        **Impact sengaja tanpa agent dan tanpa panggilan model** — pass/fail
        terhadap batas numerik adalah aritmatika
      - Cloud Run ×4 dari satu image, Pub/Sub push 3 topik + dead-letter,
        Firestore, Cloud Storage, Secret Manager, Cloud Build
      - Kode deterministik memiliki setiap mutasi; respons model tidak pernah
        masuk Firestore tanpa validator Pydantic dan guardrail
      - Keyakinan **dihitung**, bukan dilaporkan sendiri:
        `0.3·parse_quality + 0.4·self_consistency + 0.3·authority_tier`

- [ ] **Data sources** (±100 kata)
      Regulasi nyata di `data/regulations/` dengan checksum di `SOURCES.md`:
      EU 1333/2008 (konsolidasi), EU 1129/2011 Annex II, BPOM 11/2019.
      Library bawaan memotong **28 excerpt verbatim** dari keduanya — dipotong,
      tidak pernah ditulis ulang, dan masuk lewat jalur upload yang identik.

- [ ] **Findings & learnings** (±250 kata) — **bagian terkuat, jangan diperpendek**
      Ambil dari `plan/PROGRESS.md` §Decisions taken, minimal empat:
      1. Agent yang menyangkal sambil melampirkan sitasi → satu token yang bisa
         dicek (`INSUFFICIENT_EVIDENCE`) mengalahkan kalimat yang menjelaskan diri
      2. Kredensial placeholder = tidak ada kredensial; kegagalannya senyap —
         embedding mati satu per satu dan app menjawab "tidak ada regulasi"
         sambil memegang regulasinya
      3. Sitasi menunjuk passage atau tidak menunjuk apa pun; klausa yang tidak
         bisa dilokasikan didaftar sebagai unlocated, bukan diarahkan ke
         paragraf terdekat
      4. Aturan hanya mengikat jenis produk yang memang diaturnya — ditemukan
         karena library membuat drink powder gagal melawan batas dairy dessert
      5. Latensi adalah properti dokumen, bukan pipeline — diukur ulang, bukan
         diingat

- [ ] **Honest limitations** (±120 kata)
      Salin apa adanya dari README. Hanya batas numerik yang dievaluasi
      pass/fail; PDF ber-text-layer dan teks tempel saja, tanpa OCR; satu
      workspace tanpa auth, dengan `/internal/*` OIDC-gated sebagai batas
      keamanan yang relevan; latensi 25,5 detik untuk satu aturan dan 174,3
      detik untuk aneks 55 klausa, terukur dan reproducible lewat
      `scripts/measure_latency.py`.
      **Jangan hapus bagian ini.** Kejujuran terukur adalah nilai jual repo ini,
      dan juri arsitektur membaca ini sebagai kekuatan.

### S5.2 · Kartu checklist submission — `docs/submission-checklist.md`

- [ ] Tabel siap centang berisi setiap field form dan nilai yang harus diisi:

| Field Devpost | Nilai |
|---|---|
| Category / Track | **Collaborative Partner** |
| Video URL | dari S3 |
| Hosted project URL | `https://regulens-web-babuvy7w3a-as.a.run.app` |
| Repository | `https://github.com/aliefauzan/ReguLens` |
| Architecture diagram | `docs/architecture.png` |
| Text description | dari `docs/submission-text.md` |
| Published content (bonus) | dari S4.1 |
| Social post (bonus) | dari S4.2 |

### S5.3 · Verifikasi pra-submit yang bisa Claude lakukan

- [ ] `curl -s -o /dev/null -w "%{http_code}" https://regulens-web-babuvy7w3a-as.a.run.app/`
      → harus `200`
- [ ] `curl -s -o /dev/null -w "%{http_code}" https://regulens-api-babuvy7w3a-as.a.run.app/health`
      → harus `200`
- [ ] Konfirmasi repo publik:
      `curl -s -o /dev/null -w "%{http_code}" https://api.github.com/repos/aliefauzan/ReguLens`
- [ ] Konfirmasi `docs/architecture.png` ada dan bukan file rusak
- [ ] Konfirmasi README baris pertama memuat URL video yang benar
- [ ] Konfirmasi tidak ada secret yang bocor sebelum repo dilihat juri:
      `grep -rn "AIza\|BEGIN PRIVATE KEY" --exclude-dir=node_modules --exclude-dir=.git .`
- [ ] Laporkan setiap hasil apa adanya. Kalau ada yang bukan 200, **katakan**,
      jangan diperhalus

---

## Bagian kamu (manusia)

- [ ] **Submit draf lebih dulu, revisi belakangan.** Devpost mengizinkan edit
      sampai deadline; yang tidak diizinkan adalah submit setelah deadline.
      **Jangan menunggu semuanya sempurna**
- [ ] Isi form memakai `docs/submission-checklist.md`
- [ ] Verifikasi terakhir dari mode incognito atau komputer lain:
      - [ ] Web live terbuka dan berfungsi
      - [ ] Repo terbaca tanpa login
      - [ ] Video bisa diputar tanpa login
- [ ] Kalau ini submission tim, pastikan komposisi peserta di Devpost benar.
      Hadiah **Individual/Hobbyist ($10.000 ×2)** punya syarat berbeda dari
      track utama, dan repo ini berada di `aliefauzan/` sementara commit
      ditandatangani `umarmuhdhor` — pastikan itu memang disengaja
- [ ] Tekan Submit **sebelum 1 Sep 2026 07:00 WIB**

### Setelah submit — bagian Claude lagi

- [ ] `plan/PROGRESS.md`: baris Devpost registration di §Blocked on the user
      dicentang, phase 7 → `COMPLETE` dengan tanggal
- [ ] Session log ditambah satu baris terakhir
- [ ] Commit: `docs(plan): submission filed`

---

## Selesai kalau

- [ ] Submission terkirim dan muncul di dashboard Devpost
- [ ] Semua verifikasi S5.3 hijau
- [ ] `plan/PROGRESS.md` mencerminkan keadaan akhir

---

## JANGAN dikerjakan di fase ini

- [~] Claude mengisi atau mengirim form Devpost. Itu tindakan atas nama akunmu
- [~] Menghapus bagian Honest limitations agar terlihat lebih kuat. Itu justru
      melemahkan yang paling dihargai juri arsitektur
- [~] Menunggu sampai jam terakhir untuk submit pertama kali
