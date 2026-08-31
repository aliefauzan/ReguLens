# ReguLens — Video Plan v2 (4:00 exact)

Supersedes the beat order in `VIDEO-SCRIPT.md`. Same facts, same numbers,
re-cut so every second buys a judging point. Read `VIDEO-SCRIPT.md` for the
"do not say" list and the failure lines — they still apply verbatim.

## The numbers (do not improvise these)

| | Value | Source |
|---|---|---|
| Product *Herbal Drink Powder*, sodium benzoate | **300 mg/kg** | `api/app/core/samples.py` |
| BPOM 14.1.4.1 natrium benzoat | **400 mg/kg** | Perka BPOM 11/2019 |
| EU Annex II 14.1.4, E 210–213 | **150 mg/kg** | Reg. (EU) 1129/2011 |

300 is under 400 and over 150. That is the whole demo.

## Rules → where each requirement is satisfied

| Devpost requirement | Beat |
|---|---|
| Problem being solved | 0 |
| Value proposition | 1, 6 |
| Live app functionality | 1–8 |
| Backend on Google Cloud (console / Cloud Run / `.run.app` visible) | 9, plus the URL bar in every beat |
| Gemini 3.5+ | 3 (extraction), 9 (VO names it) |
| Google agent framework (ADK) | 4, 7 (VO), 9 (baris log `adk extraction complete`, `query agent complete`, `judge agent complete`) |
| Google Cloud infra (Cloud Run, Pub/Sub, Firestore) | 9 |

| Judging axis | Weight | Beats that earn it |
|---|---|---|
| Innovation & Operational Utility | 40% | 5 (unprompted flip), 6 (remediation draft), 8 (scheduler + country discovery) |
| Architectural Discipline & Tech Stack | 30% | 3, 4, 7, 9 |
| Demo & Production Readiness | 30% | 2, 9, 10 |

## Why this cut differs from v1

- v1 spent 25s on the audit timeline and the `/sources` list, and spent **zero**
  on the two things that read as *agentic*: the remediation draft the alert
  hands you, and Phase 9 country discovery. Those move the 40% axis.
- The timeline is folded into beat 5 (the event log is on the same screen).
- What-if is cut. It is a good feature and a weak 15 seconds.

---

# The 4:00 timeline

Runtime is exact. Word budget ≈ 2.5 words/second at a calm pace.

| # | Time | Screen | Words |
|---|---|---|---|
| 0 | 0:00–0:15 | the two regulation excerpts | ~35 |
| 1 | 0:15–0:33 | `/products/{id}` | ~44 |
| 2 | 0:33–0:48 | `/documents/new` | ~36 |
| 3 | 0:48–1:10 | `/documents/{id}` stepper | ~54 |
| 4 | 1:10–1:32 | `/conflicts` | ~54 |
| 5 | 1:32–2:02 | `/` dashboard, alert + impact chain | ~70 |
| 6 | 2:02–2:20 | `/products/{id}/remediation` | ~44 |
| 7 | 2:20–2:38 | `/products/{id}` ask panel | ~44 |
| 8 | 2:38–3:05 | `/sources` | ~66 |
| 9 | 3:05–3:42 | GCP console, 4 windows | ~88 |
| 10 | 3:42–4:00 | `/` dashboard | ~44 |

---

## Beat 0 · The problem — 0:00–0:15

**Tampilan:** dua kutipan regulasi berdampingan, keduanya sudah di-scroll ke
baris benzoat. Highlight kuning di angka **400** dan **150**. Tidak ada UI.

> "A drink powder sold into Indonesia and Germany. Indonesia allows sodium
> benzoate up to 400 milligrams per kilo. The EU allows 150. This product is at
> 300 — legal in one market, illegal in the other. Nobody emails you when
> either number moves."

## Beat 1 · The twin — 0:15–0:33

**Tampilan:** `/products/{id}`. Terlihat: `data-testid="compliance-twin"`,
`twin-ingredients` dengan angka nyata, dan **"Can you sell it?"** —
Indonesia `compliant`, Germany `unknown`. URL `.run.app` terlihat di address bar.

