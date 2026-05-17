JOBSTREET - UI FLOW LAMARAN KERJA
Dieksplorasi tanggal 17 Mei 2026

PACKAGE: com.jobstreet.jobstreet
ACTIVITY: com.jobstreet.jobstreet/seek.base.deeplink.presentation.DeeplinkActivity
LAUNCH COMMAND: am start -n com.jobstreet.jobstreet/seek.base.deeplink.presentation.DeeplinkActivity

==============================
STEP 1 - HOME SCREEN
==============================

Tampilan: "Good evening, Yoel Andreas" + search bar + Recommended jobs
Search bar: "Continue your job search" - clickable, koordinat approx (540, 420)
Tab: "All" dan "New to you" (badge angka = jumlah job baru)

Struktur card lowongan di home:
JobStreet memakai android.widget.TextView untuk setiap elemen (bukan content-desc)
Setiap card adalah android.view.View clickable dengan bounds lebar (x:0-1080) dan tinggi >200px
Di dalam card ada child TextView:
  - index 0: Posisi (judul pekerjaan)
  - index 1: Nama perusahaan
  - Gaji: TextView dengan teks "Rp7.000.000 - Rp10.000.000 per month"
  - Lokasi: TextView dengan teks lokasi

CARA DETEKSI CARD:
xpath('//*[@clickable="true" and @focusable="true"]')
Filter bounds: width > 800, height > 200, y1 > 400

PERHATIAN: Card pertama yang muncul adalah blacklist (PT ADIDAYA RISET INSTRUMEN INDONESIA)
WAJIB cek blacklist sebelum tap card apapun

==============================
STEP 2 - JOB DETAIL PAGE
==============================

Cara buka: tap card dari home feed
Tampilan: judul, perusahaan, lokasi, kategori, tipe, gaji

Elemen penting:
- Badge "Strong applicant" jika profil cocok
- Lokasi, tipe pekerjaan (Full time/Part time), gaji range
- Section "Skills and credentials from the job description" (bisa di-tap untuk lihat match)

Dua tombol di bagian BAWAH layar (y sekitar 2330):
  - "Save" (outline, kiri) - untuk bookmark
  - "Quick apply" (pink/magenta, kanan) - INI TOMBOL APPLY

Cara deteksi: d(text="Quick apply")
Koordinat kanan bawah: approx (800, 2330)

==============================
STEP 3 - QUICK APPLY FORM (4 langkah)
==============================

Setelah tap "Quick apply", muncul form multi-step.
Header: "Step X of 4" dengan sub-judul per step.

-- STEP 1/4: Choose documents --
Sub-judul: "Choose documents"
Tab: "Application" (aktif) | "Job details"

Section RESUME:
- Daftar file PDF tersimpan, masing-masing dalam card dengan radio button di kiri
- Default file: "profile(1).pdf" (paling baru, 6 menit lalu)
- WAJIB pilih resume dulu sebelum Continue
- Cara pilih: tap CENTER card (bukan hanya radio button)
  - Bounds resume card PERTAMA: [48,758][1032,1102] -> tap (540, 930)
  - Jika resume lain: geser ke card yang sesuai

Section COVER LETTER (di bawah resume, perlu scroll):
- Ada opsi "Write a cover letter" dengan template pre-filled:
  "Dear Hiring Team, I am writing to express my interest in [posisi]..."
  Template sudah mengandung ringkasan keahlian Yoel
- WAJIB pilih cover letter juga sebelum Continue
- Cara pilih: tap center card cover letter
  - Bounds cover letter card: [48,1729][1032,2117] -> tap (540, 1923)
  Catatan: koordinat ini RELATIF ke posisi scroll, perlu dump UI dulu
  Alternatif: d(textContains="Write a cover letter") lalu tap parent clickable-nya

Tombol Continue:
- Bounds: [48,2196][1032,2340] -> tap (540, 2268)
- Deteksi: d(text="Continue")

ERROR JIKA BELUM PILIH:
- "Resumé selection required" -> pilih resume dulu, OK, lalu Continue
- "Cover letter selection required" -> scroll ke bawah, pilih "Write a cover letter", lalu Continue

