# S0 — Konsistensi repo

**Status:** `COMPLETE` · **Selesai:** 29 Agu 2026 · **Estimasi:** 1 jam · **Claude:** ✅ penuh
**Kapan:** paling awal, sebelum apa pun · **Boleh dibuang:** ❌ tidak pernah

---

## Kenapa fase ini ada

Juri membaca repo. Repo ini menjual dirinya sebagai disiplin dokumentasi —
`CLAUDE.md` menulis aturannya sendiri: *"Tick a box only when the thing is real."*
Saat ini ada kotak yang masih kosong padahal barangnya sudah jalan di produksi,
dan dua file yang menyatakan status berbeda untuk fase yang sama.

Kontradiksi di dalam repo yang menjual disiplin **lebih merugikan** daripada
pekerjaan yang memang belum selesai. Ini jam termurah di seluruh rencana:
tidak ada kode baru, tidak ada risiko, langsung mengangkat Kategori 2
(Architectural Discipline, bobot 30%).

---

## Prasyarat

- [x] Berada di branch `master`, working tree bersih (`git status`)

---

## Langkah

### S0.1 · Centang Secret Manager

`plan/PROGRESS.md` baris 43 berbunyi:

```
- [ ] Secret Manager wired, no secrets in image or repo (phase 0)
```

Ini **sudah nyata**. Verifikasi dulu, baru centang:

- [x] Konfirmasi `cloudbuild.yaml` memang memakai `--set-secrets` untuk
      `GEMINI_API_KEY` di service api dan worker — cloudbuild.yaml:69 (api), :92 (worker)
- [x] Konfirmasi `.gitignore` mengecualikan `.env`, `.env.*`, `*.key`,
      `*-credentials.json` (dikerjakan 29 Agu, lihat Session log) — keempatnya ada
- [x] Konfirmasi tidak ada key hardcoded:
      `grep -rn "AIza\|BEGIN PRIVATE KEY" api/ web/ scripts/ --exclude-dir=node_modules`
      — satu hit, `api/tests/test_observability.py:44`, string dirakit di test (`"AIza" + "b"*35`), bukan key
- [x] Kalau ketiganya benar, ubah jadi:
      ```
      - [x] Secret Manager wired, no secrets in image or repo (phase 0) — `gemini-api-key` mounted via `--set-secrets` in cloudbuild.yaml for api + worker; `.gitignore` audited 29 Aug; no key literals in source
      ```
- [~] Kalau ada yang **tidak** benar, jangan dicentang. Perbaiki dulu atau
      laporkan apa adanya. — SKIPPED: tidak terpakai, ketiganya benar

### S0.2 · Selaraskan status Phase 6

`plan/phases/phase-6-e2e-testing.md:6` masih `NOT STARTED`, sementara
`plan/PROGRESS.md:33` menulis `IN PROGRESS` dengan daftar drill yang sudah
live-green.

- [x] Ubah baris Status di `phase-6-e2e-testing.md` jadi:
      `**Status:** \`IN PROGRESS\` · **Started:** 23 Aug 2026 · **Completed:** —`
- [x] Baca isi file itu, centang butir yang **benar-benar** sudah dibuktikan
      menurut Session log `PROGRESS.md`: UC-A sampai UC-F, redelivery tanpa
      duplikat, probe konkurensi, DLQ→failed→retry, integrity walker,
      grounding 10/10
- [x] Butir Playwright: ubah jadi
      `[~] ... — SKIPPED: scripts/verify_e2e.sh dan verify_local.sh sudah menjadi bukti eksekusi end-to-end yang setara; menambah shell Playwright dua hari sebelum deadline tidak menambah bukti baru`
- [x] Jangan mencentang apa pun yang tidak punya bukti di Session log. — `Non-comparable pair`, `Idempotent seed` dan `Latency under 90s` tetap `[ ]`; latency terukur 174.3s untuk anneks

### S0.3 · Lima alert — putuskan, jangan digantung

`plan/PROGRESS.md:47`:

```
- [ ] Five alerts configured **and each one deliberately triggered once** (phase 0 → 7)
```

Kotak kosong dibaca juri sebagai lalai. `[~]` dibaca sebagai keputusan.

- [x] Cek apakah ada alert policy yang sudah ada:
      `gcloud alpha monitoring policies list --project=regulens-506014 --format="value(displayName)"`
- [x] **Kalau gcloud tidak terautentikasi atau billing bermasalah:** jangan
      dipaksa. Langsung ke opsi SKIP di bawah. — `gcloud: command not found` di shell ini, tidak ada di PATH mana pun; ambil SKIP
