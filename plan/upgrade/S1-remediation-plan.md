# S1 — Rencana Perbaikan (fitur P3 Opsi A)

**Status:** `NOT STARTED` · **Estimasi:** 5–7 jam · **Claude:** ✅ penuh
**Kapan:** setelah S0 · **Boleh dibuang:** ✅ ya, kalau jam 14:00 tanggal 30 belum jalan

---

## Kenapa fase ini ada

Kritik juri terbesar, di kriteria berbobot 40%:

> *Agent berhenti di notifikasi. Ia bilang "produkmu melanggar di Jerman", lalu
> selesai. "High-value agent action" masih berplafon di alert.*

Fase ini mengubah agent dari **pemberi tahu** menjadi **penyiap keputusan**.

Dan karena track-nya **Collaborative Partner**, bentuknya harus tepat: agent
menyiapkan pekerjaan sampai **tinggal disetujui manusia**, bukan bertindak
sendiri. Draf, bukan aksi. Itu justru definisi track ini, sekaligus menjawab
kritik 40%.

**Risiko mendekati nol:** seluruhnya baca-saja. Tidak menyentuh pipeline, tidak
menyentuh guardrail, tidak menambah satu pun mutasi baru.

---

## Data yang sudah ada — tidak perlu menghitung ulang apa pun

Koleksi `requirements` di Firestore sudah menyimpan semua yang dibutuhkan
(lihat `api/app/core/impact.py:60-80` dan `:140-155`):

| Field | Isi |
|---|---|
| `product_id`, `market_id`, `clause_id` | penghubung |
| `substance` | nama ternormalisasi |
| `evaluation` | `pass` / `fail` / `needs_review` |
| `limit_value`, `limit_unit` | batas menurut klausa |
| `product_value`, `product_unit` | jumlah menurut produk |
| `comparable_value`, `comparable_limit`, `comparable_unit` | **kedua sisi dalam satu satuan** — ini yang dipakai |
| `severity`, `reason` | untuk pengurutan dan kalimat |

Endpoint pembanding yang sudah ada dan polanya diikuti:
`GET /products/{product_id}/compliance` di `api/app/main.py:256`.

Catatan penting: **tidak ada APIRouter di repo ini.** Semua endpoint hidup
sebagai `@app.get` / `@app.post` langsung di `api/app/main.py`. Ikuti pola itu,
jangan memperkenalkan struktur router baru dua hari sebelum deadline.

---

## Prasyarat

- [ ] S0 selesai
- [ ] `bash scripts/verify_local.sh` hijau dari stack yang diwipe (baseline sehat)

---

## Langkah

### S1.1 · Logika inti — `api/app/core/remediation.py` (file baru)

Fungsi murni, importable, dapat diuji tanpa FastAPI dan tanpa ADK — sesuai
standing rule repo.

- [ ] `def build_remediation(product_id: str) -> dict`
- [ ] Baca `requirements` untuk produk itu (pola query sama dengan
      `get_product_compliance`), plus produk dan pasar-pasarnya
- [ ] Hitung, **tanpa satu pun panggilan model** — ini aritmatika, sama seperti
      keputusan Impact tidak punya agent:

  1. **Kelompokkan per substansi.** Satu substansi bisa punya banyak batas dari
     banyak pasar.
  2. **Angka target lintas pasar** = `min(comparable_limit)` di antara pasar
     yang benar-benar dituju produk ini, untuk substansi itu.
     - Kalau ada pasar yang **belum punya aturan sama sekali** untuk substansi
       itu, target tetap dihitung dari yang ada **tetapi** hasilnya menandai
       `coverage: "partial"` dan menyebut pasar mana yang belum tercakup.
       Diam adalah kegagalan mode di sini — pasar tanpa aturan tidak boleh
       terbaca seperti pasar yang lulus.
     - Kalau tidak ada satu pun batas yang bisa dibandingkan, `target` = `None`
       dengan alasan tertulis. **Jangan mengarang angka.**
  3. **Pasar paling ketat** = pemilik `comparable_limit` terkecil. Simpan
     `market_id`-nya, bukan hanya angkanya.
  4. **Kutipan** — untuk tiap batas: `clause_id`, teks klausa verbatim,
     `document_id`, dan tanggal berlaku. Tautan passage dibentuk sebagai
     `/documents/{document_id}?cite={clause_id}` (mekanisme ini sudah ada sejak
     pekerjaan sitasi 29 Agu).
  5. **Yang tidak dicek** — bahan produk yang tidak menghasilkan requirement
     apa pun. Sebutkan alasannya dengan memakai `core/substances.py` yang sudah
     ada: nama tidak dikenal / ini makanan bukan zat yang dibatasi / jumlah
     tidak diisi / satuan tidak bisa dikonversi. **Wajib ada.** Daftar bahan
     yang diam-diam hilang membaca seperti lulus.

