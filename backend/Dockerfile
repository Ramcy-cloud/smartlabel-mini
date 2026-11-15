# Utilisation d'une image Python légère.
# Python 3.12 (et non 3.10, en fin de vie depuis le 1er octobre 2026 : plus aucun correctif de sécurité).
FROM python:3.12-slim

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

# Dossiers écrits par l'application : les données (jeux de catégories, modèles entraînés) et le
# cache du modèle téléchargé. Tous deux reçoivent un volume : le cache DOIT exister et appartenir
# à l'utilisateur ici, sinon Docker crée son point de montage en root et le téléchargement du
# modèle échoue (l'appartenance n'est pas héritée de /home/app).
# Voir le README si les écritures du dossier de données sont refusées.
RUN mkdir -p /app/data /home/app/.cache/huggingface && chown -R 10001:10001 /app /home/app

# Le cache Hugging Face est écrit dans le dossier personnel de l'utilisateur
ENV HOME=/home/app
USER 10001

# Exposition du port sur lequel FastAPI va tourner
EXPOSE 8000

# Commande pour démarrer le serveur
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
