import pika
import os
import time
import json
from transformers import pipeline

print("🤖 Modeller yükleniyor (GPU Modu)...", flush=True)

transcriber = pipeline("automatic-speech-recognition", model="openai/whisper-small", device=0)
summarizer = pipeline("summarization", model="sshleifer/distilbart-cnn-6-6", device=0)
print("✅ Modeller GPU'ya Yüklendi!", flush=True)

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
    try:
        job = json.loads(body)
        print(f" [x] Görev Alındı: {job.get('job_id', 'Unknown')}", flush=True)
        
        file_path = job['file_path']
        
        if os.path.exists(file_path):
            print(f"🎤 Ses işleniyor: {file_path}", flush=True)
            
            result = transcriber(
                file_path, 
                return_timestamps=True, 
                # chunk_length_s=30,
                generate_kwargs={
                    "language": "english", 
                    "task": "transcribe"
                }
            )
            
            text = result["text"]
            print(f"📝 Transkript: {text}", flush=True)
            
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

            print(f"💡 Özet: {final_summary}", flush=True)
            
        else:
            print(f"❌ Dosya bulunamadı: {file_path}", flush=True)

    except Exception as e:
        print(f"❌ İşlem sırasında hata: {e}", flush=True)

    ch.basic_ack(delivery_tag=method.delivery_tag)

channel.basic_qos(prefetch_count=1)
channel.basic_consume(queue='task_queue', on_message_callback=callback)

try:
    channel.start_consuming()
except KeyboardInterrupt:
    print('Worker durduruluyor...')
    connection.close()