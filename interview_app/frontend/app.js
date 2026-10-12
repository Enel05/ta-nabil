let socket = null;
let mediaRecorder = null;
let audioChunks = [];

const recordBtn = document.getElementById('record-btn');
const stopBtn = document.getElementById('stop-btn');
const transcriptBox = document.getElementById('transcript-box');
const recordingWave = document.getElementById('recording-wave');
const wsStatusDot = document.getElementById('ws-status-dot');
const wsStatusText = document.getElementById('ws-status-text');
const saveContextBtn = document.getElementById('save-context-btn');
const appContextInput = document.getElementById('app-context-input');

saveContextBtn.addEventListener('click', () => {
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({
            type: 'set_context',
            context: appContextInput.value
        }));
        
        // Visual feedback
        const originalText = saveContextBtn.innerHTML;
        saveContextBtn.innerHTML = '<i class="fa-solid fa-check"></i> Tersimpan';
        saveContextBtn.style.background = 'var(--success)';
        setTimeout(() => {
            saveContextBtn.innerHTML = originalText;
            saveContextBtn.style.background = '';
        }, 2000);
    } else {
        alert("Koneksi ke server belum siap.");
    }
});

// Connect to backend WebSocket
function connectWebSocket() {
    socket = new WebSocket('ws://localhost:8002/ws');
    
    socket.onopen = () => {
        wsStatusDot.className = 'dot connected';
        wsStatusText.textContent = 'Connected to Server';
    };
    
    socket.onclose = () => {
        wsStatusDot.className = 'dot disconnected';
        wsStatusText.textContent = 'Disconnected';
        setTimeout(connectWebSocket, 3000); // Auto reconnect
    };
    
    socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleServerMessage(data);
    };
}

connectWebSocket();

function handleServerMessage(data) {
    if (data.type === 'transcript') {
        appendTranscript(data.speaker, data.text);
    } else if (data.type === 'probing') {
        updateProbing(data.questions);
    } else if (data.type === 'persona') {
        updatePersona(data);
    } else if (data.type === 'recommendations') {
        updateRecommendations(data.content);
    }
}

let recordingInterval;

