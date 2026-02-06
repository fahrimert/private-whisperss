import pika
import os
import time
import json
import torch
import uuid 
from transformers import pipeline
from pyannote.audio import Pipeline
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from prometheus_client import start_http_server, Summary, Counter, Gauge

from audio_features import analyze_stress

REQUEST_TIME = Summary('process_processing_seconds', 'Time spent processing audio')
jobs_processed = Counter('jobs_processed_total', 'Total number of jobs processed')
jobs_failed = Counter('jobs_failed_total', 'Total number of failed jobs')
gpu_utilization = Gauge('gpu_utilization', 'Current GPU Memory Usage (MB)')

try:
    from torch.serialization import add_safe_globals
    from torch.torch_version import TorchVersion
    from pyannote.audio.core.task import Specifications, Problem, Resolution
    add_safe_globals([TorchVersion, Specifications, Problem, Resolution])
    print("🔓 PyTorch 2.6 Genişletilmiş Güvenlik Yaması Uygulandı.", flush=True)
except Exception as e:
    print(f"⚠️ Yama uygulanırken hata: {e}", flush=True)

print("🤖 Modeller yükleniyor (GPU Modu)...", flush=True)

device_str = "cuda:0" if torch.cuda.is_available() else "cpu"
device_id = 0 if torch.cuda.is_available() else -1

transcriber = pipeline("automatic-speech-recognition", model="openai/whisper-small", device=device_id)
summarizer = pipeline("summarization", model="sshleifer/distilbart-cnn-6-6", device=device_id)
embedder = SentenceTransformer('all-MiniLM-L6-v2', device=device_str)

HF_TOKEN = os.getenv("HF_TOKEN")
diarization_pipeline = None

try:
    if HF_TOKEN:
        print("🗣️ Diarization modeli yükleniyor...", flush=True)
        diarization_pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=HF_TOKEN
        )
        diarization_pipeline.to(torch.device(device_str))
        print("✅ Pyannote Diarization yüklendi!", flush=True)
    else:
        print("⚠️ HF_TOKEN bulunamadı! Konuşmacı ayrımı devre dışı kalacak.", flush=True)
except Exception as e:
    print(f"⚠️ Diarization modeli yüklenirken hata: {e}", flush=True)

print("✅ Tüm Modeller Hazır!", flush=True)

qdrant_host = os.getenv("QDRANT_HOST", "qdrant")
q_client = QdrantClient(host=qdrant_host, port=6333)
COLLECTION_NAME = "audio_memory"

try:
    if not q_client.collection_exists(COLLECTION_NAME):
        q_client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=qmodels.VectorParams(size=384, distance=qmodels.Distance.COSINE),
        )
        print(f"🧠 Hafıza (Collection) oluşturuldu: {COLLECTION_NAME}", flush=True)
    else:
        print(f"🧠 Hafıza (Collection) bulundu: {COLLECTION_NAME}", flush=True)
except Exception as e:
    print(f"⚠️ Qdrant Bağlantı Hatası: {e}", flush=True)

rabbit_url = os.environ.get('RABBITMQ_URL', 'amqp://guest:guest@rabbitmq:5672/')
params = pika.URLParameters(rabbit_url)

while True:
    try:
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        channel.queue_declare(queue='task_queue', durable=True)
        break
    except Exception:
        print("⏳ RabbitMQ bekleniyor...", flush=True)
        time.sleep(5)

print(' [*] Worker Hazır! İş bekleniyor...', flush=True)

start_http_server(8000)
print("📊 Metrics server started on port 8000", flush=True)

def update_gpu_metrics():
    if torch.cuda.is_available():
        mem = torch.cuda.memory_allocated(0) / 1024 / 1024 
        gpu_utilization.set(mem)

def format_diarization(diarization_result):
    output = []
    for turn, _, speaker in diarization_result.itertracks(yield_label=True):
        start = f"{turn.start:.1f}"
        end = f"{turn.end:.1f}"
        output.append(f"[{start}s - {end}s] {speaker}")
    return " | ".join(output)

