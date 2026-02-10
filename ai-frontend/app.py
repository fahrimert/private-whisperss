import streamlit as st
import requests
import time
import os
import io

# Mikrofon kütüphanesi kontrolü
try:
    from audiorecorder import audiorecorder
except ImportError:
    st.warning("Mikrofon özelliği için kütüphane eksik. Terminalde şunu çalıştırın: pip install streamlit-audiorecorder")
    audiorecorder = None

# Sayfa Ayarları
st.set_page_config(page_title="AI Dedektif Paneli", page_icon="🕵️‍♂️", layout="wide")

# Backend URL
API_URL = os.getenv("API_URL", "http://api:8080")

# --- CSS İle Özelleştirme ---
st.markdown("""
    <style>
    .stApp {
        background-color: #0e1117;
    }
    .stMetric {
        background-color: #262730;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #41444e;
    }
    .big-font {
        font-size:24px !important;
        font-weight: bold;
    }
    .success-box {
        padding: 15px;
        border-radius: 10px;
        background-color: rgba(33, 195, 84, 0.1);
        border: 1px solid #21c354;
    }
    .chat-row {
        padding: 10px;
        border-radius: 5px;
        margin-bottom: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

# Başlık
st.title("🕵️‍♂️ AI Dedektif Paneli: Biyometrik Analiz")
st.markdown("---")

# --- YAN MENÜ ---
with st.sidebar:
    st.header("🔍 Kanıt Topla")
    
    input_method = st.radio("Yöntem Seçin:", ["Dosya Yükle 📂", "Mikrofon Kullan 🎤"])
    
    files_to_send = None

    # 1. DOSYA YÜKLEME
    if input_method == "Dosya Yükle 📂":
        uploaded_file = st.file_uploader("Ses Dosyası (MP3/WAV)", type=["mp3", "wav"])
        if uploaded_file is not None:
            files_to_send = {"file": uploaded_file}

    # 2. MİKROFON
    elif input_method == "Mikrofon Kullan 🎤":
        if audiorecorder:
            st.info("Kaydı başlatmak için butona basın, konuşun ve durdurun.")
            audio = audiorecorder("Kaydı Başlat", "Kaydı Durdur")
            
            if len(audio) > 0:
                st.audio(audio.export().read())
                audio_bytes = io.BytesIO()
                audio.export(audio_bytes, format="wav")
                audio_bytes.seek(0)
                files_to_send = {"file": ("mic_recording.wav", audio_bytes, "audio/wav")}
        else:
            st.error("Mikrofon kütüphanesi (audiorecorder) yüklü değil.")

    # ORTAK GÖNDERME BUTONU
    if files_to_send is not None:
        if st.button("Analizi Başlat 🚀", type="primary"):
            with st.spinner("Dosya Backend'e yükleniyor..."):
                try:
                    response = requests.post(f"{API_URL}/upload", files=files_to_send)
                    
                    if response.status_code == 200:
                        data = response.json()
                        job_id = data.get("job_id")
                        st.session_state['job_id'] = job_id
                        st.session_state['status'] = 'processing'
                        # Yeni analizde temizlik
                        if 'result' in st.session_state: del st.session_state['result']
                        if 'messages' in st.session_state: st.session_state['messages'] = []
                        
                        st.success(f"✅ Dosya Kuyruğa Alındı! ID: {job_id}")
                        st.rerun()
                    else:
                        st.error(f"Yükleme hatası: {response.text}")
                except Exception as e:
                    st.error(f"Bağlantı hatası: {e}")

# --- ANA EKRAN MANTIĞI ---

# 1. İŞLEM DURUMU KONTROLÜ
if 'job_id' in st.session_state and st.session_state.get('status') == 'processing':
    job_id = st.session_state['job_id']
    status_text = st.empty()
    progress_bar = st.progress(0)
    
    for i in range(100):
        try:
            check = requests.get(f"{API_URL}/status/{job_id}")
            
            if check.status_code == 200:
                result = check.json()
                
                if result["status"] == "completed":
                    progress_bar.progress(100)
                    status_text.success("Analiz Tamamlandı!")
                    st.session_state['result'] = result
                    st.session_state['status'] = 'completed'
                    st.rerun()
                    break
                else:
                    status_text.info(f"Analiz ediliyor... (Backend: {result.get('status', 'bilinmiyor')})")
            else:
                status_text.warning("Worker bekleniyor...")
                
        except Exception as e:
            status_text.error(f"Bağlantı hatası: {e}")
            
        time.sleep(2)
        progress_bar.progress(min(i + 5, 95))

# 2. SONUÇLARI GÖSTER
if st.session_state.get('status') == 'completed' and 'result' in st.session_state:
    res = st.session_state['result']
    
    stress_score = res.get('stress_score', 0)
    details = res.get('stress_details', {})
    
    # KART VE TRANSKRİPT
    col1, col2 = st.columns([1, 2])
    
    with col1:
        color = "red" if stress_score > 50 else "green"
        level = "High Stress" if stress_score > 50 else "Calm"
        
        st.markdown(f"""
        <div style="border: 2px solid {color}; border-radius: 10px; padding: 20px; text-align: center;">
            <h3 style="color: {color}; margin:0;">STRES SKORU</h3>
            <h1 style="font-size: 80px; color: {color}; margin:0;">{int(stress_score)}</h1>
            <h3 style="color: {color}; margin:0;">{level}</h3>
        </div>
        """, unsafe_allow_html=True)
        
    with col2:
        st.subheader("📝 Transkript")
        st.info(res.get('transcript', 'Metin yok...'))
        
        if 'reasons' in details:
            st.warning(f"🚨 **Tespitler:** {details['reasons']}")

    st.markdown("---")
    
    # BİYOMETRİK VERİLER
    st.subheader("📊 Biyometrik Sinyaller")
    m1, m2, m3 = st.columns(3)
    m1.metric("Titreme (Tremor)", f"{details.get('tremor_index', 0):.3f}")
    m2.metric("Ses Kaosu", f"{details.get('chaos_index', 0):.4f}")
    m3.metric("Hız (BPM)", f"{details.get('tempo', 0):.1f}")

    # --- YENİ EKLENEN KISIM: STRES ZAMAN ÇİZELGESİ ---
    # Worker'dan gelen 'timeline' verisi varsa grafiği çiz
    timeline_data = details.get("timeline", [])
    if timeline_data and len(timeline_data) > 0:
        st.markdown("---")
        st.subheader("📈 Stres Zaman Çizelgesi (Saniye Saniye)")
        st.caption("Konuşma süresince stres seviyesinin değişimi (0-100)")
        # Kırmızı renkli alan grafiği
        st.area_chart(timeline_data, color="#ff4b4b")
    # ------------------------------------------------

    st.markdown("---")

    # 3. CHAT BÖLÜMÜ
    st.header("💬 Dedektif ile Sohbet")
    st.caption("Bu analiz hakkında Llama 3 modeline soru sorabilirsiniz.")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Örn: Mike neden bu kadar gergin görünüyor?"):
        with st.chat_message("user"):
            st.markdown(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})

        with st.chat_message("assistant"):
            with st.spinner("Dedektif düşünüyor..."):
                try:
                    payload = {"question": prompt}
                    chat_response = requests.post(f"{API_URL}/chat", json=payload)
                    
                    if chat_response.status_code == 200:
                        ai_reply = chat_response.json().get("answer", "Cevap yok.")
                        st.markdown(ai_reply)
                        st.session_state.messages.append({"role": "assistant", "content": ai_reply})
                    else:
                        st.error(f"Hata: {chat_response.text}")
                except Exception as e:
                    st.error(f"Bağlantı hatası: {e}")