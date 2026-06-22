import os
from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

# Replicate the t2v-transformers API behavior
app = FastAPI(title="T2V Transformers Mock API")

# Use the same default model as Weaviate text2vec-transformers module
MODEL_NAME = os.getenv("MODEL_NAME", "sentence-transformers/multi-qa-MiniLM-L6-cos-v1")
model = SentenceTransformer(MODEL_NAME)

class VectorizeRequest(BaseModel):
    text: str

class VectorizeResponse(BaseModel):
    text: str
    vector: list[float]

@app.get("/.well-known/ready")
def is_ready():
    return {"status": "ok"}

@app.post("/vectors")
def vectorize(req: VectorizeRequest):
    vector = model.encode(req.text).tolist()
    return VectorizeResponse(text=req.text, vector=vector)

if __name__ == "__main__":
    import uvicorn
    # t2v-transformers natively runs on 8080. If Weaviate is on 8080, we should run this on a different port.
    # The docker-compose uses a custom container named `t2v-transformers`. 
    # If we run natively, we need Weaviate to point to this mock API.
    # We will bind it to 8081.
    uvicorn.run(app, host="0.0.0.0", port=8081)
