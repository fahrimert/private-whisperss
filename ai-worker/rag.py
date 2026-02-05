import sys
import requests
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

QDRANT_HOST = "qdrant"
OLLAMA_HOST = "http://ollama:11434"

print("🧠 Modeller ve Hafıza Yükleniyor...", flush=True)

client = QdrantClient(host=QDRANT_HOST, port=6333)
embedder = SentenceTransformer('all-MiniLM-L6-v2')

def chat_with_memory(question):
    print(f"\n🔎 Soru: {question}")
    
    vector = embedder.encode(question).tolist()
    
    search_result = client.search(
        collection_name="audio_memory",
        query_vector=vector,
        limit=3
    )
    
    if not search_result:
        print("❌ Hafızada bu konuyla ilgili kayıt yok.")
        return

    context_texts = []
    print(f"📚 Bulunan Alakalı Kayıtlar:")
    for hit in search_result:
        summary = hit.payload.get("summary", "")
        file_path = hit.payload.get("file_path", "Bilinmeyen")
        print(f"  - [{hit.score:.2f}] 📂 {file_path}")
        context_texts.append(summary)
    
    context_block = "\n".join(context_texts)
    
    prompt = f"""
    You are a helpful AI assistant. Use the following CONTEXT (summaries of audio files) to answer the QUESTION.
    If the answer is not in the context, say "I don't have enough information in the audio files."
    
    CONTEXT:
    {context_block}
    
    QUESTION: 
    {question}
    
    ANSWER:
    """
    
    print("\n🤔 Llama 3 Düşünüyor...", flush=True)
    try:
        response = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": "llama3",
                "prompt": prompt,
                "stream": False
            }
        )
        
        if response.status_code == 200:
            answer = response.json()['response']
            print(f"\n🤖 CEVAP:\n{'-'*20}\n{answer}\n{'-'*20}")
        else:
            print(f"❌ Ollama Hatası: {response.text}")
            
    except Exception as e:
        print(f"❌ Bağlantı Hatası: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        user_question = " ".join(sys.argv[1:])
        chat_with_memory(user_question)
    else:
        print("Kullanım: python rag.py 'Sorunuzu buraya yazın'")