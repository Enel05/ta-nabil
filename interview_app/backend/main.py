import os
import json
import base64
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncOpenAI
from dotenv import load_dotenv
import aiofiles

# Memuat environment variable (OPENAI_API_KEY, PYANNOTE_API_KEY)
load_dotenv(dotenv_path="../../.env.local")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

import os
os.environ["HF_TOKEN"] = os.getenv("PYANNOTE_API_KEY")

from diart import SpeakerDiarization, SpeakerDiarizationConfig
import torch
import datetime
import shutil

from pyannote.audio import Model
from scipy.spatial.distance import cosine

print("Menginisialisasi Sistem Registrasi Suara (Voice Enrollment)...")
try:
    original_torch_load = torch.load
    def custom_torch_load(*args, **kwargs):
        kwargs['weights_only'] = False
        return original_torch_load(*args, **kwargs)
    torch.load = custom_torch_load
        
    embedding_model = Model.from_pretrained("pyannote/embedding")
    embedding_model.eval()
    if embedding_model is not None:
        print("Sistem Registrasi Suara berhasil dimuat!")
    else:
        print("Model gagal dimuat.")
except Exception as e:
    print(f"Gagal memuat sistem registrasi suara: {e}")
    embedding_model = None

# Global State (Simulasi untuk menyimpan persona sementara)
current_persona = {
    "demographics": {"name": "Belum diketahui", "age": "Belum diketahui", "occupation": "Belum diketahui", "location": "Belum diketahui"},
    "psychographics": {"personality": "Belum diketahui", "interests": []},
    "behaviors": {"usage_patterns": "Belum diketahui", "brand_loyalty": "Belum diketahui"},
    "goals": [],
    "motivations": [],
    "needs": [],
    "pain_points": [],
    "metrics": {
        "Tech_Savviness": 5,
        "Price_Sensitivity": 5,
        "Brand_Loyalty": 5,
        "Impatience": 5,
        "Analytical_Thinking": 5
    }
}

full_transcript = []


async def analyze_with_openai(text: str, speaker: str, app_context: str = ""):
    """
    Menggunakan OpenAI untuk menganalisis ucapan terbaru,
    mengekstrak info persona, dan merekomendasikan pertanyaan lanjutan (probing).
    """
    # Membaca prompt instruksi kualitatif
    try:
        async with aiofiles.open("../interview_assistant_prompt_id.md", mode='r', encoding='utf-8') as f:
            system_prompt = await f.read()
    except FileNotFoundError:
        system_prompt = "Kamu adalah Asisten Wawancara Pengguna cerdas."

    # Prompt khusus untuk realtime update
    prompt = f"""
    Konteks Aplikasi / Proyek:
    {app_context if app_context else "Tidak ditentukan"}

    Konteks percakapan sejauh ini (Transkrip):
    {json.dumps(full_transcript)}
    
    Ucapan terbaru:
    [{speaker}]: "{text}"
    
    87. Tugas Anda:
    1. Ekstrak data Persona selengkap mungkin: Demographics (Nama, Umur, Pekerjaan, Lokasi), Psychographics (Kepribadian, Ketertarikan), Behaviors (Pola penggunaan), Goals, Motivations, Needs, dan Pain Points.
    2. Berikan skor (1-10) untuk "metrics" berdasarkan nada bicara dan sifat yang tersirat dari narasumber (misal: jika gaptek, Tech_Savviness rendah).
    3. Berikan maksimal 3 rekomendasi pertanyaan lanjutan (Probing Questions) yang PENTING.
    
    Jawab HANYA dalam format JSON:
    {{
        "probing_questions": [
            {{"question": "pertanyaan 1?", "reason": "alasan 1"}}
        ],
        "extracted_persona": {{
            "demographics": {{"name": "...", "age": "...", "occupation": "...", "location": "..."}},
            "psychographics": {{"personality": "...", "interests": ["..."]}},
            "behaviors": {{"usage_patterns": "...", "brand_loyalty": "..."}},
            "goals": ["goal baru jika ada"],
            "motivations": ["motivasi baru jika ada"],
            "needs": ["kebutuhan baru jika ada"],
            "pain_points": ["pain point baru jika ada"],
            "metrics": {{
                "Tech_Savviness": 8,
                "Price_Sensitivity": 4,
                "Brand_Loyalty": 5,
                "Impatience": 7,
                "Analytical_Thinking": 6
            }}
        }}
    }}
    """

    try:
        response = await openai_client.chat.completions.create(
            model="gpt-6-luna",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            response_format={ "type": "json_object" },
            reasoning_effort="high"
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"OpenAI Error: {e}")
        return None