**Aksi:** scroll pelan sekali dari ingredients ke kartu verdict. Jangan klik.

> "ReguLens keeps a structured model of the actual product — ingredients,
> amounts, packaging, target markets — not a document it read. Indonesia is
> compliant: we have the BPOM rule. Germany says unknown, because no EU rule
> has entered the graph yet. Unknown, not a guess."

## Beat 2 · The upload and the source tier — 0:33–0:48

**Tampilan:** `/documents/new`. Paste kutipan EU Annex II 14.1.4. Kursor
berhenti sebentar di selector jenis sumber, tetap di **Official Regulation**.

> "Everything enters through one path. How authoritative a source is changes
> what the system will do with it: an official regulation may rewrite state, a
> forwarded message is capped and routed to review. Submit."

## Beat 3 · The pipeline, live — 0:48–1:10

**Tampilan:** `/documents/{id}` — `pipeline-stepper` bergerak
Extracting → Extracted → Reconciling, `elapsed` berjalan, lalu `clause-list`.
Buka satu clause: substance, limit **150**, unit mg/kg, jurisdiction, effective
date, confidence. Hover confidence untuk memunculkan rinciannya.

> "The clause comes out verbatim with its citation, extracted by Gemini 3.5
> Flash. That confidence is not the model grading itself — it is parse quality,
> agreement across two independent extractions, and the authority tier of the
> source, in fixed weights. Under the floor, it mutates nothing and waits for a
> human."

## Beat 4 · The guardrail — 1:10–1:32

**Tampilan:** `/conflicts`. Terlihat kartu konflik EU vs BPOM, label
**"Stricter — follow this one"**, **"Maximum allowed"**, dan **"What to do:"**.

> "Before any model sees a pair of clauses, ordinary typed code decides whether
> they may even be compared — same substance, same food category, comparable
> units, comparable dates. Pairs that fail are rejected with a stated reason.
> The model is only called on pairs that pass, through an ADK agent, and the
> model never writes to the database. Deterministic code owns every mutation."

## Beat 5 · The flip, unprompted — 1:32–2:02 · **money beat**

**Tampilan:** navigasi ke `/`. Jangan refresh manual. Banner sudah ada:

```
⚠  Herbal Drink Powder — Germany
    compliant  →  NON-COMPLIANT
    sodium benzoate 300 mg/kg exceeds EU limit 150 mg/kg
```

Klik **"See why"** (`alert-see-why`) → `impact-chain` terbuka:
regulation → clause → requirement → product → Germany. Lalu scroll 3 detik ke
`event-log` di halaman produk, berhenti di baris transisi.

> "Nobody asked a question. A document arrived, the graph changed, and the
> system worked out on its own which product that broke, in which market, and
> why. Here is the chain it followed — regulation, clause, requirement,
> product, market. And every state change is an immutable event written in the
> same batch as the change itself. That is what you show a regulator: when your
> status moved, and which document moved it."

Kalau ada satu take yang harus sempurna, ini.

## Beat 6 · It drafts the fix — 2:02–2:20

