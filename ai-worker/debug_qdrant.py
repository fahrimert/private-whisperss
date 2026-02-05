import qdrant_client
from qdrant_client import QdrantClient

print(f"📦 Kütüphane Yolu: {qdrant_client.__file__}")
print(f"ℹ️ Sürüm: {qdrant_client.__version__}")

if hasattr(QdrantClient, 'search'):
    print("✅ BAŞARILI: 'search' metodu bulundu!")
else:
    print("❌ HATA: 'search' metodu HALA YOK!")
    print("Mevcut Metotlar:", [m for m in dir(QdrantClient) if 'search' in m or 'query' in m])