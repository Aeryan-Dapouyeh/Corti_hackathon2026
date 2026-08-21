from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from Utils import (
    extractFacts,
    extractCodes,
    generate_patient_timeline,
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class JournalRequest(BaseModel):
    journal: str


@app.get("/")
def root():
    return {"status": "Corti backend running"}


@app.post("/api/extract-facts")
def extract_facts_endpoint(request: JournalRequest):

    df = extractFacts(request.journal)

    return {
        "facts": df.to_dict(orient="records")
    }


@app.post("/api/extract-codes")
def extract_codes_endpoint(request: JournalRequest):

    df = extractCodes(request.journal)

    return {
        "codes": df.to_dict(orient="records")
    }


@app.get("/api/timeline")
def timeline():

    df = generate_patient_timeline(data_dir="Data")

    return {
        "timeline": df.to_dict(orient="records")
    }