# SmartLabel-Mini — trier automatiquement un texte dans les catégories de votre choix

Ce projet sert à **ranger un texte dans une catégorie que vous choisissez vous-même** (par exemple « joie », « colère », « tristesse », « neutre »), grâce à une intelligence artificielle, sans avoir à lui apprendre ces catégories au préalable.

![Démonstration de SmartLabel-Mini](./image_99b8db.png)

---

## À quoi ça sert

Trier des textes à la main prend du temps : lire chaque message client, chaque avis ou chaque document, puis décider dans quelle « case » il va.

SmartLabel-Mini fait ce tri à votre place. Vous lui donnez :

1. un **texte**, par exemple : « Je n'en reviens pas, l'attente était interminable et la commande est arrivée complètement abîmée. C'est inacceptable. » ;
2. une **liste de catégories** possibles, séparées par des virgules, par exemple : `joie, colère, tristesse, neutre`.

L'application répond avec **la catégorie la plus probable** et un **niveau de confiance** (un pourcentage qui indique à quel point l'IA est sûre de son choix).

Le point fort : **vous pouvez changer les catégories à tout moment**. Aujourd'hui des émotions, demain `livraison, facturation, panne technique` pour trier des demandes au service client. Il n'y a rien à reprogrammer.

Exemples d'usages possibles :

- repérer l'émotion ou l'humeur d'un message (satisfait, en colère, neutre…) ;
- orienter automatiquement des demandes de support client vers le bon service ;
- classer des documents ou des messages par thème.

---

## Comment ça marche

### L'idée : la classification « zero-shot »

D'habitude, pour qu'une IA range des textes dans des catégories, il faut d'abord l'**entraîner** : lui montrer des milliers d'exemples déjà triés pour chaque catégorie. Si on ajoute une catégorie, il faut recommencer.

La méthode utilisée ici s'appelle **zero-shot** (« zéro exemple ») : l'IA n'a besoin d'**aucun exemple** pour vos catégories. Elle a déjà appris, de façon générale, à juger si une phrase « va avec » une autre. Pour chaque catégorie proposée, elle se demande en quelque sorte : « Ce texte parle-t-il de *colère* ? de *joie* ? … », puis garde la catégorie qui convient le mieux.

C'est comme demander à quelqu'un qui maîtrise bien la langue de ranger des lettres dans des boîtes étiquetées : il n'a pas besoin de formation spéciale, il lit l'étiquette et le contenu, et décide.

### Les étapes

1. Vous saisissez le texte et les catégories dans la page web.
2. La page envoie ces informations au **serveur** (le programme qui tourne en arrière-plan).
3. Le serveur les transmet à un **modèle d'IA** : un programme qui a « appris » à comprendre le langage en lisant une très grande quantité de textes. Celui utilisé ici, `joeddav/xlm-roberta-large-xnli`, est **multilingue** : il comprend notamment le français et l'anglais.
4. Le modèle attribue un score à chaque catégorie. Le serveur renvoie la meilleure catégorie et son score.
5. La page affiche le résultat.

