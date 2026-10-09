from fastapi import FastAPI

from app.whatsapp.webhook import (
    router as whatsapp_router,
)


app = FastAPI(
    title="Chatbot JCF",
    description="API del chatbot empresarial JCF",
    version="1.0.0",
)


app.include_router(
    whatsapp_router
)


@app.get("/")
def root():
    return {
        "message": "Chatbot JCF API funcionando",
        "status": "ok",
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "Chatbot JCF",
    }