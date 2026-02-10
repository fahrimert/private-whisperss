import librosa
import numpy as np
import warnings

warnings.filterwarnings("ignore")

def analyze_stress(file_path):
    try:
        # Sesi yükle
        y, sr = librosa.load(file_path)

        # --- 1. HAM VERİLERİ ÇIKAR ---
        
        # Pitch (Perde)
        f0, voiced_flag, voiced_probs = librosa.pyin(
            y, fmin=librosa.note_to_hz('C2'), fmax=librosa.note_to_hz('C7')
        )
        f0_clean = f0[~np.isnan(f0)]
        
        # Enerji (RMS)
        rms = librosa.feature.rms(y=y)[0]
        
        # Tempo (Ritim)
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        tempo_dynamic = librosa.feature.tempogram(onset_envelope=onset_env, sr=sr)
        avg_tempo = librosa.beat.tempo(onset_envelope=onset_env, sr=sr)[0]

        # --- 2. İSTATİSTİKSEL ANALİZ (Kişiye Özel Normalizasyon) ---
        
        # Bu kişinin "Normal" ses tonu nedir?
        mean_pitch = np.mean(f0_clean) if len(f0_clean) > 0 else 0
        std_pitch = np.std(f0_clean) if len(f0_clean) > 0 else 0
        
        # Bu kişinin "Normal" enerji seviyesi nedir?
        mean_energy = np.mean(rms)
        std_energy = np.std(rms)
        
        # Pitch Değişkenliği (Titreme)
        pitch_variance = std_pitch  # Standart sapma zaten değişimdir

        # --- 3. DİNAMİK PUANLAMA (Z-Score Mantığı) ---
        # Burada "Sayılar" değil, "Sapmalar" konuşur.
        # Bir değer, ortalamadan ne kadar uzak? (Standart Sapma cinsinden)
        
        score = 0
        reasons = []
        
        # A. PITCH ANALİZİ (Göreceli)
        # Eğer pitch, ortalamanın %20 üzerindeyse veya standart sapmanın 1.5 katıysa
        if len(f0_clean) > 0:
            max_pitch = np.max(f0_clean)
            # Kişi kendi ortalamasının çok üstüne çıktı mı?
            if max_pitch > (mean_pitch + (1.5 * std_pitch)):
                score += 30
                reasons.append("Sudden Pitch Spike")
            elif max_pitch > (mean_pitch * 1.2):
                score += 15
                reasons.append("Elevated Pitch")

        # B. TİTREME (VARIANCE)
        # Standart sapma (titreme) çok yüksekse
        # İnsan sesi genelde 20-30 arası sapar. 40+ güvensizliktir.
        if std_pitch > 50:
            score += 30
            reasons.append("Extreme Voice Tremor")
        elif std_pitch > 30:
            score += 15
            reasons.append("Shaky Voice")

        # C. TEMPO (HIZ)
        # 130 BPM evrensel bir panik sınırıdır ama biz yine de dinamik bakalım.
        if avg_tempo > 140:
            score += 40
            reasons.append("Panic Speed")
        elif avg_tempo > 120:
            score += 20
            reasons.append("Fast Pace")

        # D. SESSİZLİK ORANI (Silence Ratio)
        # Çok fazla duraksamak (kem küm etmek) strestir.
        non_silent_intervals = librosa.effects.split(y, top_db=20)
        non_silent_duration = sum(end - start for start, end in non_silent_intervals) / sr
        total_duration = librosa.get_duration(y=y, sr=sr)
        silence_ratio = 1 - (non_silent_duration / total_duration)

        if silence_ratio > 0.4: # %40'tan fazla sessizlik/duraksama
            score += 15
            reasons.append("Hesitation/Pauses")

        # --- 4. SONUÇ ---
        final_score = min(100, score)
        
        # Etiketleme
        if final_score > 70: label = "HIGH STRESS"
        elif final_score > 40: label = "Moderate Stress"
        elif final_score > 20: label = "Low Stress"
        else: label = "Calm"

        # Debug için gerçek değerleri de basalım
        print(f"🔍 DEBUG: MeanPitch={mean_pitch:.1f}, MaxPitch={np.max(f0_clean):.1f}, StdDev={std_pitch:.1f}, Tempo={avg_tempo:.1f}", flush=True)

        return final_score, {
            "avg_pitch": round(float(mean_pitch), 2),
            "voice_fluctuation": round(float(std_pitch), 2),
            "tempo": round(float(avg_tempo), 2),
            "reasons": ", ".join(reasons),
            "analysis": label
        }

    except Exception as e:
        print(f"⚠️ Audio Analiz Hatası: {e}")
        return 0, {"error": str(e)}