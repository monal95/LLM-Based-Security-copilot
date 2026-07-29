import chromadb

# Change the path if your ChromaDB is stored somewhere else
client = chromadb.PersistentClient(
    path=r"D:\Project\SOC_Analyst\embeddings\chroma_db"
)

collection = client.get_collection("secure_rag_chunks")

result = collection.get(limit=1)

print(result["metadatas"][0])