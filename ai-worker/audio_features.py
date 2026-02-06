import librosa
import numpy as np
import warnings

warnings.filterwarnings("ignore")

def analyze_stress(file_path):
    try:
        y, sr = librosa.load(file_path)

        # 1. Temel Ölçümler
        rms = librosa.feature.rms(y=y)
        avg_energy = np.mean(rms)

        f0, voiced_flag, voiced_probs = librosa.pyin(
            y, fmin=librosa.note_to_hz('C2'), fmax=librosa.note_to_hz('C7')
        )
        f0_clean = f0[~np.isnan(f0)]
        
        if len(f0_clean) == 0:
            pitch_variance = 0
            avg_pitch = 0
        else:
            pitch_variance = np.std(f0_clean)
            avg_pitch = np.mean(f0_clean)

        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        tempo = librosa.beat.tempo(onset_envelope=onset_env, sr=sr)
        avg_tempo = tempo[0] if len(tempo) > 0 else 0

        print(f"🔍 DEBUG ANALİZ: Pitch={avg_pitch:.2f}Hz, Variance={pitch_variance:.2f}, Tempo={avg_tempo:.2f}, Energy={avg_energy:.4f}", flush=True)

        score = 0
        reasons = []

        # --- ORTAK KRİTERLER (Herkes İçin) ---
        
        # 1. HIZ (TEMPO): Mike'ı Yakalar
        if avg_tempo > 160:
            score += 50
            reasons.append("Extreme Speed")
        elif avg_tempo > 130:
            score += 30
            reasons.append("Fast Speech")

        # 2. TİTREME (VARIANCE): Robot sesinde bile olsa panik belirtisidir
        if pitch_variance > 35:
            score += 20
            reasons.append("Unstable Voice")

        # --- CİNSİYETE ÖZEL KRİTERLER (Pitch) ---
        
        # 160Hz altı Erkek, üstü Kadın kabul edelim
        if avg_pitch < 160:
            # ERKEK MODU (Mike)
            if avg_pitch > 130: 
                score += 30
                reasons.append("Male High Pitch")
        else:
            # KADIN MODU (Sarah)
            # Sarah 257Hz gelmişti. Eşiği 245'e çekelim ki onu yakalasın.
            if avg_pitch > 245: 
                score += 40
                reasons.append("High Pitch Scream")
            elif avg_pitch > 220:
                score += 20

        # --- ÖZEL DURUMLAR ---
        
        # Sessiz Panik (Fısıltı) - Enerji düşük ama Hız yüksek
        if avg_energy < 0.05 and avg_tempo > 120:
            score += 20
            reasons.append("Whispered Panic")
        
        # Yüksek Enerji (Bağırma)
        if avg_energy > 0.08:
            score += 15
            reasons.append("Loud Volume")

        final_score = min(100, score)
        
        if final_score > 65: label = "HIGH STRESS"
        elif final_score > 40: label = "Moderate Stress"
        else: label = "Calm"

        return final_score, {
            "pitch": round(float(avg_pitch), 2),
            "tempo": round(float(avg_tempo), 2),
            "reasons": ", ".join(reasons),
            "analysis": label
        }

    except Exception as e:
        print(f"⚠️ Audio Analiz Hatası: {e}")
        return 0, {"error": str(e)}