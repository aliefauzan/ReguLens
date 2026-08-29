# S3 — Naskah & aset video

**Status:** `NOT STARTED` · **Estimasi:** 2 jam Claude + 4 jam kamu · **Claude:** ⚠️ sebagian
**Kapan:** setelah S2 · **Boleh dibuang:** ❌ **tidak pernah — ini fase yang menentukan hidup-matinya submission**

---

## Kenapa fase ini ada

Video adalah **deliverable wajib**. Tanpa video, submission gugur di Stage One
berapa pun bagusnya kode. Selain itu ia menyumbang sepertiga dari kriteria
Demo & Production Readiness (bobot 30%), yang menyebut eksplisit:
*"clarity of video"*, *"unedited execution proof"*, *"Google Cloud backend visibility"*.

Claude tidak bisa merekam layar. Yang Claude bisa: menulis **seluruh materinya**
sampai kamu tinggal membaca dan mengklik.

---

## Prasyarat

- [ ] S2 selesai — state pembuka bersih, timing terukur, tab Console siap
- [ ] Kalau S1 jadi: halaman Rencana Perbaikan sudah live

---

## Bagian Claude

### S3.1 · Naskah lengkap — `docs/demo/script.md`

- [ ] Tulis narasi **bahasa Inggris**, lengkap kata per kata. Jangan kerangka —
      improvisasi menghabiskan 4 menit lebih cepat dari dugaan
- [ ] Target durasi baca **3:40**, sisakan margin dari batas 4:00
- [ ] Format tiap segmen: `[waktu] AKSI DI LAYAR — narasi`
- [ ] Alokasi durasi:

| Waktu | Segmen | Yang wajib terlihat |
|---|---|---|
| 0:00–0:30 | Masalah | Satu produk, dua negara. Dua angka besar: **150 vs 400 mg/kg** |
| 0:30–1:00 | State awal | Indonesia lulus · **Jerman "No rules added yet", bukan "lulus"** |
| 1:00–1:30 | Aturan masuk | Paste aturan EU, lalu **tutup tab**. Narasi menyebut: nobody is watching this |
| 1:30–2:30 | **Google Cloud** | Pub/Sub, log worker dengan `trace_id`, `graph_events` bertambah, 4 service Cloud Run |
| 2:30–3:15 | Jawaban berubah sendiri | Jerman merah tanpa diminta · Disagreements dua sisi · Ask dengan sitasi · Jepang **menolak** |
| 3:15–4:00 | Arsitektur + kolaborasi | `docs/architecture.png` · review queue: sumber lemah **tidak mengubah apa pun** · (kalau S1 jadi) rencana perbaikan yang menunggu persetujuan |

- [ ] Naskah wajib menyebut angka latensi **dengan jujur**, kalimat semacam:
      *"A single rule lands in about 25 seconds. A 55-clause annex takes about
      three minutes — and we publish the measurement rather than the best case."*
      Kejujuran terukur menang atas angka bagus tanpa bukti, dan juri kriteria
      arsitektur menghargainya
- [ ] Naskah **tidak boleh** mengklaim: monitoring berkelanjutan, akurasi
      persentase, atau kemampuan yang tidak ada di repo
- [ ] Bingkai penutup ke **Collaborative Partner**: agent menyiapkan keputusan,
      manusia menyetujui. Bukan otomasi tanpa manusia

### S3.2 · Shot list — `docs/demo/shotlist.md`

- [ ] Satu baris per shot: nomor · durasi target · tab/URL yang dibuka ·
      apa yang diklik · apa yang harus terlihat di frame
- [ ] Tandai shot yang butuh label **"3× speed"** berdasarkan `docs/demo/timing.md`
- [ ] Tandai shot Console sebagai **prioritas tertinggi**: kalau durasi kurang,
      yang dipotong adalah segmen arsitektur, **bukan** segmen Console.
      Segmen Console paling sering dilewatkan peserta lain dan diminta eksplisit
      oleh kriteria

### S3.3 · Subtitle — `docs/demo/subtitles.srt`

- [ ] Buat `.srt` dari naskah, timestamp mengikuti alokasi durasi di S3.1
- [ ] Wajib: kriteria mengharuskan bahasa Inggris **atau** subtitle Inggris.
      File ini menutup syarat itu apa pun bahasa narasimu

### S3.4 · Deskripsi YouTube — `docs/demo/youtube.md`

- [ ] Judul: `ReguLens — an agent that tells you what a new regulation just broke`
- [ ] Deskripsi memuat: satu paragraf masalah, link live app, link repo, track
      (Collaborative Partner), stack (Gemini 3.5 · ADK · Cloud Run · Pub/Sub ·
      Firestore), dan timestamp per segmen

---

## Bagian kamu (manusia)

- [ ] Baca naskah keras sambil menghitung waktu. Kalau lewat 3:50, minta Claude
      memangkas — **jangan** membaca lebih cepat
- [ ] Rekam layar penuh, minimal 1080p
- [ ] **Tanpa potongan diam-diam.** Percepat hanya dengan label "3× speed" yang
      terlihat di layar. Kriteria menyebut "unedited execution proof"; memotong
      sunyi-sunyi adalah persis yang dilarang
- [ ] Upload ke YouTube — **Public**, atau Unlisted yang **tidak** butuh login
- [ ] Cek durasi akhir ≤ **4:00**. Cek angkanya, jangan diperkirakan
- [ ] Tonton sekali penuh sebagai orang asing: apakah masalahnya jelas dalam 30
      detik pertama? Kalau tidak, ulangi **segmen pembuka saja**
- [ ] Kirim URL video ke Claude untuk langkah terakhir di bawah

### Setelah video tayang — bagian Claude lagi

- [ ] Isi URL video ke blok teratas `README.md` (placeholder `_TODO_` dari S0.6)
- [ ] Isi URL video ke `docs/demo/youtube.md`
- [ ] Commit: `docs: link the demo video from the README`

---

## Verifikasi

- [ ] `docs/demo/script.md` ada, lengkap, dan waktu bacanya sudah diuji ≤ 3:50
- [ ] `docs/demo/shotlist.md` menandai shot Console sebagai prioritas tertinggi
- [ ] `docs/demo/subtitles.srt` valid dan sinkron dengan naskah
- [ ] Video tayang di URL publik dan bisa diputar **tanpa login** — uji di mode
      incognito
- [ ] README baris pertama memuat URL video yang benar

---

## Selesai kalau

- [ ] Video ≤ 4 menit tayang publik
- [ ] README dan `docs/demo/youtube.md` memuat URL-nya
- [ ] `plan/PROGRESS.md` Session log ditambah satu baris

---

## JANGAN dikerjakan di fase ini

- [~] Merekam money-shot dengan aneks EU 4 halaman. 174 detik tidak muat
- [~] Memotong waktu tunggu secara diam-diam. Pakai label kecepatan yang terlihat
- [~] Mengklaim di narasi apa pun yang tidak ada di repo. Setiap kalimat harus
      punya padanan yang bisa ditunjuk di kode atau di layar
- [~] Video unlisted yang butuh login, atau file yang harus diunduh dulu. Juri
      tidak akan mengejar akses
