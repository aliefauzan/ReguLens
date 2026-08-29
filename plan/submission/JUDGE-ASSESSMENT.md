# Penilaian Juri — All Things Agentic Hackathon

Dinilai: **29 Agu 2026**. Sumber kriteria: [devpost rules](https://allthingsagentichackathon.devpost.com/rules).
Deadline: **31 Agu 2026 17:00 PDT** = **1 Sep 2026 07:00 WIB**.

Diverifikasi live saat penilaian: API `200`, web `200`, repo publik, ADK terpakai
di 4 file, `docs/architecture.png` ada.

---

## Stage One — cek kelayakan (pass/fail)

| Syarat wajib | Status |
|---|---|
| Gemini 3.5+ via Gemini API atau Vertex | ✅ `gemini-3.5-flash`, dua jalur |
| ≥1 Google Agent Framework | ✅ ADK, 4 agent, tool body plain Python |
| ≥1 Google Cloud infra | ✅ Cloud Run ×4, Firestore, Pub/Sub, GCS, Secret Manager |
| Hosted URL bisa dites | ✅ keduanya 200 |
| Repo + README spin-up | ✅ |
| Diagram arsitektur | ✅ generated, bukan digambar tangan |
| Registrasi Devpost | ✅ terdaftar, track Collaborative Partner |
| Deskripsi teks Devpost | ⚠️ bahan ada di `regulens-session-summary.md`, belum diformat |
| **Video demo ~4 menit, Inggris** | ❌ **TIDAK ADA — satu-satunya blocker mati** |

> Tanpa video, submission gugur di Stage One berapa pun bagusnya kode.

---

## Kategori 1 — Innovation & Operational Utility · bobot 40% · **skor 4.0 / 5**

### Yang kuat

- Bukan chatbot. Verdict berubah **tanpa user minta** — persis definisi
  "beyond standard chat interfaces, background execution".
- Workflow multi-step asinkron nyata: upload → extract → reconcile → impact,
  3 topik Pub/Sub, tiap tahap idempoten.
- Friksi dunia nyata yang mahal: eksportir kecil tak punya tim hukum.
- Kejujuran arsitektural (Impact sengaja tanpa model — "aritmatika jangan
  didelegasikan ke model") menaikkan kredibilitas, bukan menurunkan.

### Yang menahan skor

1. **Agent berhenti di notifikasi.** Ia bilang "produkmu melanggar di Jerman",
   lalu selesai. Tidak ada draf reformulasi, dossier kepatuhan, tabel batas aman
   lintas pasar yang bisa diunduh, atau draf surat ke supplier. "High-value agent
   action" masih berplafon di alert. **Ini kerugian terbesar** — 40% bobot.
2. **"Living twin" yang hidupnya cuma saat di-upload.** README sendiri menghindari
   kata "monitoring" karena pipeline hanya jalan saat ada upload. Tak ada
   scheduled watcher. Untuk hackathon *agentic*, agent yang bangun hanya kalau
   manusia menekan tombol berkontradiksi dengan tagline "living compliance twin".
3. **Metadata kategori di repo salah tempat.** `regulens-session-summary.md:7`
   menulis kategori sebagai judul konsep, bukan sebagai track resmi Devpost.
   Harus disamakan dengan yang benar-benar didaftarkan.

---

## Kategori 2 — Architectural Discipline & Tech Stack · bobot 30% · **skor 4.5 / 5**

Kategori terkuat. Kandidat serius **Architectural Design Prize ($5.000)**.

| Yang dinilai | Bukti di repo |
|---|---|
| Decoupling | 3 topik Pub/Sub push + DLQ; worker privat, OIDC-gated |
| State / memory | Firestore knowledge graph + `graph_events` immutable + integrity walker |
| Credential security | Secret Manager (1 secret), IAM sempit, `.gitignore` diaudit, fallback Vertex bila key hilang |
| Failure handling | DLQ→failed→retry terbukti live; idempotensi teruji redelivery; tiap agent fallback ke jalur deterministik |
| Guardrail | model tak pernah menulis ke DB tanpa Pydantic + guardrail |

### Cacat yang terlihat saat juri membaca repo

1. **`plan/PROGRESS.md:43` bertentangan dengan README.**
   `- [ ] Secret Manager wired, no secrets in image or repo` masih kosong,
   sementara README menyatakan sudah terpasang dan `cloudbuild.yaml` memang
   memakai `--set-secrets`. Aturanmu sendiri berbunyi "box ticked = real" —
   sekarang aturan itu menusuk balik: juri percaya kotak kosong.
2. **`plan/phases/phase-6-e2e-testing.md:6` masih `NOT STARTED`** sementara
   `PROGRESS.md:33` menulis `IN PROGRESS`. Dua sumber kebenaran berbeda di dalam
   repo yang menjual dirinya sebagai disiplin dokumentasi.
3. **Tanpa auth sama sekali**, satu workspace hardcoded. Masih bisa dibela untuk
   Collaborative Partner dan Taskmaster. Untuk "Fortified Enterprise Fleet"
   langsung mati — jangan pilih track itu.
4. **CI hanya trigger manual** (`PROGRESS.md:42`). "Cloud Build pipeline green"
   benar, tapi push trigger belum ada.
5. **5 alert belum dikonfigurasi & belum pernah ditrigger** (`PROGRESS.md:47`).
   Observability diklaim di README, belum dibuktikan di kotak.

---

## Kategori 3 — Demo & Production Readiness · bobot 30% · **skor 2.0 sekarang / 4.5 dengan video**

### Yang kuat

- **Dokumentasi terbaik yang saya baca di batch ini.** `docs/USER_GUIDE.md`,
  README, evidence trail `plan/`, `SOURCES.md` dengan checksum, angka latensi
  **terukur** (`scripts/measure_latency.py`) bukan diingat. **5/5.**
- **Reproducible setup 5/5.** `regulens.env` + `scripts/quickstart.sh` — satu
  file, satu perintah, sudah dites dari clone bersih.

### Yang hilang

- **Video: 0/5. Tidak ada.** Kriteria menyebut eksplisit "clarity of video",
  "unedited execution proof", "Google Cloud backend visibility". Sepertiga dari
  30% hilang total.
- **Masalah fisik untuk video 4 menit:** aneks EU butuh **174 detik** propagasi
  (`README` §Honest limitations). Itu 72% durasi video habis menunggu.
  Money-shot tak bisa direkam real time apa adanya.
- **Playwright shell formal belum ada.** Ringan dampaknya — `verify_e2e.sh` dan
  `verify_local.sh` sudah jadi bukti eksekusi yang lebih kuat untuk juri.

---

## Skor akhir

```
Sekarang (tanpa video)     : GAGAL Stage One          → 0
Video ala kadarnya         : 4.0(.4)+4.5(.3)+3.0(.3)  → 3.85 / 6
Video bagus                : 4.0(.4)+4.5(.3)+4.5(.3)  → 4.30 / 6
Video bagus + P1 + P3      : 4.5(.4)+4.7(.3)+4.5(.3)  → 4.56 + 0.4 bonus → 4.96 / 6
Bonus terpakai saat ini    : 0.0 / 0.6
```

**Posisi jujur hari ini:** Honorable Mention sampai Architectural Design Prize.
**Bukan** Grand Prize — tertahan oleh "agent memberi tahu, tidak bertindak" dan
bonus nol.

---

## Soal track: tetap **Collaborative Partner**

Rekomendasi awal saya adalah pindah ke Taskmaster. **Saya cabut rekomendasi itu**
setelah membaca ulang rules dengan fakta bahwa kamu sudah terdaftar. Alasannya:

**1. Rubriknya identik di semua track.** Rules hanya mendefinisikan satu set
kriteria berbobot (40/30/30) yang dipakai untuk seluruh submission. Track
menentukan **kolam hadiah $20.000 mana yang kamu perebutkan**, bukan dengan
penggaris apa kamu diukur. Jadi pindah track menaikkan skor **nol poin**.

**2. Taskmaster adalah track paling ramai.** "Multi-step workflow automation"
adalah bentuk paling umum agent hackathon. Collaborative Partner lebih sepi.

**3. Bukti Collaborative Partner-mu sebenarnya kuat dan belum kamu klaim:**

| Bukti di kode | Kenapa ini "adaptive guidance with feedback loops" |
|---|---|
| Review queue (`/review`) | Klausa berkeyakinan rendah **tak mengubah apa pun** sampai manusia menerimanya. Feedback loop harfiah |
| `authority_tier` di rumus keyakinan | Sumber lemah dibatasi *by construction*, lalu dikembalikan ke manusia |
| `core/detection.py` | Tebakan ragu diserahkan ke user, tak pernah diam-diam default; setiap jawaban mengutip frasa asalnya |
| `INSUFFICIENT_EVIDENCE` | Agent mengaku tak tahu, bukan mengarang. Kemitraan, bukan otomasi buta |
| `GET /substances/resolve` | "ini makanan, bukan yang bisa dicek" — memandu, tidak memaksa |
| Kartu "What to do next" | Panduan berikutnya dihitung dari state nyata |

**4. Kritik "agent berhenti di notifikasi" justru melunak di track ini.** Agent
kolaboratif memang seharusnya menyerahkan keputusan ke manusia. Yang harus kamu
tunjukkan bukan aksi otonom penuh, melainkan **agent yang menyiapkan pekerjaan
manusia sampai tinggal disetujui** — itulah bentuk P3 Opsi A di `UPGRADES.md`.

**Kesimpulan: jangan pindah.** Dua hari sebelum deadline, jangan belanjakan risiko
untuk perubahan yang bernilai nol poin. Yang perlu dilakukan hanyalah
**membingkai ulang narasi** submission dan video ke arah kolaborasi
manusia–agent, bukan otomasi tanpa manusia.

---

## Yang JANGAN dikerjakan

- **Auth / multi-tenant** — tidak dinilai di track ini, dan README sudah jujur.
- **Playwright shell formal** — `verify_e2e.sh` sudah bukti yang lebih baik.
- **Mengejar target latensi 90s** — kamu sudah menjelaskannya dengan angka
  terukur. Kejujuran terukur menang atas angka bagus tanpa bukti.

---

Rencana perbaikan: [`UPGRADES.md`](UPGRADES.md) ·
Daftar kerja langkah demi langkah: [`ACTION-PLAN.md`](ACTION-PLAN.md)
