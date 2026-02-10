import streamlit as st
import requests
import time

st.set_page_config(page_title="AI Yalan Dedektifi", layout="wide")

API_URL = "http://api:8080"

st.title(" AI Dedektif Paneli: Mike & Sarah Operasyonu")
st.markdown("---")

with st.sidebar:
    st.header("Kanıt Yükle")
    uploaded_file = st.file_uploader("Ses Dosyası Seç (MP3)", type=["mp3", "wav"])
    
    if uploaded_file is not None:
        if st.button("Analizi Başlat"):
            with st.spinner("Dosya Dedektife Gönderiliyor..."):
                files = {"file": (uploaded_file.name, uploaded_file, "audio/mpeg")}
                try:
                    response = requests.post(f"{API_URL}/upload", files=files)
                    if response.status_code == 200:
                        st.success(" Dosya Yüklendi! Analiz Başladı.")
                        st.info("Worker arka planda sesi işliyor (Stres, Pitch, Tempo)...")
                        time.sleep(2) 
                    else:
                        st.error(f"Hata: {response.text}")
                except Exception as e:
                    st.error(f"Bağlantı Hatası: {e}")

st.header("Sorgu Odası")

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Şüpheli hakkında ne öğrenmek istiyorsun?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        message_placeholder.markdown("Dedektif düşünüyor...")
        
        try:
            payload = {"question": prompt}
            response = requests.post(f"{API_URL}/chat", json=payload)
            
            if response.status_code == 200:
                answer = response.json().get("answer", "Cevap alınamadı.")
                message_placeholder.markdown(answer)
                st.session_state.messages.append({"role": "assistant", "content": answer})
            else:
                message_placeholder.markdown("API Hatası: Dedektif cevap veremiyor.")
        except Exception as e:
            message_placeholder.markdown(f"Bağlantı Koptu: {e}")

st.markdown("---")
st.caption("Powered by Llama 3, Whisper & Librosa Audio Analysis Engine")