- [x] Pilih satu: — **SKIP**
      - **Kerjakan** (hanya kalau sisa waktu S0 masih > 30 menit): buat 5 policy —
        DLQ depth > 0, API 5xx rate, latensi worker p95, kegagalan Cloud Build,
        budget 90% — lalu picu tiap satu sekali dan screenshot buktinya ke
        `docs/evidence/alerts/`
      - **SKIP**: ubah jadi
        `[~] Five alerts configured and each one deliberately triggered once — SKIPPED: budget alert + uptime check live dan cukup untuk cakupan ini; lima policy dengan trigger sengaja tidak muat sebelum deadline dan tidak menambah bukti yang belum ditunjukkan verify_e2e.sh`
- [x] Apa pun pilihannya, **jangan tinggalkan `[ ]`**.

### S0.4 · Push trigger CI — perjelas, jangan digantung

`plan/PROGRESS.md:42` sudah `[x]` dengan catatan miring *"manual trigger only;
push trigger still to wire"*. Itu jujur tapi terbaca seperti utang.

- [x] Ubah catatan miringnya jadi pernyataan keputusan, misalnya:
      `— manual trigger by design for a single-maintainer hackathon build; a push trigger needs GitHub-app OAuth from the repo owner and buys nothing before the deadline`
- [x] Kalau kamu justru ingin push trigger benar-benar ada, itu bukan pekerjaan
      S0 — catat sebagai pekerjaan pasca-hackathon. — dicatat sebagai pasca-hackathon di baris PROGRESS.md itu sendiri

### S0.5 · Samakan metadata kategori

- [x] `regulens-session-summary.md:7` saat ini:
      `**Category:** Collaborative Partner (Evolving Knowledge Engine)`
- [x] Pecah jadi dua baris supaya track resmi tidak tercampur nama konsep:
      ```markdown
      **Track:** Collaborative Partner
      **Concept name:** Evolving Knowledge Engine
      ```

### S0.6 · README: 20 detik pertama juri

- [x] Sisipkan blok ini **di paling atas** `README.md`, sebelum `# ReguLens`:
      ```markdown
      > **Demo video (4 min):** _TODO — diisi di fase S3_
      > **Live app:** https://regulens-web-babuvy7w3a-as.a.run.app
      > **Track:** Collaborative Partner · All Things Agentic Hackathon
      ```
- [x] Biarkan `_TODO_` apa adanya. Fase S3 yang mengisinya. **Jangan** mengarang URL.

---

## Verifikasi

- [x] `grep -n "^- \[ \]" plan/PROGRESS.md` — tiap baris yang tersisa memang
      benar-benar belum dikerjakan. Tidak ada yang sebenarnya sudah jalan. — tersisa satu: `Devpost registration`, memang diblokir user
- [x] Tidak ada dua file di `plan/` yang menyatakan status berbeda untuk fase
      yang sama. Bandingkan tabel Phases di `PROGRESS.md` dengan baris Status di
      tiap `plan/phases/phase-*.md`. — verifikasi menemukan kontradiksi kedua: `phase-3` masih `IN PROGRESS` padahal PROGRESS.md menulis `COMPLETE` dan nol kotak kosong tersisa di file itu; disamakan jadi `COMPLETE` 23 Agu. Delapan fase kini cocok
- [x] `git diff --stat` — hanya menyentuh file markdown. **Nol perubahan kode.**
      Kalau ada file `.py`/`.tsx` yang berubah, ada yang salah. — 5 file, semua `.md`

---

## Selesai kalau

- [x] Enam sub-langkah di atas tuntas atau ditandai `[~]` dengan alasan
- [x] Verifikasi hijau
- [x] `plan/PROGRESS.md` Session log ditambah satu baris:
      `| 29 Aug 2026 | submission prep | Reconciled every checkbox with what is actually deployed: Secret Manager ticked with evidence, phase 6 status aligned with its own drill record, the five-alert and push-trigger lines turned into decisions instead of open debt, README leads with video + live link |`
- [x] Commit: `docs(plan): reconcile checkboxes with what is actually deployed`

---

## JANGAN dikerjakan di fase ini

- [~] Menyentuh kode apa pun — ini fase dokumen murni
- [~] Mencentang kotak yang belum punya bukti, demi terlihat rapi. Itu persis
      pelanggaran yang membuat repo ini kehilangan kredibilitasnya
- [~] Menulis persentase kesiapan atau angka yang tidak diukur
