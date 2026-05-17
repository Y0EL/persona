# Script Reel Instagram

Tema: Bot auto lamar kerja di Glints dan JobStreet dari laptop pake ADB
Durasi target: 2 sampai 3 menit (bisa di-cut jadi 60 detik versi pendek)
Gaya: casual gaul, sedikit flexing, edukatif

Tanpa em dash, en dash, semicolon. Pakai comma + period + colon.

---

## Visual Setup Sebelum Record

1. HP fisik di samping laptop, kabel USB nyambung
2. Layar HP keliatan jelas (mode landscape atau split)
3. Terminal laptop fullscreen jalanin `python visualizer.py` atau `python main.py jobstreet`
4. File `17052026.md` kebuka di VS Code di sebelah terminal
5. Pakai tripod / phone holder biar stable
6. Lighting cukup. Gua saranin sore atau pakai ring light

---

## VERSI PANJANG (2 sampai 3 menit)

### HOOK (0 sampai 7 detik)

VISUAL:
- Close up layar HP yang auto-scroll sendiri, tap sendiri, ngisi form sendiri
- Kamera zoom ke HP

VOICEOVER / CAPTION:
> Gua lamar 97 kerjaan dalam 1 hari, tanpa nyentuh HP sekalipun.

ON SCREEN TEXT (besar):
**97 LAMARAN. 0 SENTUHAN.**

### TRANSISI (7 sampai 12 detik)

VISUAL: cut cepat ke laptop, terminal lagi spit log warna warni

VOICEOVER:
> Caranya. Gua bikin bot Android pake Python sama ADB. Dia yang scroll, tap, isi form, sampai submit. Gua tinggal nonton.

### ISI 1 LIVE DEMO (12 sampai 60 detik)

VISUAL: split screen, kiri layar HP auto jalan, kanan terminal log

VOICEOVER:
> Sekarang gua run live. Yang kiri HP gua, yang kanan terminal di laptop. Bot ini target Glints sama JobStreet, posisi yang nyambung sama profile gua doang. AI Engineer, Frontend, DevOps, IT Support.

NARASI sambil layar jalan:
> Liat nih, dia buka feed, scan kartu lowongan, baca title sama gaji, lewatin yang gak match, terus tap apply. Step 1 dokumen auto, step 2 jawab pertanyaan HRD, step 3 update profil, step 4 KIRIM. Selesai. Lanjut ke lowongan berikutnya.

### ISI 2 OTAKNYA (60 sampai 90 detik)

VISUAL: switch ke VS Code, scroll cepat di file `jobstreet.py` dan `glints.py`

VOICEOVER:
> Dia gak cuma robotic. Punya filter:
> Gaji minimum 8 juta. Skip blacklist. Lokasi harus Jabodetabek. Fuzzy match 60 lebih keyword.
> Pertanyaan teks bebas dijawab pakai OpenRouter, gratis. Salary expectation auto fill 10 juta. Yes No question default Yes.
> Kalau form gagal di tengah, dia gak nge mark applied. Besok dicoba lagi.

### ISI 3 REPORT (90 sampai 120 detik)

VISUAL: buka file `Lamaran/17052026.md`, scroll dari atas. Tunjukin table per lamaran.

VOICEOVER:
> Setiap submit sukses, auto tulis ke file markdown. Hari ini 97 entry. Format rapi pake table, deskripsi pekerjaan, sama benefit perusahaan.

ZOOM ke total counter di atas.

### ISI 4 VISUALIZER COSMETIC (120 sampai 150 detik)

VISUAL: terminal run `python visualizer.py`. Tunjukin progress bar gerak, log warna warni keluar urut.

VOICEOVER:
> Buat replay seharian, gua bikin visualizer. Pakai loguru, progress bar, log warna warni. Bisa pamerin ke temen kayak lagi hacking.

### PENUTUP (150 sampai 180 detik)

VISUAL: close up muka lo / overlay text

VOICEOVER:
> 97 lamaran dalam sehari. Yang penting tetap follow up manual yang paling cocok. Bot bukan ganti effort, tapi ngebantu yang repetitif.
> Source code ada di github gua. Drop comment kalau mau gua bikinin part 2 jelasin arsitekturnya.

