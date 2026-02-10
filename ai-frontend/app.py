import streamlit as st
import requests
import io
from audiorecorder import audiorecorder
import time

# Sayfa Ayarları
st.set_page_config(page_title="AI Dedektif Paneli", page_icon="🕵️‍♂️", layout="wide")

API_URL = "http://api:8080" # Backend Adresi

# CSS: Metrikleri büyüt
st.markdown("""
<style>
    div[data-testid="stMetricValue"] { font-size: 24px; }
    .stProgress > div > div > div > div { background-color: #f63366; }
</style>
""", unsafe_allow_html=True)

st.title("🕵️‍♂️ AI Dedektif Paneli: Biyometrik Analiz")
st.markdown("---")

if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None

# --- YAN PANEL ---
with st.sidebar:
    st.header("🔍 Kanıt Topla")
    input_method = st.radio("Yöntem:", ["Dosya Yükle 📂", "Mikrofon 🎤"])
    
    file_to_upload = None

    if input_method == "Dosya Yükle 📂":
        uploaded_file = st.file_uploader("Ses Dosyası (MP3/WAV)", type=["mp3", "wav"])
        if uploaded_file:
            file_to_upload = {"file": (uploaded_file.name, uploaded_file, "audio/mpeg")}

    elif input_method == "Mikrofon 🎤":
        st.info("Kayıt al ve analize gönder.")
        audio = audiorecorder("Kaydı Başlat", "Durdur")
        if len(audio) > 0:
            st.audio(audio.export().read())
            audio_bytes = io.BytesIO()
            audio.export(audio_bytes, format="wav")
            audio_bytes.seek(0)
            file_to_upload = {"file": ("mic_recording.wav", audio_bytes, "audio/wav")}

    if file_to_upload and st.button("Analizi Başlat 🚀", type="primary"):
        with st.spinner("Dosya Backend'e gönderiliyor..."):
            try:
                # 1. Dosyayı Yükle
                response = requests.post(f"{API_URL}/upload", files=file_to_upload)
                
                if response.status_code == 200:
                    data = response.json()
                    file_id = data.get("file_id")
                    st.success("✅ Dosya Kuyruğa Alındı! Worker bekleniyor...")
                    
                    # 2. Polling (Sürekli sorma)
                    progress_text = "Analiz ediliyor..."
                    my_bar = st.progress(0, text=progress_text)
                    
                    for percent_complete in range(100):
                        time.sleep(1) # 1 saniye bekle
                        my_bar.progress(percent_complete + 1, text=f"{progress_text} ({percent_complete}sn)")
                        
                        # Backend'e sor: Bitti mi?
                        try:
                            status_res = requests.get(f"{API_URL}/status/{file_id}")
                            if status_res.status_code == 200:
                                res_json = status_res.json()
                                if res_json.get("status") == "completed":
                                    st.session_state.analysis_result = res_json
                                    my_bar.progress(100, text="Analiz Tamamlandı!")
                                    st.success("Sonuçlar Hazır!")
                                    break
                        except:
                            pass
                    else:
                        st.error("Zaman aşımı! Worker cevap vermedi.")
                else:
                    st.error(f"Hata: {response.text}")
            except Exception as e:
                st.error(f"Bağlantı Hatası: {e}")

# --- ANA EKRAN (GÖSTERGELER) ---
if st.session_state.analysis_result:
    data = st.session_state.analysis_result
    # Eğer Qdrant'tan gelen veri string ise parse etmeye gerek olabilir, 
    # ama Go kodunda map[string]interface gönderdik, JSON olarak gelir.
    details = data.get("stress_details", {})
    score = data.get("stress_score", 0)
    transcript = data.get("transcript", "")

    col1, col2 = st.columns([1, 2])
    
    with col1:
        # Renkli Skor
        color = "green"
        if score > 60: color = "red"
        elif score > 30: color = "orange"
        
        st.markdown(f"""
            <div style="text-align: center; border: 4px solid {color}; padding: 20px; border-radius: 15px;">
                <h3 style="color: {color}; margin:0;">STRES SKORU</h3>
                <h1 style="font-size: 80px; color: {color}; margin:0;">{int(score)}</h1>
                <h4 style="color: gray;">{details.get('analysis', 'Unknown')}</h4>
            </div>
        """, unsafe_allow_html=True)

    with col2:
        st.subheader("📝 Transkript")
        st.info(f'"{transcript}"')
        if details.get("reasons"):
            st.warning(f"🚨 Tespitler: {details.get('reasons')}")

    st.markdown("### 📊 Biyometrik Sinyaller")
    m1, m2, m3 = st.columns(3)
    
    with m1:
        # Tremor (Titreme)
        val = float(details.get("tremor_index", 0))
        pct = min(100, int(val * 200)) # 0.5 -> 100%
        st.metric("Titreme (Tremor)", f"{val}")
        st.progress(pct)

    with m2:
        # Chaos (Kaos)
        val = float(details.get("chaos_index", 0))
        pct = min(100, int(val * 1500)) 
        st.metric("Ses Kaosu", f"{val}")
        st.progress(pct)

    with m3:
        # Tempo
        val = float(details.get("tempo", 0))
        # 60 BPM = %0, 180 BPM = %100
        pct = min(100, max(0, int((val - 60) * 0.8)))
        st.metric("Hız (BPM)", f"{val}")
        st.progress(pct)