// Audio Recording
recordBtn.addEventListener('click', async () => {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ 
            audio: {
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true
            } 
        });
        
        recordBtn.disabled = true;
        stopBtn.disabled = false;
        recordingWave.style.display = 'flex';
        transcriptBox.innerHTML = '';
        
        // Kirim konteks aplikasi ke backend
        const appContext = document.getElementById('app-context-input').value;
        if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({
                type: 'set_context',
                context: appContext
            }));
        }
        
        // Setup Audio Analyser untuk VAD (Voice Activity Detection)
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const analyser = audioContext.createAnalyser();
        const microphone = audioContext.createMediaStreamSource(stream);
        microphone.connect(analyser);
        analyser.fftSize = 512;
        const bufferLength = analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);
        
        let silenceTimer = null;
        let isRecordingActive = false;
        let forceStopTimer = null;
        let voiceDetected = false;
        
        // Fungsi untuk merekam dinamis
        const startChunkRecording = () => {
            if (stopBtn.disabled) return;
            
            // Reset deteksi suara setiap potongan baru
            voiceDetected = false;
            
            // Biarkan browser memilih format default (Safari=mp4, Chrome=webm)
            mediaRecorder = new MediaRecorder(stream);
            let audioChunks = [];
            
            mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) audioChunks.push(event.data);
            };
            
            mediaRecorder.onstop = () => {
                try {
                    if (socket.readyState === WebSocket.OPEN && audioChunks.length > 0 && voiceDetected) {
                        const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType || 'audio/mp4' });
                        const reader = new FileReader();
                        reader.readAsDataURL(blob);
                        reader.onloadend = () => {
                            try {
                                const base64data = reader.result.split(',')[1];
                                socket.send(JSON.stringify({
                                    type: 'audio_chunk',
                                    audio: base64data
                                }));
                            } catch (e) {
                                socket.send(JSON.stringify({type: 'error', message: 'FileReader parsing error: ' + e.message}));
                            }
                        };
                    } else if (!voiceDetected) {
                        console.log("Chunk dibuang karena hanya berisi keheningan.");
                    }
                } catch (e) {
                    socket.send(JSON.stringify({type: 'error', message: 'Onstop error: ' + e.message}));
                }
                
                if (!stopBtn.disabled) {
                    startChunkRecording();
                }
            };
            
            mediaRecorder.start();
            isRecordingActive = true;
            
            // Paksa potong jika bicara tanpa henti lebih dari 60 detik (fallback)
            forceStopTimer = setTimeout(() => {
                if (mediaRecorder.state === 'recording') {
                    mediaRecorder.stop();
                }
            }, 60000); 
        };
        
        const checkSilence = () => {
            if (stopBtn.disabled) return;
            
            analyser.getByteFrequencyData(dataArray);
            let sum = 0;
            for(let i = 0; i < bufferLength; i++) {
                sum += dataArray[i];
            }
            let averageVolume = sum / bufferLength;
            
            if (averageVolume < 5) { // Ambang batas hening diturunkan (5) untuk mendeteksi suara jarak jauh (2 meter)
                if (!silenceTimer && isRecordingActive && voiceDetected) {
                    // Jika hening selama 2.5 detik SETELAH ada suara, potong rekaman
                    silenceTimer = setTimeout(() => {
                        if (mediaRecorder && mediaRecorder.state === 'recording') {
                            isRecordingActive = false;
                            clearTimeout(forceStopTimer);
                            mediaRecorder.stop();
                        }
                    }, 2500); 
                }
            } else {
                // Suara manusia terdeteksi
                voiceDetected = true;
                if (silenceTimer) {
                    clearTimeout(silenceTimer);
                    silenceTimer = null;
                }
            }
            
            requestAnimationFrame(checkSilence);
        };
        
        startChunkRecording();
        checkSilence(); // Mulai memantau keheningan
        
    } catch (err) {
        console.error("Error accessing microphone:", err);
        alert("Mohon izinkan akses mikrofon untuk memulai wawancara.");
    }
});

stopBtn.addEventListener('click', () => {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop();
        mediaRecorder.stream.getTracks().forEach(track => track.stop());
    }
    
    recordBtn.disabled = false;
    stopBtn.disabled = true;
    recordingWave.style.display = 'none';
});

document.getElementById('generate-recommendations-btn').addEventListener('click', () => {
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'generate_recommendations' }));
    }
});

// UI Update Functions
function appendTranscript(speaker, text) {
    const msgDiv = document.createElement('div');
    const isInterviewer = speaker.toLowerCase().includes('interviewer') || speaker === 'Speaker 1';
    
    msgDiv.className = `message ${isInterviewer ? 'interviewer' : 'interviewee'}`;
    
    msgDiv.innerHTML = `
        <div class="msg-header">
            <span class="speaker-name">${isInterviewer ? '🎤 Pewawancara' : '👤 Narasumber'}</span>
            <span>${new Date().toLocaleTimeString()}</span>
        </div>
        <div class="msg-content">${text}</div>
    `;
    
    transcriptBox.appendChild(msgDiv);
    transcriptBox.scrollTop = transcriptBox.scrollHeight;
}

function updateProbing(questions) {
    const box = document.getElementById('suggestions-box');
    if (box.querySelector('.placeholder-text')) {
        box.innerHTML = '';
    }
    
    // Clear previous probing suggestions to only show the latest 3
    box.innerHTML = '';
    
    if (questions && questions.length > 0) {
        questions.forEach((q, index) => {
            const div = document.createElement('div');
            div.className = 'suggestion-item fade-in';
            div.style.animationDelay = `${index * 0.1}s`;
            div.innerHTML = `
                <strong>💡 Pertanyaan ${index + 1}:</strong>
                <p>"${q.question}"</p>
                <small style="color: var(--text-muted); display: block; margin-top: 5px;">
                    <i class="fa-solid fa-circle-info"></i> Alasan: ${q.reason}
                </small>
            `;
            box.appendChild(div);
        });
        
        box.scrollTop = box.scrollHeight;
    }
}

