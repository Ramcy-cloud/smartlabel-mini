# Utilisation d'une image Python légère
FROM python:3.10-slim

# Compte sans privilège : un conteneur qui tourne en root donne des droits root sur l'hôte
# si un attaquant sort du conteneur. Créé avant l'installation pour profiter du cache de couches.
RUN useradd --create-home --uid 10001 app

# Définition du répertoire de travail dans le conteneur
WORKDIR /app

# Copie du fichier des dépendances
COPY requirements.txt .

# Installation des dépendances (FastAPI, Transformers, PyTorch, etc.)
RUN pip install --no-cache-dir -r requirements.txt

# Copie du reste du code source
COPY ./app ./app

# Dossier des données (jeux de catégories enregistrés, modèles entraînés), écrit par l'application.
# Il est habituellement monté depuis l'hôte : voir le README si les écritures sont refusées.
RUN mkdir -p /app/data && chown -R 10001:10001 /app

# Le cache Hugging Face est écrit dans le dossier personnel de l'utilisateur
ENV HOME=/home/app
USER 10001

# Exposition du port sur lequel FastAPI va tourner
EXPOSE 8000

# Commande pour démarrer le serveur
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
