import pika
import os
import time

print("⏳ RabbitMQ bekleniyor...")
time.sleep(10) 

rabbit_url = os.environ.get('RABBITMQ_URL', 'amqp://guest:guest@rabbitmq:5672/')
params = pika.URLParameters(rabbit_url)
connection = pika.BlockingConnection(params)
channel = connection.channel()

channel.queue_declare(queue='task_queue', durable=True)

print(' [*] Worker Hazır! Mesaj bekleniyor. Çıkmak için CTRL+C')

def callback(ch, method, properties, body):
    print(f" [x] Mesaj alındı: {body}")
    print(" [x] İşlem tamamlandı")
    ch.basic_ack(delivery_tag=method.delivery_tag)

channel.basic_qos(prefetch_count=1)
channel.basic_consume(queue='task_queue', on_message_callback=callback)

channel.start_consuming()
