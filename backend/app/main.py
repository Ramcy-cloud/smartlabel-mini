from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router

app = FastAPI(title="SmartLabel-Mini API", description="API IA pour la labellisation de données")

# Autoriser React (qui tournera sur un autre port) à faire des requêtes
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # À sécuriser en production, mais parfait pour le dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# On connecte nos routes sous le préfixe /api
app.include_router(router, prefix="/api")