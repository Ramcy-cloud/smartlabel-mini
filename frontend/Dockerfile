# Utilisation d'une image Node.js légère
FROM node:20-alpine

# Définition du répertoire de travail
WORKDIR /app

# Copie des fichiers de configuration NPM
COPY package.json package-lock.json* ./

# Installation des dépendances (React, Vite, Ant Design, Axios)
RUN npm install

# Copie du reste du code source
COPY . .

# Exposition du port par défaut de Vite
EXPOSE 5173

# Commande pour démarrer Vite en exposant le réseau local
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]