ON SCREEN TEXT:
- **FOLLOW** for part 2
- **COMMENT** if mau source code
- **SAVE** buat referensi nanti

---

## VERSI PENDEK 60 DETIK

### HOOK 0 sampai 5

VISUAL: HP auto-scroll + tap sendiri.

CAPTION:
**Gua lamar 97 kerja tanpa nyentuh HP.**

### ISI 5 sampai 50

VISUAL: split. Kiri HP jalan, kanan terminal log.

VOICEOVER cepat:
> Bot Python plus ADB. Auto scan Glints sama JobStreet. Filter gaji 8 juta minimum, blacklist, lokasi Jabodetabek doang. Form 4 step auto isi. Pertanyaan teks dijawab pake AI. Tiap submit dicatat di markdown rapi.

CUT cepat:
- Detik 5 sampai 15: HP scroll feed
- Detik 15 sampai 25: HP isi form step 2
- Detik 25 sampai 35: HP tap KIRIM, success screen
- Detik 35 sampai 45: VS Code report file 97 entry
- Detik 45 sampai 50: terminal visualizer progress bar

### PENUTUP 50 sampai 60

VOICEOVER:
> 97 dalam sehari. Source code di link bio. Follow buat part 2.

CAPTION akhir:
**Save buat job hunt season selanjutnya.**

---

## CAPTION INSTAGRAM POST

```
Bot auto lamar kerja di Android. 97 lamaran dalam 1 hari.
Glints sama JobStreet, full auto pake ADB plus Python plus OpenRouter.

Stack:
. Python 3.11
. uiautomator2
. loguru buat visualizer
. OpenRouter free LLMs buat jawab pertanyaan HRD
. Markdown report harian rapi

Yang dia bisa:
. Scan feed sama search keyword
. Filter gaji minimum, blacklist, lokasi
. Isi form 4 step end to end
. Jawab dropdown sama free text via AI
. Auto submit
. Detect lowongan luar negeri, auto skip

Yang dia GA bisa:
. Ganti follow up manual
. Ngenalin recruiter
. Bikin lo lulus interview

Source code di github bio. Save buat next job hunt.

#jobhunt #devlife #android #python #automation
```

---

## TIPS REKAMAN

- Pakai screen recorder bawaan HP buat capture HP. Tapi lebih bagus pake DroidCam atau scrcpy di laptop terus capture lewat OBS biar synced sama terminal.
- Terminal pake font Cascadia Code atau Fira Code biar enak diliat. Zoom font besar minimal 16pt.
- Cursor jangan keliatan diem. Move sedikit biar engaging.
- Background music: lo fi atau synthwave low volume biar gak overpower voiceover.
- Cut transisi 0.2 sampai 0.4 detik. Jangan terlalu lama.
- Akhiri dengan freeze frame 1 detik di angka 97 atau di tombol follow.

---

## ALTERNATIF HOOK

Pilih salah satu kalau gak suka yang utama:

1. "Auto lamar kerja sambil tidur. Pagi bangun 97 lamaran udah masuk."
2. "Recruiter pasti bingung. 97 lamaran masuk dari satu kandidat dalam sehari."
3. "Gua bayar Rp 0 buat developer ini. Karena developer-nya gua sendiri."
4. "Setup ADB. Run script. Tinggal nonton HP gerak sendiri."
5. "POV: bot lo ngeapply ke 97 lowongan, lo cuma scroll TikTok."

---

## SHOT LIST CHECKLIST

[] Close up HP lagi auto scroll
[] Close up HP lagi tap CHAT UNTUK MELAMAR
[] Close up HP lagi isi form Step 2
[] Close up HP lagi tap KIRIM
[] Close up screen Success Nice work
[] Terminal log scrolling
[] VS Code file 17052026.md zoom ke 97
[] Terminal visualizer running progress bar
[] Muka lo ngomong outro

Semua siap. Sini siapin tripod, mulai rekam.