**Tampilan:** klik **"Prepare fix"** (`alert-prepare-fix`) →
`/products/{id}/remediation`. Terlihat `targets` ("It has today" / "It needs to
be at most"), `strictest-flag`, `draft-notice` ("This is a draft for you to
check, not an action we took"), dan `not-checked`.

> "It does not stop at a red flag. It works out the number the recipe has to
> hit to clear every market you target, and names the rule that binds. It also
> prints what it did not check — labelling and certification clauses are
> extracted, not evaluated. It calls the draft a draft. It does not edit your
> product behind your back."

## Beat 7 · Grounded answer, honest refusal — 2:20–2:38

**Tampilan:** kembali ke `/products/{id}`, `ask-panel`. Ketik
*"Why is my product at risk in Germany?"*. Tunggu `answer-card` +
`citations`. Lalu satu pertanyaan kedua tentang pasar tanpa data →
`refusal-flag` muncul.

> "The query agent picks its own tools and cites what it read. Every clause id
> in that answer is checked in code against what retrieval actually served — an
> invented citation cites nothing and never reaches the screen. Ask about a
> market it has no data for and it refuses, with zero citations."

## Beat 8 · It goes and finds the rules — 2:38–3:05

**Tampilan:** `/sources`. Mulai dari `autonomy-panel` — angka
"regulations read / rules extracted / verdicts changed / checks run", lalu
tabel alamat yang diawasi dengan last check dan status error kalau ada. Terakhir
`discover-panel` — ketik sebuah negara, tekan Watch, potong ke hasil
`discover-matches` yang sudah jadi (lihat catatan B-roll).

> "None of this needed a person. A scheduled sweep re-reads regulator addresses
> daily. A change means the wording changed, not the bytes — a session id in a
> response must not bill us for a model run. Anything new enters through the
> same path the upload just took. And if you sell into a country nobody
> configured, it finds the regulator itself: the model names the agency and the
> root domain, then every link is read off pages actually fetched, never
> invented."

## Beat 9 · Google Cloud proof — 3:05–3:42 · **required**

**Screen capture, tanpa UI produk. Tiga perhentian, sudah login sebelum rekam.**

### 1 · Cloud Run — 3:05–3:17

Halaman daftar service. Terlihat `regulens-api`, `regulens-worker`,
`regulens-web` semua hijau. Klik `regulens-api`, tunjukkan grafik request yang
naik karena run barusan, lalu tab **Jobs** untuk `regulens-job` (`seed`).

### 2 · Logs Explorer — 3:17–3:33

Query pertama, tempel sekali, jangan diketik di kamera:

```
resource.type="cloud_run_revision"
(jsonPayload.message="vertex_call" OR jsonPayload.message:"agent complete")
```

Buka satu baris `vertex_call`. Yang harus terlihat di payload:
`model: "gemini-3.5-flash"`, `stage: "extraction"`, `latency_ms`,
`usage_metadata`, `trace_id`. Di baris lain terlihat `adk extraction complete`,
`query agent complete` dengan `tool_calls`, dan `judge agent complete` dengan
`verdict`. Itu bukti Vertex AI dan bukti ADK dalam satu layar.

Lalu **ganti query-nya di depan kamera** ke:

```
resource.type="cloud_run_revision"
jsonPayload.message="discovery finished"
```

Buka satu baris. Payload menunjukkan `model: "gemma-4-31b-it"`, `country`,
`committed`. Dua model berbeda untuk dua pekerjaan berbeda, terbukti dari log,
bukan dari klaim.

### 3 · Firestore — 3:33–3:42

Collection `products`, buka dokumen produk yang tadi diunggah. Lalu collection
`requirements`, tunjukkan `limit_value` = 150. Itu tulisan worker, bukan
tulisan UI.

> "Cloud Run. One container image, deployed by Cloud Build as three services
> and a job: the API, the worker behind Pub/Sub, and the web app. Request
> counts moved while I recorded. Now the logs. Every line is structured JSON
> with a trace id. Here is the extraction call: Vertex AI, Gemini 3.5 Flash,
> with token usage, and the ADK agents logging the tools they chose. Change the
> query, and here is discovery running on gemma. And Firestore: the product I
> uploaded, and the requirement now reading 150."

**Syarat sebelum segmen ini bisa direkam**

- Discovery harus sudah pernah jalan hari itu, kalau tidak `discovery finished`
  tidak ada di log dan query kedua kosong di kamera.
- Log Cloud Run hanya menyimpan 30 hari, jadi rentang waktu di Logs Explorer
  disetel ke **Last 1 hour** supaya yang muncul run hari ini.
- `GOOGLE_GENAI_USE_VERTEXAI=true` memang diset di ketiga service di
  `cloudbuild.yaml`, jadi kata "Vertex AI" di narasi itu benar. Kalau suatu saat
  deployment beralih ke Gemini API key, ganti satu kata itu, jangan dibiarkan.

## Beat 10 · Close — 3:42–4:00

**Tampilan:** kembali ke `/`, alert terlihat, kursor diam.

> "ReguLens watches the regulators, reconciles what changes against what it
> already knew, and tells an exporter what broke, why, and with what evidence.
> The model reasons. It never decides."

---

# Produksi

## Sebelum rekam

- [ ] Jalankan `seed` Job (atau **Try it with sample data**): produk ada, aturan
      BPOM aktif, Indonesia `compliant`, Germany `unknown`.
- [ ] **Aturan EU belum di-ingest.** Itu titik baliknya.
- [ ] `min-instances=1` aktif di api dan web — jangan rekam cold start.
- [ ] Browser 1920×1080, zoom 100%, bookmark bar disembunyikan, satu tab,
      profil bersih tanpa ekstensi.
- [ ] Tab kedua sudah login di Cloud Console, dan tiga tab-nya sudah dibuka
      duluan: Cloud Run, Logs Explorer, Firestore. Jangan rekam layar login dan
      jangan rekam halaman yang masih loading.
- [ ] Dua query Logs Explorer sudah ada di clipboard atau di file teks. Di beat
      9 keduanya ditempel, tidak diketik.
- [ ] Sekali dry run bisu penuh. Ekstraksi kutipan EU terukur **25.5s** di stack
      deployed — kenali jedanya sebelum mikrofon menyala.
- [ ] Buka `/sources` sekali sebelum rekam supaya angka `autonomy-panel` sudah
      terisi, dan cek tidak ada sumber yang error merah (kalau ada, tetap
      tunjukkan — itu justru poin kejujuran; sebut satu kalimat).

## B-roll yang direkam terpisah lalu di-cut

- **Beat 8 discovery.** Discovery adalah job multi-hop (fetch, pilih dari
  inventory, turunkan pattern). Jangan tunggu live. Rekam sekali sampai selesai,
  lalu potong ke hasil. Narasi tetap satu tarikan.
- **Beat 9 seluruhnya.** Rekam sesudah run utama supaya grafik request Cloud Run
  benar-benar bergerak karena demo itu.
- **Beat 3** kalau ekstraksi melewati 30 detik: potong jeda, jangan potong
  stepper — perpindahan state adalah buktinya.

## Urutan editing

1. Rekam beat 0–8 satu tarikan, satu take. Potong, jangan ulang.
2. Rekam beat 9 di console: Cloud Run, lalu Logs Explorer dengan dua query,
   lalu Firestore.
3. Tempel beat 9 di antara beat 8 dan beat 10.
4. Tempel B-roll discovery ke dalam beat 8.
5. Tambahkan caption angka besar di beat 0 (400 / 150 / 300) dan di beat 5
   (`compliant -> NON-COMPLIANT`). Selain itu tanpa efek.
6. Bar tipis di bawah sepanjang video: `regulens-web-babuvy7w3a-as.a.run.app`.
   Itu juga bukti hosting.
7. Render subtitle Inggris ke dalam gambar (burned in), bukan track caption.
   Aturannya ada di bagian subtitle di akhir dokumen.

## Kalau gagal di tengah take

- **Ekstraksi macet:** bilang "we've already run this one — here's the cached
  result", lanjut dari beat 4. Content-hash cache-nya nyata, bukan trik.
- **Query lambat:** terus bicara di atas panel evidence; evidence render duluan.
- **Hard fail:** stop, reseed, ulang. Take 4 menit itu murah.

## Jangan diucapkan

Ikuti daftar di `VIDEO-SCRIPT.md`: tidak boleh "real-time" atau "continuous"
(ini re-read terjadwal harian), tidak ada persentase readiness, "knowledge
graph" harus dikualifikasi, dan jangan mengklaim evaluasi klausul labelling
atau sertifikasi — itu diekstrak dan ditandai `needs_review`, bukan dinilai.

---

# VO versi Bahasa Indonesia

Ini versi yang dipakai. Narasi bahasa Indonesia, subtitle Inggris **hardcoded**
ke dalam video (burned in), bukan caption YouTube yang bisa dimatikan penonton.
Juri Devpost berbahasa Inggris dan mereka tidak akan menyalakan caption sendiri.

Ditulis untuk dibaca keras, bukan untuk dibaca di layar. Kalimatnya pendek,
anak kalimatnya tidak bertumpuk, dan tidak ada istilah yang butuh dieja pelan.
Kalau satu kalimat bikin Anda kehabisan napas waktu latihan, potong jadi dua.
Jangan tambah kalimat baru, karena semua jatah waktu di bawah sudah pas.

Kecepatan aman: 2,3 sampai 2,5 kata per detik. Jumlah kata tiap beat sudah
dihitung untuk itu.

Istilah teknis dibiarkan dalam bahasa Inggris karena penonton mencocokkannya
dengan yang muncul di layar: Cloud Run, Pub/Sub, Firestore, Cloud Build, ADK,
Gemini 3.5 Flash, dead-letter, clause, requirement, guardrail, compliant,
unknown.

## Beat 0 · Masalah, 0:00 sampai 0:15 (39 kata)

> "Satu bubuk minuman, dua pasar: Indonesia dan Jerman. Indonesia mengizinkan
> natrium benzoat 400 miligram per kilo, Uni Eropa 150. Produk ini isinya 300.
> Legal di satu pasar, melanggar di satunya. Dan kalau angka itu berubah, tidak
> ada yang memberi tahu."

## Beat 1 · Kembaran produk, 0:15 sampai 0:33 (40 kata)

> "ReguLens menyimpan model produknya: bahan, takaran, kemasan, pasar tujuan.
> Bukan dokumen yang dibaca, tapi produknya sendiri. Indonesia sudah compliant,
> karena aturan BPOM-nya sudah masuk. Jerman masih unknown, karena belum ada
> aturan Uni Eropa yang masuk. Sistem menulis unknown daripada menebak."

## Beat 2 · Unggah dan tingkat sumber, 0:33 sampai 0:48 (33 kata)

> "Semua aturan masuk lewat satu jalur yang sama. Seberapa resmi sumbernya
> menentukan apa yang boleh dilakukan sistem. Regulasi resmi boleh mengubah
> status produk. Pesan berantai tidak, dan langsung masuk antrean review. Saya
> kirim."

## Beat 3 · Pipeline berjalan, 0:48 sampai 1:10 (50 kata)

> "Clause-nya keluar apa adanya, lengkap dengan sitasinya, hasil ekstraksi
> Gemini 3.5 Flash. Angka confidence itu bukan model yang menilai dirinya
> sendiri. Isinya kualitas parsing, kecocokan dua ekstraksi yang jalan
> terpisah, dan seberapa resmi sumbernya, dengan bobot tetap. Di bawah ambang,
> sistem tidak mengubah apa pun dan menunggu orang memeriksa."

## Beat 4 · Guardrail, 1:10 sampai 1:32 (51 kata)

> "Sebelum model melihat sepasang clause, yang memutuskan boleh tidaknya
> dibandingkan adalah kode biasa. Zatnya harus sama, kategori pangannya sama,
> satuan dan tanggalnya sebanding. Pasangan yang gagal ditolak, dan alasannya
> ditulis. Model cuma dipanggil untuk pasangan yang lolos, lewat agent ADK.
> Model tidak pernah menulis ke database; yang mengubah data selalu kode."

## Beat 5 · Verdict berubah sendiri, 1:32 sampai 2:02 (68 kata) · beat kunci

> "Tidak ada yang bertanya apa pun. Satu dokumen masuk, graph-nya berubah, dan
> sistem sendiri yang menyimpulkan produk mana yang jadi bermasalah, di pasar
> mana, dan kenapa. Ini rantai yang dia telusuri: regulasi, clause,
> requirement, produk, pasar. Setiap perubahan status juga ditulis jadi event
> permanen, di batch yang sama dengan perubahannya. Jadi kalau regulator
> bertanya, Anda bisa menunjukkan kapan status Anda berubah dan dokumen mana
> yang mengubahnya."

## Beat 6 · Sistem menyusun perbaikannya, 2:02 sampai 2:20 (44 kata)

> "Sistem tidak berhenti di tanda merah. Dia menghitung angka yang harus
> dicapai resep ini supaya lolos di semua pasar tujuan, dan menyebut aturan
> mana yang paling mengikat. Dia juga mencetak apa yang tidak dia periksa. Ini
> rancangan saja; produk Anda tidak diubah diam-diam."

## Beat 7 · Jawaban berbukti, 2:20 sampai 2:38 (43 kata)

> "Query agent memilih tool-nya sendiri, lalu menyitir apa yang benar-benar dia
> baca. Setiap id clause di jawaban itu dicek di kode terhadap data yang tadi
> diambil. Sitasi karangan tidak menunjuk apa pun dan tidak pernah sampai ke
> layar. Kalau datanya belum ada, dia menolak menjawab."

## Beat 8 · Sistem mencari aturannya sendiri, 2:38 sampai 3:05 (64 kata)

> "Tidak ada bagian ini yang butuh manusia. Setiap hari ada sapuan terjadwal
> yang membaca ulang alamat regulator. Yang dihitung berubah itu kata-katanya,
> bukan byte-nya, supaya session id di dalam respons tidak menagih kita satu
> panggilan model. Apa pun yang baru masuk lewat jalur yang sama dengan
> unggahan tadi. Dan untuk negara yang belum diatur siapa pun, sistem mencari
> regulatornya sendiri. Model menyebut lembaga dan domain utamanya, sisanya
> dibaca dari halaman yang benar-benar diambil."

## Beat 9 · Bukti Google Cloud, 3:05 sampai 3:42 (82 kata) · wajib

Tiga perhentian: Cloud Run, Logs Explorer, Firestore. Query log-nya ada di beat
9 versi Inggris di atas.

> "Ini Cloud Run. Satu image container, di-deploy Cloud Build jadi tiga service
> dan satu job: API, worker yang jalan di belakang Pub/Sub, dan web-nya. Grafik
> request-nya naik waktu saya merekam tadi. Sekarang lognya. Semua baris
> berbentuk JSON dan punya trace id. Ini panggilan ekstraksinya: Vertex AI,
> Gemini 3.5 Flash, lengkap dengan pemakaian token. Di bawahnya agent ADK
> mencatat tool yang dia pilih. Saya ganti query-nya, dan ini discovery yang
> jalan pakai gemma. Terakhir Firestore: produk yang tadi saya unggah, dan
> requirement-nya sekarang 150."

## Beat 10 · Penutup, 3:42 sampai 4:00 (40 kata)

> "ReguLens mengawasi regulator, membandingkan yang berubah dengan yang sudah
> dia tahu, lalu memberi tahu eksportir apa yang rusak, kenapa, dan buktinya
> apa. Modelnya yang bernalar, tapi keputusannya tidak pernah di tangan model.
> Semuanya jalan di Google Cloud."

## Cara membacanya

Baca seperti menjelaskan ke rekan kerja yang duduk di sebelah Anda, bukan
seperti membaca pengumuman. Lebih lambat sedikit dari yang terasa wajar, karena
di rekaman selalu terdengar lebih cepat.

- "mg/kg" dibaca miligram per kilo. Jangan dieja per huruf.
- 400, 150, dan 300 selalu disebut utuh.
- `compliant`, `unknown`, dan `NON-COMPLIANT` dibaca dalam bahasa Inggris.
- Beat 5 diberi jeda satu ketuk sesudah "Tidak ada yang bertanya apa pun."
  Itu klaim utama produk dan penonton butuh sepersekian detik untuk mencernanya.
- Beat 9 dibaca paling cepat di antara semuanya, karena gambarnya berpindah
  empat kali. Latih beat ini terpisah.

## Subtitle Inggris

- Pakai terjemahan dari VO Inggris di bagian atas dokumen ini. Jangan
  menerjemahkan ulang dari bahasa Indonesia, karena angka dan istilahnya bisa
  bergeser.
- Maksimal dua baris, sekitar 42 karakter per baris, minimal 1,5 detik per kartu.
- Posisikan agak naik dari dasar layar supaya tidak menutupi alert banner di
  beat 5 dan tabel di beat 8.
- Teks putih, latar hitam semi transparan. Kontras ini yang selamat kalau juri
  menonton di layar laptop kecil.
- Angka dan nama service ditulis persis: 400 mg/kg, 150 mg/kg, 300 mg/kg,
  Cloud Run, Pub/Sub, Firestore, Gemini 3.5 Flash.
- Render ke dalam video (burned in). Jangan mengandalkan track caption.
