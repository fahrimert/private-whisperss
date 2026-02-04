import pika
import os
import time
import json
from transformers import pipeline

print("🤖 Modeller yükleniyor...", flush=True)

transcriber = pipeline("automatic-speech-recognition", model="openai/whisper-tiny")
summarizer = pipeline("summarization", model="sshleifer/distilbart-cnn-6-6")

print("✅ Modeller Hazır!", flush=True)

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

def callback(ch, method, properties, body):
    job = json.loads(body)
    print(f" [x] Görev Alındı: {job['job_id']}", flush=True)
    
    file_path = job['file_path']
    
    if os.path.exists(file_path):
        print(f"🎤 Ses işleniyor: {file_path}", flush=True)
        
        # --- DEĞİŞTİRDİĞİMİZ KISIM BURASI ---
        # Uzun dosyalar için chunk_length_s ve return_timestamps ekledik
        result = transcriber(
            file_path, 
            return_timestamps=True, 
            chunk_length_s=30
        )
        # ------------------------------------
        
        text = result["text"]
        print(f"📝 Transkript: {text}", flush=True)
        
        if len(text) > 50:
            summary = summarizer(text, max_length=60, min_length=10)
            print(f"💡 Özet: {summary[0]['summary_text']}", flush=True)
        else:
            print("💡 Özet: Metin çok kısa.", flush=True)
    else:
        print(f"❌ Dosya bulunamadı: {file_path}", flush=True)

    ch.basic_ack(delivery_tag=method.delivery_tag)

channel.basic_qos(prefetch_count=1)
channel.basic_consume(queue='task_queue', on_message_callback=callback)
channel.start_consuming()