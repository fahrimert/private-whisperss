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

        # --- 1. ÖZNİTELİK ÇIKARIMI (FEATURE EXTRACTION) ---
        
        # A. Pitch (F0) Analizi
        f0, voiced_flag, voiced_probs = librosa.pyin(
            y, fmin=librosa.note_to_hz('C2'), fmax=librosa.note_to_hz('C7')
        )
        f0_clean = f0[~np.isnan(f0)]
        
        # B. Enerji (RMS)
        rms = librosa.feature.rms(y=y)[0]
        
        # C. Spektral Düzlük (Spectral Flatness)
        # Bu değer sesin ne kadar "Gürültüye/Kaosa" benzediğini ölçer.
        # Sakin ses = Düşük Flatness (Tonlu)
        # Çığlık/Panik/Hışırtı = Yüksek Flatness (Kaotik)
        flatness = librosa.feature.spectral_flatness(y=y)[0]
        
        # D. Tempo
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        tempo = librosa.beat.tempo(onset_envelope=onset_env, sr=sr)
        avg_tempo = tempo[0] if len(tempo) > 0 else 0

        # --- 2. İSTATİSTİKSEL HESAPLAMALAR (EVRENSEL) ---
        
        # Eğer ses çok kısaysa veya sessizse varsayılan değerler
        if len(f0_clean) == 0:
            return 0, {"error": "No voice detected"}

        # Varyasyon Katsayısı (CV) -> Standart Sapma / Ortalama
        # Bu oran, sesin perdesinden (ince/kalın) bağımsız olarak "Titreme"yi verir.
        # CV < 0.15: Çok stabil (Spiker gibi)
        # CV > 0.35: Çok kararsız (Ağlama, Korku)
        pitch_cv = variation(f0_clean)
        
        # Enerji Değişkenliği
        energy_cv = variation(rms)
        
        # Ortalama Kaos (Flatness)
        mean_flatness = np.mean(flatness)

        # --- 3. SKORLAMA (NORMALİZASYON) ---
        # Burada "if > 140" yok. İnsan konuşma limitlerine göre 0-100 arası puanlıyoruz.
        
        # A. Stabilite Skoru (Ses ne kadar titriyor?)
        # İnsan sesi genelde 0.1 ile 0.5 arası CV üretir.
        score_instability = normalize_feature(pitch_cv, 0.15, 0.45)
        
        # B. Enerji Skoru (Ses ne kadar patlayıcı?)
        # Enerji CV genelde 0.3 ile 1.5 arasındadır.
        score_energy_var = normalize_feature(energy_cv, 0.4, 1.2)
        
        # C. Kaos Skoru (Ses ne kadar bozuk/yırtık?)
        # Çığlık atınca bu değer tavan yapar.
        score_chaos = normalize_feature(mean_flatness, 0.01, 0.06)
        
        # D. Tempo Skoru
        # 90 BPM altı sakin, 160 BPM üstü panik kabul edilir (Lineer artış)
        score_tempo = normalize_feature(avg_tempo, 90, 160)

        # --- 4. AĞIRLIKLI ORTALAMA ---
        # Stres tek bir şey değildir. Hepsinin birleşimidir.
        
        # Titreme ve Kaos en büyük stres belirtisidir (%70 etki)
        # Hız ve Enerji değişimi yardımcı faktördür (%30 etki)
        
        final_score = (
            (score_instability * 0.40) +  # En önemli: Ses titremesi
            (score_chaos * 0.30) +        # Önemli: Sesin bozulması/yırtılması
            (score_tempo * 0.15) +        # Yan etken: Hız
            (score_energy_var * 0.15)     # Yan etken: Enerji dalgalanması
        )
        
        # Sebepleri belirle (En yüksek puanı verenler)
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

        return int(final_score), {
            "tremor_index": round(float(pitch_cv), 3),
            "chaos_index": round(float(mean_flatness), 4),
            "tempo": round(float(avg_tempo), 1),
            "reasons": ", ".join(reasons),
            "analysis": label
        }

    except Exception as e:
        print(f"⚠️ Audio Analiz Hatası: {e}")
        return 0, {"error": str(e)}