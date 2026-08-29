# Prompt Template — jalankan satu fase upgrade

Salin **seluruh blok di bawah** ke Claude Code. **Hanya baris pertama yang diubah.**

---

```
Kerjakan plan/upgrade/S0-repo-consistency.md

Aturan menjalankan fase ini:

1. Baca CLAUDE.md dan plan/PROGRESS.md lebih dulu, sesuai working agreement repo ini.
2. Baca file fase di baris pertama secara utuh sebelum menyentuh apa pun.
3. Kerjakan HANYA yang ada di file fase itu. Kalau menemukan pekerjaan milik fase
   lain, catat di file fase tersebut, jangan dikerjakan sekarang.
4. Hormati bagian "JANGAN dikerjakan" di file fase. Itu keputusan yang sudah
   diambil, bukan kelalaian.
5. Setiap langkah punya kotak centang. Centang di file fase begitu sesuatu benar
   nyata dan terverifikasi — bukan "sudah ditulis", bukan "harusnya jalan".
   Yang sengaja dilewati ditandai [~] beserta alasannya.
6. Jalankan bagian "Verifikasi" di file fase sampai hijau sebelum mengaku selesai.
   Kalau ada yang merah, laporkan outputnya apa adanya, jangan disamarkan.
7. Setelah selesai, update plan/PROGRESS.md: satu baris Session log dan kotak
   yang relevan di plan/phases/. Ini bagian dari pekerjaan, bukan opsional.
8. Commit dengan pesan yang disebut di file fase. Jangan push kecuali saya minta.
9. Laporkan di akhir: apa yang benar-benar landing, apa yang gagal, dan apa yang
   masih butuh saya kerjakan manual.

Konteks yang tidak boleh dilanggar:
- Deadline 31 Agu 2026 17:00 PDT = 1 Sep 2026 07:00 WIB. Waktu adalah kendala utama.
- Track hackathon: Collaborative Partner. Tidak berubah.
- Kode deterministik memiliki setiap mutasi. Respons model tidak pernah masuk
  Firestore tanpa validator Pydantic dan guardrail.
- Klaim hanya yang terverifikasi. Tidak ada persentase kesiapan yang dikarang.
```

---

## Cara pakai

Ganti baris pertama dengan salah satu dari ini:

| Ganti baris pertama jadi | Fase | Estimasi | Claude bisa? |
|---|---|---|---|
| `Kerjakan plan/upgrade/S0-repo-consistency.md` | S0 · Konsistensi repo | 1 jam | ✅ penuh |
| `Kerjakan plan/upgrade/S1-remediation-plan.md` | S1 · Fitur Rencana Perbaikan | 5–7 jam | ✅ penuh |
| `Kerjakan plan/upgrade/S2-demo-stage-prep.md` | S2 · Siapkan panggung demo | 1,5 jam | ⚠️ sebagian |
| `Kerjakan plan/upgrade/S3-video-assets.md` | S3 · Naskah & aset video | 2 jam | ⚠️ sebagian |
| `Kerjakan plan/upgrade/S4-bonus-content.md` | S4 · Artikel + post sosial | 2 jam | ⚠️ sebagian |
| `Kerjakan plan/upgrade/S5-submission-text.md` | S5 · Teks submission Devpost | 1 jam | ⚠️ sebagian |

**Urutan yang disarankan:** S0 → S1 → S2 → S3 → S4 → S5.
Kalau waktu mepet: S0 → S2 → S3 → S5 (S1 dan S4 boleh dibuang).

⚠️ *sebagian* = Claude menghasilkan seluruh materinya; kamu yang mengeksekusi
langkah manusia (merekam layar, menerbitkan tulisan, mengisi form). Tiap file
fase punya bagian **"Bagian kamu"** yang menyebut persis apa itu.
