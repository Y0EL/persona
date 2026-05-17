GLINTS - UI FLOW LAMARAN KERJA
Dieksplorasi tanggal 16 Mei 2026

PACKAGE: com.glints.candidate
ACTIVITY: com.glints.candidate/.MainActivity
LAUNCH COMMAND: am start -n com.glints.candidate/.MainActivity

==============================
STEP 1 - HOME SCREEN
==============================

Tampilan: Daftar lowongan "Posisi Kecerdasan Buatan" yang sudah difilter sesuai preferensi akun.
Tab aktif: "For You"
Tab lain: Baru, Fresh Grad, Remote, Lokasi

Struktur card lowongan di home:
- Setiap card adalah android.view.View dengan clickable=true
- Seluruh data job ada di atribut content-desc, format:
  "[Posisi]\n[Gaji]\n[Perusahaan]\n[Lokasi]\n[Tipe kerja]\n[Pengalaman]\n[Pendidikan]\n..."
- Contoh: "CEO Office\nRp 6-9jt\nAiSensum (PT Aisensum)\nJakarta Selatan, DKI Jakarta\nHybrid\n1-3 thn\nS1"

CARA DETEKSI CARD: xpath('//*[@clickable="true" and @content-desc!=""]')
Filter: len(content-desc) > 40 dan ada karakter \n di dalamnya

PERHATIAN: Header "Posisi Kecerdasan Buatan..." DAN tab Lokasi juga clickable.
Jika ter-tap, popup "Preferensi Bidang Kerja" muncul (bottom sheet).
Cara dismiss popup: tap teks "X" atau press keyevent 4 (back)

Koordinat header yang harus DIHINDARI: y = 0 sampai y = 414 (dari UI dump)
Card job AMAN dimulai dari y = 438 ke bawah

==============================
STEP 2 - JOB DETAIL PAGE
==============================

Cara buka: tap card dari home feed
Tampilan: halaman detail berisi judul, gaji, lokasi, requirements, deskripsi pekerjaan

Elemen penting di detail:
- Judul posisi (besar, di atas)
- Gaji: format "Rp X-Yjt/bulan"
- Lokasi, tipe kerja, pengalaman dibutuhkan
- Link "Bisa lamar tanpa CV, lamar sekarang!" (biru, bisa di-tap juga)
- Tombol utama di bagian BAWAH: "CHAT UNTUK MELAMAR" (biru, full width)

Cara deteksi tombol apply:
  d(text="CHAT UNTUK MELAMAR")
  atau d(textContains="CHAT UNTUK MELAMAR")

Perlu scroll ke bawah dulu untuk memastikan tombol terlihat.
Tombol ada di sekitar y = 2300 dari total tinggi layar 2436.

==============================
STEP 3 - FORM PERTANYAAN HRD (4 langkah)
==============================

Setelah tap "CHAT UNTUK MELAMAR", muncul modal/overlay "Pertanyaan dari HRD".
Progress bar menunjukkan kemajuan X/4.
Semua jawaban sudah PRE-FILLED dari lamaran sebelumnya.
Cukup tap SELANJUTNYA untuk setiap step, lalu KIRIM di step terakhir.

-- STEP 1/4 --
Judul: "CV (Opsional)"
Isi: CV sudah ter-upload otomatis (5a304077...pdf, 1.49 MB)
Keterangan: "CV-mu akan otomatis dikirimkan untuk lamaran kerjamu selanjutnya"
Tombol: SELANJUTNYA (biru, bawah kanan)
Deteksi: d(text="SELANJUTNYA")

-- STEP 2/4 --
Pertanyaan: "Berapa tahun pengalaman yang kamu miliki dalam bidang ini?"
Pilihan: Tidak berpengalaman / Kurang dari 1 tahun / 1 tahun / 2 tahun / 3 tahun / 4 tahun / 5 tahun / Lebih dari 5 tahun
Pre-filled: "5 tahun" (biru dengan centang)
Jawaban yang tepat untuk Yoel: "3 tahun" namun pre-filled ke "5 tahun" sudah oke
Tombol: SELANJUTNYA

-- STEP 3/4 --
Pertanyaan: "Seberapa mahir kamu mengoperasikan software yang dibutuhkan dalam pekerjaan ini?"
Pilihan: Baru Belajar / Sedikit Mahir / Cukup Mahir / Mahir / Sangat Mahir
Pre-filled: "Sangat Mahir" (biru dengan centang)
Jawaban untuk Yoel: "Sangat Mahir" (sesuai dengan pengalaman)
Tombol: SELANJUTNYA

-- STEP 4/4 --
Pertanyaan: "Sebutkan bahasa asing yang kamu kuasai?"
Pilihan: Bahasa Indonesia / Bahasa Melayu / Inggris / Mandarin / Tamil / Jepang / Korea / Perancis / Jerman / Lainnya
Pre-filled: "Bahasa Indonesia" + "Inggris" (keduanya dipilih)
Jawaban untuk Yoel: Bahasa Indonesia + Inggris (sesuai CV, bisa tambah Mandarin)
Tombol: KIRIM (bukan SELANJUTNYA)
Deteksi tombol final: d(text="KIRIM")

==============================
STEP 4 - SUKSES
==============================

Setelah KIRIM, masuk ke halaman chat dengan recruiter.
Status: "Telah Melamar / Chat Dimulai" dengan centang hijau
CV sudah terkirim otomatis.
Recruiter mengirim pesan otomatis.

Cara kembali ke home: press back 2-3 kali hingga muncul home feed lagi.
Deteksi sukses: d(textContains="Telah Melamar") atau d(textContains="Chat Dimulai")

==============================
RINGKASAN OTOMATISASI GLINTS
==============================

1. Launch app via: am start -n com.glints.candidate/.MainActivity
2. Tunggu 4 detik
3. Dismiss popup jika ada (keyevent 4 atau d(text="X").click())
4. Ambil semua card dari home: xpath('//*[@clickable="true" and @content-desc!=""]')
5. Filter: len(desc)>40, ada \n, bukan header/nav (y>414), fuzzy match posisi, blacklist check, gaji check
6. Tap card
7. Cari tombol: d(textContains="CHAT UNTUK MELAMAR") -> klik
8. Loop sampai step selesai:
   - Jika ada d(text="SELANJUTNYA") -> klik, tunggu 1.5 detik
   - Jika ada d(text="KIRIM") -> klik, tunggu 2 detik -> selesai
   - Jika ada pilihan yang belum dipilih -> pilih opsi terbaik dari profil
9. Deteksi sukses: d(textContains="Telah Melamar")
10. Press back 2x -> kembali ke home
11. Scroll dan ulangi untuk card berikutnya

JENIS PERTANYAAN YANG MUNGKIN MUNCUL (selain 4 step di atas):
- "Berapa ekspektasi gaji kamu?" -> isi: 10000000
- "Apakah kamu bersedia bekerja di [lokasi]?" -> pilih: Ya
- "Apakah kamu memiliki pengalaman di [teknologi]?" -> pilih: Ya (jika ada di stack Yoel)
- "Tingkat pendidikan terakhir?" -> pilih: S1
- "Kapan kamu bisa mulai bekerja?" -> pilih: Segera / 2 minggu