-- STEP 2/4: Answer employer questions --
Sub-judul: "Answer employer questions"
Pertanyaan yang muncul (bervariasi per lowongan):
- "Berapa gaji bulanan yang kamu inginkan?" -> pre-filled: "Rp 10 Jt"
- Pertanyaan lain mungkin muncul tergantung job
Tombol: Back | Continue
Deteksi Continue: d(text="Continue")

-- STEP 3/4: Update Jobstreet Profile --
Sub-judul: "Update Jobstreet Profile"
Menampilkan career history dari profile JobStreet (sudah terisi otomatis):
- Software Engineer - PT Decision Tree Indonesia - Des 2025
- Full Stack Developer - ReUse - Nov 2024
- AI Specialist - ZANDO Agency - Jan 2024
- dan lainnya (11 roles total)
Tidak perlu input apapun, langsung Continue
Tombol: Back | Continue

-- STEP 4/4: Review and submit --
Sub-judul: "Review and submit"
Halaman review lengkap berisi:
- Profil Yoel (nama, email, telepon, lokasi)
- Documents included: Resume + Cover letter
- Employer questions: "You answered X of X"
- Jobstreet Profile: Career history, Education, Licences, Skills (22 skills)
- Section "Make a strong impression" dengan toggle "Show strong interest"

TOGGLE "Show strong interest": AKTIFKAN selalu
- Meningkatkan visibilitas lamaran
- Bounds toggle area: sekitar y=1840 saat halaman sudah di-scroll ke bawah

Tombol FINAL: "Submit application" (PINK/MAGENTA, full width, paling bawah)
- Perlu scroll ke paling bawah dulu
- Deteksi: d(text="Submit application")
- Koordinat approx: (540, 2310) saat sudah di-scroll ke bawah

==============================
STEP 4 - SUKSES
==============================

Halaman "Success" muncul:
- Header: "Success"
- Teks: "Nice work, Yoel Andreas!"
- Sub-teks: "Your application has been sent to [Nama Perusahaan]."
- Rekomendasi job lain muncul di bawah ("You might also like...")

Cara kembali ke home: tap X di pojok kiri atas
Atau press back 1-2 kali

Deteksi sukses: d(text="Success") atau d(textContains="application has been sent")

==============================
RINGKASAN OTOMATISASI JOBSTREET
==============================

1. Launch app via am start
2. Tunggu 4 detik, dismiss popup
3. Ambil job cards dari home feed:
   xpath('//*[@clickable="true" and @focusable="true"]')
   Filter: width>800, height>200, y>400
4. Untuk setiap card:
   a. Extract posisi dan perusahaan dari child TextView
   b. Cek blacklist, gaji, fuzzy match posisi
   c. Tap center card
5. Di detail page: tap d(text="Quick apply")
6. STEP 1 - Resume:
   a. Scroll ke atas (sudah di atas)
   b. Cari card resume dengan Default badge atau paling baru
   c. Tap center card resume untuk select
   d. Scroll ke bawah cari "Write a cover letter"
   e. Tap center card cover letter
   f. Tap Continue: d(text="Continue")
   g. Jika ada error dialog: tap OK, cek ulang pilihan
7. STEP 2: Jawab pertanyaan gaji dan lainnya berdasarkan profil
   - Gaji sudah pre-filled, tap Continue
8. STEP 3: Career history, tap Continue
9. STEP 4: Scroll ke bawah, aktifkan "Show strong interest", tap "Submit application"
10. Deteksi sukses: d(textContains="application has been sent")
11. Tap X atau back, kembali ke home
12. Ulangi untuk card berikutnya

CATATAN PENTING:
- UI JobStreet DARK MODE pada hp Yoel
- Cover letter sudah terisi pre-written yang personal dan relevan - tidak perlu edit
- Gaji pre-filled Rp 10 Jt sesuai ekspektasi
- Career history terisi otomatis dari profile
- "Show strong interest" HARUS diaktifkan tiap kali

PERBEDAAN UTAMA GLINTS vs JOBSTREET:
- Glints: 1 tombol "CHAT UNTUK MELAMAR", 4 step pilihan, lalu KIRIM
- JobStreet: "Quick apply", Step 1 pilih resume+cover letter, Step 2-3 auto, Step 4 submit
- JobStreet butuh scroll lebih banyak dan ada 2 dokumen yang harus dipilih manual