def save_to_memory(text, summary, speakers, file_path, stress_score=0):
    try:
        print("🧠 Vektör oluşturuluyor (Full Text)...", flush=True)
        embedding = embedder.encode(text).tolist() 
        
        point_id = str(uuid.uuid4())
        q_client.upsert(
            collection_name=COLLECTION_NAME,
            points=[
                qmodels.PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload={
                        "file_path": file_path,
                        "summary": text, 
                        "text": text,
                        "full_text": text, 
                        "stress_score": stress_score,
                        "speakers": speakers,
                        "processed_at": time.time()
                    }
                )
            ]
        )
        print("🧠 Hafızaya Kaydedildi!", flush=True)
    except Exception as e:
        print(f"⚠️ Hafıza Kayıt Hatası: {e}", flush=True)

@REQUEST_TIME.time() 
def process_audio_job(file_path):
    update_gpu_metrics()
    
    print(f"🎤 Ses işleniyor: {file_path}", flush=True)
    
    result = transcriber(
        file_path, 
        return_timestamps=True, 
        generate_kwargs={"language": "english", "task": "transcribe"}
    )
    text = result["text"]
    print(f"📝 Transkript: {text}", flush=True)
    
    # --- 2. SES TONU VE STRES ANALİZİ (YENİ) ---
    print("📉 Ses Tonu Analiz Ediliyor (Biometrik Veri)...", flush=True)
    stress_score, audio_details = analyze_stress(file_path)
    print(f"📊 Stres Skoru: {stress_score}/100 ({audio_details['analysis']})", flush=True)
    
    # Llama 3'ün bu stresi görebilmesi için metnin sonuna ekliyoruz!
    ai_context_note = f"\n\n[SYSTEM ANALYSIS]: Audio Biometrics indicate a Stress Score of {stress_score}/100. Details: {audio_details}"
    final_text_for_ai = text + ai_context_note

    speakers_log = "Devre dışı"
    if diarization_pipeline:
        try:
            print("🗣️ Konuşmacılar analiz ediliyor...", flush=True)
            diarization = diarization_pipeline(file_path)
            speakers_log = format_diarization(diarization)
            print(f"👥 Konuşmacılar: {speakers_log}", flush=True)
        except Exception as d_error:
            print(f"⚠️ Diarization sırasında hata: {d_error}", flush=True)
    
    # Özetleme kısmı (Artık sadece loglarda görünmesi için var, API'ye full text gidecek)
    word_count = len(text.split())
    if word_count > 30: 
        summary = summarizer(
            text, 
            max_length=100,  
            min_length=30,    
            do_sample=False,
            repetition_penalty=2.0,
            truncation=True
        )
        final_summary = summary[0]['summary_text']
    else:
        final_summary = text
        print("ℹ️ Metin kısa olduğu için özetleme atlandı.", flush=True)

    print(f"💡 Özet (Log): {final_summary}", flush=True)

    # Kaydederken 'final_text_for_ai' kullanıyoruz ki Llama 3 stres notunu görsün
    save_to_memory(final_text_for_ai, final_summary, speakers_log, file_path, stress_score)

def callback(ch, method, properties, body):
    try:
        job = json.loads(body)
        print(f" [x] Görev Alındı: {job.get('job_id', 'Unknown')}", flush=True)
        
        file_path = job['file_path']
        
        if os.path.exists(file_path):
            process_audio_job(file_path)
            
            jobs_processed.inc()
            print("✅ Görev Başarıyla Tamamlandı", flush=True)
            
        else:
            print(f"❌ Dosya bulunamadı: {file_path}", flush=True)
            jobs_failed.inc()

    except Exception as e:
        print(f"❌ İşlem sırasında genel hata: {e}", flush=True)
        jobs_failed.inc()

    ch.basic_ack(delivery_tag=method.delivery_tag)

channel.basic_qos(prefetch_count=1)
channel.basic_consume(queue='task_queue', on_message_callback=callback)

try:
    channel.start_consuming()
except KeyboardInterrupt:
    print('Worker durduruluyor...')
    connection.close()