- [ ] Kembalikan struktur yang stabil, kira-kira:
      ```python
      {
        "product_id": ..., "product_name": ...,
        "generated_for_markets": [...],
        "targets": [
          {
            "substance": ..., "target_value": ..., "target_unit": ...,
            "coverage": "full" | "partial",
            "markets_without_rules": [...],
            "strictest_market_id": ...,
            "current_value": ..., "current_unit": ...,
            "verdict_today": "fail" | "pass" | "needs_review",
            "limits": [ {market_id, limit, unit, clause_id, document_id,
                         effective_date, quote, is_strictest}, ... ],
          }, ...
        ],
        "not_checked": [ {ingredient, reason_code, reason_text}, ... ],
        "trace_id": ...,
      }
      ```

### S1.2 · Model Pydantic — `api/app/models.py`

- [ ] Tambahkan model respons untuk struktur di atas
- [ ] **Tidak ada field opsional yang diam-diam kosong.** Kalau target tak bisa
      dihitung, ada field alasan yang terisi. Ini standing rule repo: klaim hanya
      yang terverifikasi

### S1.3 · Endpoint — `api/app/main.py`

- [ ] `@app.get("/products/{product_id}/remediation")`, taruh setelah
      `get_product_compliance` (sekitar baris 295) supaya endpoint produk
      berkelompok
- [ ] `404` kalau produk tidak ada — samakan dengan `get_product_compliance`
- [ ] `200` dengan `targets: []` kalau tidak ada pelanggaran, **bukan 404**.
      "Tidak ada yang perlu diperbaiki" adalah jawaban yang sah
- [ ] Sertakan `trace_id` seperti endpoint lain
- [ ] **Baca-saja.** Tidak ada tulis Firestore, tidak ada publish Pub/Sub, tidak
      ada `graph_event`

### S1.4 · Test — `api/tests/test_remediation.py` (file baru)

- [ ] Dua pasar, dua batas berbeda → target = yang paling ketat, dan
      `strictest_market_id` menunjuk pasar yang benar
- [ ] Satu pasar punya aturan, satu belum → `coverage == "partial"` dan pasar
      yang belum tercakup **disebut namanya**
- [ ] Produk tanpa pelanggaran → `targets == []`, status 200
- [ ] Bahan tanpa jumlah → muncul di `not_checked` dengan alasan yang benar
- [ ] Bahan berupa makanan (mis. `ginger`) → muncul di `not_checked` sebagai
      makanan, **bukan** sebagai lulus
- [ ] Produk tidak ada → 404
- [ ] Ikuti gaya test yang sudah ada, contoh terdekat:
      `api/tests/test_requirement_change.py`

### S1.5 · Halaman web — `web/app/products/[id]/remediation/page.tsx`

