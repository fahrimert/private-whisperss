import librosa
import numpy as np
import warnings
from scipy.stats import variation

warnings.filterwarnings("ignore")

def normalize_feature(value, min_val, max_val):
    """Değeri 0-100 arasına sıkıştırır (Clamping)"""
    return max(0, min(100, (value - min_val) / (max_val - min_val) * 100))

def analyze_stress(file_path):
    try:
        # Sesi yükle (Mono)
        y, sr = librosa.load(file_path)
        duration = librosa.get_duration(y=y, sr=sr)

        # --- YENİ EKLENEN KISIM: ZAMAN ÇİZELGESİ (TIMELINE) ---
        # Grafiği çizmek için saniye saniye enerji ve gerginlik analizi
        timeline = []
        total_seconds = int(duration)
        if total_seconds == 0: total_seconds = 1 # Çok kısa dosyalar için koruma

        for t in range(total_seconds):
            # Saniyelik parça al (Slicing)
            start_sample = t * sr
            end_sample = (t + 1) * sr
            chunk = y[start_sample:end_sample]
            
            if len(chunk) > 0:
                # O saniyedeki Enerji (RMS) -> Bağırma şiddeti
                local_rms = np.mean(librosa.feature.rms(y=chunk))
                # O saniyedeki Tizlik/Sertlik (Zero Crossing Rate) -> Heyecan
                local_zcr = np.mean(librosa.feature.zero_crossing_rate(chunk))
                
                # Basit bir anlık stres formülü (Normalize edilmemiş ham değerlerden skor üretme)
                # RMS genelde 0.0-0.1 arası, ZCR 0.0-0.2 arasıdır. Katsayılarla 0-100'e çekiyoruz.
                momentary_stress = (local_rms * 400) + (local_zcr * 150)
                
                # 0-100 arasına sıkıştır ve listeye ekle
                timeline.append(min(100, max(0, momentary_stress)))
            else:
                timeline.append(0)
        # -------------------------------------------------------

        # --- 1. ÖZNİTELİK ÇIKARIMI (MEVCUT KOD) ---
        
        # A. Pitch (F0) Analizi
        f0, voiced_flag, voiced_probs = librosa.pyin(
            y, fmin=librosa.note_to_hz('C2'), fmax=librosa.note_to_hz('C7')
        )
        f0_clean = f0[~np.isnan(f0)]
        
        # B. Enerji (RMS)
        rms = librosa.feature.rms(y=y)[0]
        
        # C. Spektral Düzlük (Spectral Flatness)
        flatness = librosa.feature.spectral_flatness(y=y)[0]
        
        # D. Tempo
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        tempo = librosa.beat.tempo(onset_envelope=onset_env, sr=sr)
        avg_tempo = tempo[0] if len(tempo) > 0 else 0

        # --- 2. İSTATİSTİKSEL HESAPLAMALAR (EVRENSEL) ---
        
        if len(f0_clean) == 0:
            return 0, {"error": "No voice detected", "timeline": []}

        # Varyasyon Katsayısı (CV)
        pitch_cv = variation(f0_clean)
        
        # Enerji Değişkenliği
        energy_cv = variation(rms)
        
        # Ortalama Kaos (Flatness)
        mean_flatness = np.mean(flatness)

        # --- 3. SKORLAMA (NORMALİZASYON) ---
        
        # A. Stabilite Skoru
        score_instability = normalize_feature(pitch_cv, 0.15, 0.45)
        
        # B. Enerji Skoru
        score_energy_var = normalize_feature(energy_cv, 0.4, 1.2)
        
        # C. Kaos Skoru
        score_chaos = normalize_feature(mean_flatness, 0.01, 0.06)
        
        # D. Tempo Skoru
        score_tempo = normalize_feature(avg_tempo, 90, 160)

        # --- 4. AĞIRLIKLI ORTALAMA ---
        
        final_score = (
            (score_instability * 0.40) +  # En önemli: Ses titremesi
            (score_chaos * 0.30) +        # Önemli: Sesin bozulması/yırtılması
            (score_tempo * 0.15) +        # Yan etken: Hız
            (score_energy_var * 0.15)     # Yan etken: Enerji dalgalanması
        )
        
        # Sebepleri belirle
        reasons = []
        if score_instability > 60: reasons.append("High Tremor")
        if score_chaos > 60: reasons.append("Harsh/Chaotic Voice")
        if score_tempo > 70: reasons.append("Rapid Speech")
        if score_energy_var > 70: reasons.append("Explosive Energy")
        
        if final_score < 25: label = "Calm"
        elif final_score < 50: label = "Mild Stress"
        elif final_score < 75: label = "High Stress"
        else: label = "EXTREME PANIC"

        print(f"🔍 DEBUG: Instab={score_instability:.1f}, Chaos={score_chaos:.1f}, TempoScore={score_tempo:.1f}, EnergyScore={score_energy_var:.1f}", flush=True)

        # --- DÖNÜŞ DEĞERİ (GÜNCELLENDİ: TIMELINE EKLENDİ) ---
        return int(final_score), {
            "tremor_index": round(float(pitch_cv), 3),
            "chaos_index": round(float(mean_flatness), 4),
            "tempo": round(float(avg_tempo), 1),
            "reasons": ", ".join(reasons),
            "analysis": label,
            "timeline": timeline  # <-- Backend ve Frontend'in kullanacağı grafik verisi
        }

    except Exception as e:
        print(f"⚠️ Audio Analiz Hatası: {e}")
        return 0, {"error": str(e), "timeline": []}