Le modèle tourne **sur votre propre machine**. Il est téléchargé une fois depuis **Hugging Face** (une plateforme qui partage des modèles d'IA) au premier lancement, puis gardé en mémoire pour les fois suivantes. Le texte analysé n'est envoyé à aucun service extérieur.

---

## Résultat / ce qu'on obtient

Une page web, ouverte dans votre navigateur, qui s'ouvre **directement sur l'outil** (il n'y a pas de compte ni de mot de passe), avec :

- une zone pour coller le **texte à analyser** ;
- un champ pour écrire les **catégories candidates**, séparées par des virgules (par défaut : `joie, colère, tristesse, neutre`) ;
- un bouton **« Soumettre à l'IA »** ;
- un encadré **« Résultat de la prédiction »** qui affiche la catégorie retenue et le niveau de confiance. Sur la capture d'écran ci-dessus, le message de client mécontent est classé dans la catégorie `TRISTESSE`, avec un niveau de confiance de 79,80 %.

---

## Pour les développeurs

### Architecture

L'application est composée de deux services, conteneurisés avec Docker :

- **Frontend** : React 19 + Vite, avec la bibliothèque de composants Ant Design. L'API est appelée via `axios`.
- **Backend** : FastAPI (Python), servi par Uvicorn.
- **Modèle d'IA** : `joeddav/xlm-roberta-large-xnli`, chargé avec le `pipeline("zero-shot-classification")` de la bibliothèque Transformers (Hugging Face) et exécuté avec PyTorch. Le modèle est chargé une seule fois au démarrage du backend.
- **Docker / Docker Compose** : un environnement d'exécution identique sur toutes les machines. Un volume Docker (`huggingface_cache`) conserve le modèle téléchargé entre deux démarrages.

### API

| Méthode | Route | Rôle |
|---|---|---|
| `POST` | `/api/predict` | Classe un texte parmi les catégories fournies |

Exemple de requête :

```json
{
  "text": "Le client est vraiment furieux à cause du retard de livraison.",
  "candidate_labels": ["joie", "colère", "tristesse", "neutre"]
}
```

Format de la réponse :

```json
{
  "text": "…",
  "predicted_label": "…",
  "confidence_score": 0.0
}
```

`confidence_score` est le score de la catégorie retenue, entre 0 et 1, arrondi à 4 décimales. La documentation interactive de l'API (générée par FastAPI) est disponible sur **http://localhost:8000/docs**.

### Lancement avec Docker (recommandé)

Prérequis : [Docker Desktop](https://www.docker.com/products/docker-desktop/) installé et démarré.

#### 1. Cloner le projet

```bash
git clone https://github.com/Ramcy-cloud/smartlabel-mini.git
cd smartlabel-mini
```

#### 2. Construire et démarrer les conteneurs

En arrière-plan (mode « détaché ») :

```bash
docker compose up -d --build
```

Le premier lancement prend plusieurs minutes : Docker télécharge les images de base et les dépendances, puis le backend télécharge le modèle d'IA.

#### 3. Ouvrir l'interface

- Interface : **http://localhost:5175/** (le port 5175 de la machine est relié au port 5173 du conteneur)
- API : **http://localhost:8000**

Le frontend appelle l'API à l'adresse `http://127.0.0.1:8000/api` (définie dans `frontend/src/services/api.js`).

#### 4. Commandes utiles

- Suivre les journaux (logs) en temps réel :

  ```bash
  docker compose logs -f
  ```

- Arrêter l'application :

  ```bash
  docker compose down
  ```

- Arrêter l'application et supprimer le cache du modèle d'IA (il sera retéléchargé au prochain lancement) :

  ```bash
  docker compose down -v
  ```

### Lancement sans Docker

Backend (Python 3.10 ou plus récent ; l'image Docker utilise Python 3.10) :

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Frontend (Node.js et npm) :

```bash
cd frontend
npm install
npm run dev
```

L'interface est alors disponible sur **http://localhost:5173**.

### Configuration : origines autorisées (CORS)

Par sécurité, le navigateur n'autorise une page web à interroger l'API que si l'adresse de cette page figure dans la liste des **origines autorisées**. Cette liste se règle avec la variable d'environnement `ALLOWED_ORIGINS` : des adresses séparées par des virgules, les espaces sont ignorés.

- **Valeur par défaut** (variable absente) : `http://localhost:5175,http://localhost:5173`, c'est-à-dire l'interface lancée avec Docker et celle lancée avec `npm run dev`. Le fonctionnement local ne change donc pas.
- **Exemple pour un déploiement** : `ALLOWED_ORIGINS=https://app.example.com,https://admin.example.com`
- `*` (« tout le monde ») est **refusé** : le backend ne démarre pas si cette valeur est présente.
- Avec Docker, `docker-compose.yml` transmet la variable au backend ; vous pouvez la définir dans un fichier `.env` placé à la racine (voir `.env.example`). Sans Docker, définissez-la avant `uvicorn`, par exemple `ALLOWED_ORIGINS=https://app.example.com uvicorn app.main:app` (Linux/macOS).
- Seules les méthodes `GET` et `POST` et l'en-tête `Content-Type` sont autorisés, sans cookies ni identifiants.

### Tests du backend

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest
```

Les tests vérifient la configuration CORS. Le vrai modèle d'IA n'est pas chargé : il est remplacé par un faux.

### Structure du projet

```
smartlabel-mini/
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── requirements-dev.txt      # Dépendances de test (pytest)
│   ├── tests/                    # Tests (CORS)
│   └── app/
│       ├── main.py               # Application FastAPI, CORS (ALLOWED_ORIGINS), préfixe /api
│       ├── api/routes.py         # Route POST /predict
│       ├── models/schemas.py     # Formats de requête et de réponse (Pydantic)
│       └── services/ai_service.py # Chargement du modèle et prédiction
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── index.html
│   ├── vite.config.js
│   ├── public/                   # Icônes
│   └── src/
│       ├── App.jsx               # Page principale (saisie + résultat)
│       ├── services/api.js       # Appel à l'API
│       └── *.css                 # Styles
├── docker-compose.yml
├── .env.example                  # Variables d'environnement (ALLOWED_ORIGINS)
├── image_99b8db.png              # Capture d'écran
└── README.md
```

### Limites connues

- L'application n'a **aucune authentification** : l'écran de connexion factice a été retiré, car il ne protégeait rien. Quiconque peut joindre le frontend ou l'API peut l'utiliser ; ne l'exposez pas sur Internet sans protection (par exemple un proxy avec authentification).
- Le frontend Docker tourne avec le serveur de développement de Vite (`npm run dev`), pas avec une version compilée pour la production.

---

*Projet développé par Ramcy-cloud.*
