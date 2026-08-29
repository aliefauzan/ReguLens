# plan/upgrade — rencana eksekusi sampai submit

Enam fase, satu file per fase, masing-masing dijalankan lewat **satu prompt yang
hanya berubah di baris pertama**.

**Deadline:** 31 Agu 2026 17:00 PDT = **1 Sep 2026 07:00 WIB**
**Track:** Collaborative Partner — tidak berubah

Latar belakang penilaiannya ada di [`../submission/JUDGE-ASSESSMENT.md`](../submission/JUDGE-ASSESSMENT.md).

---

## Cara menjalankan

Buka [`PROMPT.md`](PROMPT.md), salin blok prompt-nya, **ganti baris pertama saja**.

```
Kerjakan plan/upgrade/S0-repo-consistency.md     ← baris ini satu-satunya yang diubah
```

---

## Peta fase

| Fase | File | Isi | Estimasi | Claude | Buang kalau mepet? |
|---|---|---|---|---|---|
| S0 | [S0-repo-consistency.md](S0-repo-consistency.md) | Selaraskan kotak centang dengan yang benar-benar ter-deploy | 1 jam | ✅ penuh | ❌ tidak |
| S1 | [S1-remediation-plan.md](S1-remediation-plan.md) | Fitur Rencana Perbaikan — endpoint baca-saja + halaman | 5–7 jam | ✅ penuh | ✅ ya |
| S2 | [S2-demo-stage-prep.md](S2-demo-stage-prep.md) | Reset state, ukur timing, siapkan tab Console | 1,5 jam | ⚠️ sebagian | ❌ tidak |
| S3 | [S3-video-assets.md](S3-video-assets.md) | Naskah, shot list, subtitle, deskripsi YouTube | 2 jam + 4 jam kamu | ⚠️ sebagian | ❌ **tidak pernah** |
| S4 | [S4-bonus-content.md](S4-bonus-content.md) | Artikel + post sosial — bonus +0.4 | 2 jam | ⚠️ sebagian | ✅ ya |
| S5 | [S5-submission-text.md](S5-submission-text.md) | Teks Devpost + checklist + verifikasi pra-submit | 1 jam | ⚠️ sebagian | ❌ tidak |

**Urutan:** S0 → S1 → S2 → S3 → S4 → S5
**Kalau waktu mepet:** S0 → S2 → S3 → S5

---

## Apa arti "⚠️ sebagian"

Claude menghasilkan **seluruh materinya**; kamu mengeksekusi langkah yang butuh
manusia. Tiap file fase punya bagian **"Bagian kamu"** yang menyebut persis apa.

| Fase | Yang Claude kerjakan | Yang kamu kerjakan |
|---|---|---|
| S2 | Reset stack, ukur latensi, tulis daftar URL Console | Buka tab, atur zoom, bersihkan layar |
| S3 | Naskah lengkap, shot list, `.srt`, deskripsi YouTube | Merekam, mengedit, mengunggah |
| S4 | Draf artikel + draf post sosial | Menerbitkan atas namamu |
| S5 | Teks submission, checklist, verifikasi HTTP | Mengisi & mengirim form Devpost |

Batasnya disengaja: menerbitkan tulisan dan mengirim form adalah tindakan
keluar atas nama akunmu. Claude menyiapkan sampai tinggal ditekan.

---

## Dampak skor

Skor sekarang: **gagal Stage One** — video wajib belum ada.

| Setelah | Perkiraan skor (skala 1–6) |
|---|---|
| S0 + S2 + S3 + S5 | **≈ 4.30** |
| + S4 (bonus +0.4) | **≈ 4.70** |
| + S1 | **≈ 4.96** |

---

## Aturan yang berlaku di semua fase

Diturunkan dari `CLAUDE.md` dan §Decisions taken di `plan/PROGRESS.md`.

- Kode deterministik memiliki setiap mutasi. Respons model tidak pernah masuk
  Firestore tanpa validator Pydantic dan guardrail.
- Kotak dicentang hanya kalau barangnya nyata dan terverifikasi — bukan
  "sudah ditulis", bukan "harusnya jalan". Yang sengaja dilewati ditandai `[~]`
  dengan alasannya.
- Klaim hanya yang terverifikasi. Tidak ada persentase kesiapan yang dikarang,
  tidak ada teks regulasi yang diarang, tidak ada bahasa "monitoring" untuk
  perilaku yang hanya jalan saat upload.
- Setiap fase memperbarui `plan/PROGRESS.md` di commit yang sama dengan
  perubahannya. Kotak yang tertinggal dari repo lebih buruk daripada tidak ada
  kotak sama sekali.