- [ ] Tambahkan fungsi fetch di `web/lib/api.ts` mengikuti pola yang ada
- [ ] Urutan isi halaman, dari atas:
      1. **Satu kalimat besar** yang langsung menjawab:
         *"Turunkan sodium benzoate ke 150 mg per kg atau kurang, dan produk ini
         diterima di Jerman dan Indonesia."*
         Kalau `coverage == "partial"`, kalimatnya harus menyebut batasnya:
         *"…diterima di Jerman dan Indonesia. Kami belum punya aturan untuk Jepang,
         jadi Jepang tidak termasuk dalam angka ini."*
      2. **Tabel per pasar**: batas · sumber · tanggal berlaku · penanda paling ketat
      3. **Kutipan verbatim** tiap klausa, masing-masing tertaut ke passage-nya
      4. **Blok "Yang tidak kami cek"** — jujur, jangan disembunyikan di balik disclosure
      5. Tombol **Print / Save as PDF** → `window.print()` + aturan `@media print`
         di `globals.css`. Cukup. **Jangan** menambah pustaka generator PDF
- [ ] Pakai `_ui/status.tsx` untuk menerjemahkan kata mesin — jangan menulis
      terjemahan baru di halaman ini
- [ ] Pakai `_ui/Provenance.tsx` untuk blok "dari mana ini" — sudah ada
- [ ] `data-testid` di tiap blok utama
- [ ] Bahasa: sama dengan halaman lain (Inggris, plain language, non-teknis)

### S1.6 · Pintu masuk

- [ ] Tombol **"Prepare a fix plan"** di kartu alert pada
      `web/app/products/[id]/page.tsx`
- [ ] Tombol yang sama di banner "What changed on its own"
      (`web/app/AlertsBanner.tsx`)
- [ ] Tombol hanya muncul kalau ada requirement yang `fail`. Halaman kosong
      yang bisa diklik membaca seperti tombol rusak

### S1.7 · Pembingkaian Collaborative Partner — **jangan dilewat**

Ini yang membuat fitur ini bernilai di track yang kamu daftarkan.

- [ ] Di bagian atas halaman, satu kalimat sejenis:
      **"This is a draft for you to check, not an action we took."**
- [ ] **JANGAN** kirim email
- [ ] **JANGAN** mengubah state produk, requirement, atau klausa apa pun
- [ ] **JANGAN** ada aksi otonom keluar sistem
      Aksi keluar-sistem tidak bernilai lebih tinggi di track ini dan menambah
      permukaan risiko dua hari sebelum deadline

---

## Verifikasi

- [ ] `cd api && pytest -q` — hijau, termasuk test baru
- [ ] `cd api && ruff check .` — bersih
- [ ] `cd web && npx tsc --noEmit` — bersih
- [ ] `cd web && npm run build` — hijau
- [ ] `bash scripts/verify_local.sh` — **masih** hijau dari stack yang diwipe.
      Kalau merah, fitur baca-saja ini merusak sesuatu dan harus dibatalkan
- [ ] Dicek di browser untuk produk demo: light dan dark, lebar HP dan desktop
- [ ] Deploy ke Cloud Run dan **dibuka di URL live**. Video merekam yang live,
      bukan localhost

---

## Selesai kalau

- [ ] Verifikasi di atas hijau seluruhnya
- [ ] Halaman live menampilkan angka target yang benar untuk produk demo
      (`≤150 mg/kg`) dengan kedua klausa terkutip dan tertaut
- [ ] `plan/PROGRESS.md`: Session log ditambah satu baris, dan kotak yang
      relevan di `plan/phases/phase-7-demo-hardening.md` dicentang
- [ ] Commit: `feat: draft a remediation plan the user can approve`

---

## JANGAN dikerjakan di fase ini

- [~] Panggilan model apa pun. Menentukan batas paling ketat adalah membandingkan
      angka. Sama alasannya dengan Impact yang sengaja tidak punya agent
- [~] Mutasi Firestore, publish Pub/Sub, atau `graph_event` baru. Fitur ini
      baca-saja, dan justru itu yang membuatnya aman dikerjakan sekarang
- [~] Generator PDF sebagai dependensi baru. `window.print()` sudah cukup
- [~] Struktur APIRouter baru. Repo ini menaruh endpoint di `main.py`; ikuti
- [~] Mengirim email atau notifikasi keluar. Lihat S1.7