let radarChart = null;

function updatePersona(persona) {
    const updateList = (id, items) => {
        const ul = document.getElementById(id);
        if(items && items.length > 0) {
            ul.innerHTML = items.map(i => `<li>${i}</li>`).join('');
        }
    };
    
    // Update Lists
    updateList('persona-goals', persona.goals);
    updateList('persona-motivations', persona.motivations);
    updateList('persona-needs', persona.needs);
    updateList('persona-painpoints', persona.pain_points);
    
    // Update Demographics
    if (persona.demographics) {
        document.getElementById('persona-name').textContent = persona.demographics.name || "Belum diketahui";
        document.getElementById('persona-age').textContent = persona.demographics.age || "Belum diketahui";
        document.getElementById('persona-occupation').textContent = persona.demographics.occupation || "Belum diketahui";
        document.getElementById('persona-location').textContent = persona.demographics.location || "Belum diketahui";
    }
    
    // Update Psychographics
    if (persona.psychographics) {
        document.getElementById('persona-personality').textContent = persona.psychographics.personality;
        updateList('persona-interests', persona.psychographics.interests);
    }
    
    // Update Behaviors
    if (persona.behaviors) {
        document.getElementById('persona-behaviors').innerHTML = `
            <strong>Usage Patterns:</strong> ${persona.behaviors.usage_patterns}<br>
            <strong>Brand Loyalty:</strong> ${persona.behaviors.brand_loyalty}
        `;
    }
    
    // Render Chart.js
    if (persona.metrics) {
        const ctx = document.getElementById('personaChart').getContext('2d');
        const dataValues = [
            persona.metrics.Tech_Savviness || 5,
            persona.metrics.Price_Sensitivity || 5,
            persona.metrics.Brand_Loyalty || 5,
            persona.metrics.Impatience || 5,
            persona.metrics.Analytical_Thinking || 5
        ];
        
        if (radarChart) {
            radarChart.data.datasets[0].data = dataValues;
            radarChart.update();
        } else {
            radarChart = new Chart(ctx, {
                type: 'radar',
                data: {
                    labels: ['Tech Savvy', 'Price Sensitive', 'Brand Loyal', 'Impatience', 'Analytical'],
                    datasets: [{
                        label: 'Persona Traits (1-10)',
                        data: dataValues,
                        backgroundColor: 'rgba(234, 88, 12, 0.2)', // var(--primary)
                        borderColor: '#ea580c',
                        pointBackgroundColor: '#c2410c',
                        borderWidth: 2
                    }]
                },
                options: {
                    scales: {
                        r: {
                            angleLines: { color: 'rgba(24, 24, 27, 0.2)' },
                            grid: { color: 'rgba(24, 24, 27, 0.2)' },
                            pointLabels: { color: '#18181b', font: { family: 'Inter', size: 12, weight: 600 } },
                            ticks: { display: false, min: 0, max: 10 }
                        }
                    },
                    plugins: {
                        legend: { labels: { color: '#09090b', font: { family: 'Inter', weight: 800 } } }
                    }
                }
            });
        }
    }
}

function updateRecommendations(content) {
    const box = document.getElementById('recommendations-box');
    // Simple basic markdown parser for demo
    const htmlContent = content
        .replace(/### (.*)/g, '<h3>$1</h3>')
        .replace(/\*\*(.*)\*\*/g, '<strong>$1</strong>')
        .replace(/\* (.*)/g, '<li>$1</li>')
        .replace(/- (.*)/g, '<li>$1</li>');
        
    box.innerHTML = `<div class="markdown-content">${htmlContent}</div>`;
}
