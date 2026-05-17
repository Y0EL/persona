---
name: project-jobapply-flow
description: Automation lamaran kerja Glints dan JobStreet untuk Yoel Andreas Manoppo - flow UI yang sudah diverifikasi manual
metadata: 
  node_type: memory
  type: project
  originSessionId: e5be0fb4-dc9e-44f4-bddf-0246648619e9
---

Proyek automation melamar kerja di Glints dan JobStreet via ADB + uiautomator2 di HP fisik Itel S686LN (serial: 13344254B7000215, Android 15).

**Why:** Yoel ingin melamar banyak posisi AI Engineer, Frontend, IT secara otomatis tanpa harus tap satu per satu.

**How to apply:** Selalu gunakan flow yang sudah diverifikasi manual ini sebagai acuan saat menulis atau memperbaiki script.

FLOW GLINTS (sudah diverifikasi):
1. Launch: am start -n com.glints.candidate/.MainActivity
2. Home feed sudah menampilkan job relevan (React Native, data di content-desc)
3. Job card: clickable View dengan content-desc berisi "Posisi\nGaji\nPerusahaan\nLokasi\n..."
4. Tap card -> detail page -> tombol "CHAT UNTUK MELAMAR" di bawah
5. 4 step pertanyaan, semua PRE-FILLED, cukup: SELANJUTNYA x3, lalu KIRIM
6. Sukses: halaman chat "Telah Melamar / Chat Dimulai"

FLOW JOBSTREET (sudah diverifikasi):
1. Launch: am start -n com.jobstreet.jobstreet/seek.base.deeplink.presentation.DeeplinkActivity
2. Home feed "Recommended" - job cards deteksi via clickable View besar (width>800, height>200)
3. Tap card -> detail -> tombol "Quick apply" (PINK, kanan bawah)
4. Step 1: WAJIB pilih Resume (tap center card) DAN Cover Letter (tap center card "Write a cover letter")
5. Step 2: Gaji pre-filled Rp 10 Jt, Continue
6. Step 3: Career history auto, Continue
7. Step 4: Scroll bawah, aktifkan "Show strong interest", tap "Submit application"
8. Sukses: halaman "Success - Nice work, Yoel Andreas!"

BLACKLIST PERUSAHAAN:
- PT Gemilang Satria Perkasa / PT. GSP (perusahaan Yoel saat ini)
- Zando Agency (perusahaan Yoel sebelumnya)
- PT ADIDAYA RISET INSTRUMEN INDONESIA
- Eka (terkait Zando)

PROFIL YOEL:
- File: C:\Users\Engineer02\Desktop\persona\profile\yoel_profile.json
- Pengalaman: 3 tahun (sejak 2022)
- Stack: LangGraph, Python, Vue 3, React, FastAPI, Docker
- Gaji ekspektasi: 10 juta (pre-filled di JobStreet)
- Bahasa: Indonesia, Inggris, Mandarin

FILE PENTING:
- C:\Users\Engineer02\Desktop\persona\steps\glints\flow.md - dokumentasi flow Glints
- C:\Users\Engineer02\Desktop\persona\steps\jobstreet\flow.md - dokumentasi flow JobStreet
- C:\Users\Engineer02\Desktop\persona\automation\ - script automation
- C:\Users\Engineer02\Desktop\persona\Lamaran\ - folder laporan harian