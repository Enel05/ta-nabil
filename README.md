# Real-Time Smart User Interview Assistant

## 📝 Deskripsi Proyek
Proyek ini adalah sebuah sistem cerdas untuk membantu proses wawancara pengguna (User Interview) secara real-time. Sistem ini bertugas mendengarkan percakapan, membedakan siapa yang berbicara (interviewer vs narasumber), mentranskripsi audio, lalu menganalisis hasilnya menggunakan AI untuk menghasilkan wawasan produk (product insights), persona pengguna, analisis masalah, hingga rekomendasi UX/UI.

Proyek ini didasarkan pada pedoman prompt wawancara kualitatif yang telah diterjemahkan dan disimpan dalam file `interview_assistant_prompt_id.md`.

## 🛠️ Tech Stack & Teknologi Utama
- **Bahasa Pemrograman:** Python
- **LLM / AI Analysis:** OpenAI API (Menggunakan model terbaru seperti GPT-4o) untuk memproses teks, melakukan analisis *Jobs-to-be-Done*, dan memberikan rekomendasi produk.
- **Diarization & Voice Recognition:** Pyannote AI (Hugging Face) untuk membedakan suara *interviewer* (pewawancara) dan *interviewee* (narasumber).

## ✨ Fitur Utama
1. **Speaker Diarization:** Memisahkan dan mengenali suara dari pewawancara dan narasumber menggunakan Pyannote AI.
2. **Speech-to-Text:** Mengubah suara percakapan menjadi teks transkrip (misal menggunakan Whisper dari OpenAI).
3. **Analisis Konteks & Wawasan:** AI akan menganalisis hasil percakapan berdasarkan panduan di `interview_assistant_prompt_id.md`.
4. **Pembuatan Laporan (Output):** 
   - Persona Pengguna
   - *Pain Points* dan Motivasi
   - Rekomendasi Fitur Produk
   - Rekomendasi Pola UX/UI

## 📂 Struktur & Referensi File
- `interview_assistant_prompt_id.md`: Berisi *core prompt* atau panduan instruksi sistem AI untuk menjalankan perannya sebagai asisten riset pengguna.
- `.env.local`: Tempat menyimpan konfigurasi environment variables secara aman.

## 🔐 Kredensial & Konfigurasi (Environment Variables)
Rahasia dan API Keys disimpan secara lokal (di `.env.local`) dan TIDAK BOLEH dipublikasikan. API yang dikonfigurasi meliputi:
- `OPENAI_API_KEY`: Untuk akses ke model OpenAI.
- `PYANNOTE_API_KEY`: (Hugging Face / Pyannote API Key) Untuk fitur diarization suara.

---
*Catatan: Dokumen ini dibuat sebagai pengingat rancangan dasar (blueprint) proyek.*