async def background_ai_analysis(transcribed_text, speaker_guess, current_context, session_dir, websocket):
    ai_analysis = await analyze_with_openai(transcribed_text, speaker_guess, current_context)
    if ai_analysis:
        # Update global state persona
        ext = ai_analysis.get("extracted_persona", {})
        for key in current_persona.keys():
            if key in ext and ext[key]:
                if isinstance(current_persona[key], list):
                    current_persona[key].extend(ext[key])
                    current_persona[key] = list(set(current_persona[key]))
                elif isinstance(current_persona[key], dict):
                    current_persona[key].update(ext[key])
        
        try:
            # Kirim update Persona ke Frontend
            await websocket.send_json({
                "type": "persona",
                **current_persona
            })
            
            # Simpan persona terbaru ke file JSON
            with open(f"{session_dir}/persona.json", "w", encoding="utf-8") as f:
                json.dump(current_persona, f, indent=4, ensure_ascii=False)
            
            # Kirim Probing Questions ke Frontend
            if ai_analysis.get("probing_questions"):
                await websocket.send_json({
                    "type": "probing",
                    "questions": ai_analysis["probing_questions"]
                })
        except Exception as e:
            print(f"Gagal mengirim update dari background task: {e}")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("Client connected!")
    
    # State untuk Registrasi Suara
    app.interviewer_embedding = None
    
    # State untuk Session Logging
    session_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = f"logs/{session_id}"
    os.makedirs(session_dir, exist_ok=True)
    chunk_counter = 0
    print(f"Sesi Wawancara dimulai. Log disimpan di: {session_dir}")
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("type") == "error":
                print(f"Error dari Frontend Browser: {message.get('message')}")
                continue
                
            if message.get("type") == "set_context":
                app.user_app_context = message.get("context", "")
                print(f"Konteks Aplikasi Diset: {app.user_app_context}")
                continue

            if message.get("type") == "audio_chunk":
                print("Menerima potongan audio baru dari frontend...")
                # 1. Terima Audio base64
                audio_b64 = message["audio"]
                audio_bytes = base64.b64decode(audio_b64)
                
                # Simpan sementara untuk diproses Whisper
                temp_filename = "temp_chunk.mp4"
                async with aiofiles.open(temp_filename, "wb") as f:
                    await f.write(audio_bytes)
                
                # 2. Transkripsi dengan OpenAI Whisper
                try:
                    with open(temp_filename, "rb") as audio_file:
                        transcript_response = await openai_client.audio.transcriptions.create(
                            model="whisper-1",
                            file=audio_file,
                            language="id",
                            temperature=0.0,
                            prompt="Umm, ya, halo, siapakah, anda, namanya, oke, jadi begini."
                        )
                    
                    transcribed_text = transcript_response.text.strip()
                    print(f"Hasil Transkripsi: {transcribed_text}")
                    
                    lower_text = transcribed_text.lower()
                    
                    # Daftar ekstensif halusinasi Whisper saat audio hening
                    hallucinations = [
                        "terima kasih telah menonton", "terima kasih sudah menonton", 
                        "share this video", "ご視聴", "subscribe", "terjemahan",
                        "selamat menikmati", "halo apa kabar", "halo, apa kabar",
                        "sampai jumpa di video selanjutnya", "sampai jumpa",
                        "amara.org", "subtitle", "terjemahan oleh", "teks oleh",
                        "teks terjemahan", "thanks for watching", "mohon maaf",
                        "mohon ditunggu", "jangan lupa", "sampai bertemu",
                        "musik", "music", "...", "terima kasih.",
                        "www.websiteonline.com", "websiteonline"
                    ]
                    
                    import re
                    # Hapus spasi & tanda baca untuk pengecekan murni
                    clean_text = re.sub(r'[^\w\s]', '', lower_text).strip()
                    
                    if not transcribed_text or any(h in lower_text for h in hallucinations):
                        transcribed_text = ""
                    # Tolak kalimat yang terlalu pendek & tidak bermakna
                    elif len(clean_text.split()) <= 2 and ("terima kasih" in clean_text or "halo" in clean_text or "oke" in clean_text or "ya" == clean_text):
                        transcribed_text = ""
                    # Tolak jika isinya HANYA tanda baca atau simbol
                    elif len(clean_text) == 0:
                        transcribed_text = ""
                        
                except Exception as e:
                    print(f"Whisper Error: {e}")
                    transcribed_text = ""

                # 3. Diarization dengan Pyannote (12-Second Fast Buffer)
                if transcribed_text:
                    speaker_guess = "Interviewee"
                    try:
                        import subprocess
                        import soundfile as sf
                        import numpy as np
                        import torch
                        
                        subprocess.run(["afconvert", temp_filename, "-f", "WAVE", "-d", "LEI16", "temp_chunk.wav"], check=True)
                        chunk_data, samplerate = sf.read("temp_chunk.wav")
                        
                        if embedding_model is not None:
                            # 1. Ubah potongan kalimat utuh menjadi Tensor
                            wav_tensor = torch.tensor(chunk_data).unsqueeze(0).float()
                            
                            # 2. Ekstrak Sidik Jari Suara (Voice Fingerprint)
                            with torch.no_grad():
                                current_embedding = embedding_model(wav_tensor).squeeze(0).cpu().numpy()
                                
                            # 3. Pendaftaran Suara Otomatis (Auto-Enrollment)
                            if app.interviewer_embedding is None:
                                print("MENGUNCI SUARA PEWAWANCARA...")
                                app.interviewer_embedding = current_embedding
                                speaker_guess = "Interviewer"
                            else:
                                # 4. Pencocokan Suara (Speaker Verification)
                                similarity = 1 - cosine(app.interviewer_embedding, current_embedding)
                                print(f"Kemiripan suara: {similarity:.2f} (Threshold 0.75)")
                                
                                if similarity > 0.75:
                                    speaker_guess = "Interviewer"
                                else:
                                    speaker_guess = "Interviewee"
                        else:
                            speaker_guess = "Interviewer" if transcribed_text.endswith('?') else "Interviewee"
                    except Exception as e:
                        print(f"Sistem Registrasi Suara error: {e}")
                        speaker_guess = "Interviewer" if transcribed_text.endswith('?') else "Interviewee"
                    
                    full_transcript.append({"speaker": speaker_guess, "text": transcribed_text})
                    
                    # Simpan audio rekaman
                    chunk_counter += 1
                    shutil.copy("temp_chunk.wav", f"{session_dir}/audio_chunk_{chunk_counter}_{speaker_guess}.wav")
                    
                    # Simpan live transcript
                    with open(f"{session_dir}/transcript.txt", "a", encoding="utf-8") as f:
                        f.write(f"[{speaker_guess}]: {transcribed_text}\n")
                    
                    # Kirim Transkrip ke Frontend
                    await websocket.send_json({
                        "type": "transcript",
                        "speaker": speaker_guess,
                        "text": transcribed_text
                    })
                    
                    # 4. Analisis pakai AI untuk semua orang yang berbicara panjang di background
                    if len(transcribed_text) > 10:
                        current_context = getattr(app, 'user_app_context', '')
                        asyncio.create_task(background_ai_analysis(transcribed_text, speaker_guess, current_context, session_dir, websocket))

            elif message.get("type") == "generate_recommendations":
                # 5. Generate UI/UX & Feature Recommendations based on Persona
                prompt = f"""
                Berdasarkan Persona Pengguna berikut yang telah terkumpul selama wawancara:
                {json.dumps(current_persona)}
                
                Berikan rekomendasi:
                1. Fitur Produk (Product Features)
                2. Pola UI/UX (UI/UX Patterns)
                Gunakan format Markdown.
                """
                
                resp = await openai_client.chat.completions.create(
                    model="gpt-6-luna",
                    messages=[{"role": "user", "content": prompt}],
                    reasoning_effort="high"
                )
                
                await websocket.send_json({
                    "type": "recommendations",
                    "content": resp.choices[0].message.content
                })

    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"Error: {e}")
