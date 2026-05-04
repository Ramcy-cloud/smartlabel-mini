# Utilisation d'une image Python légère
FROM python:3.10-slim

# Définition du répertoire de travail dans le conteneur
WORKDIR /app

# Copie du fichier des dépendances
COPY requirements.txt .

# Installation des dépendances (FastAPI, Transformers, PyTorch, etc.)
RUN pip install --no-cache-dir -r requirements.txt

# Copie du reste du code source
COPY ./app ./app

# Exposition du port sur lequel FastAPI va tourner
EXPOSE 8000

# Commande pour démarrer le serveur
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]