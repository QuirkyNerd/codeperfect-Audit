import chromadb

client = chromadb.PersistentClient(path="chroma_store")

print("ICD docs:", client.get_collection("icd10_codes").count())
print("CPT docs:", client.get_collection("cpt_codes").count())
print("Guidelines:", client.get_collection("coding_guidelines").count())