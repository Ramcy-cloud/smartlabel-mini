# ---------------------------------------------------------------- construction
FROM node:20-alpine AS build

WORKDIR /app

# npm ci (et non npm install) : installe exactement les versions du verrou,
# celles qui ont été auditées et testées. Pas de dérive silencieuse à la construction.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Adresse du backend, figée dans les fichiers construits (Vite remplace import.meta.env à la construction)
ARG VITE_API_BASE_URL
RUN npm run build

# ---------------------------------------------------------------- service
# Fichiers statiques servis par nginx, sous un utilisateur sans privilège (image « unprivileged »,
# qui écoute sur 8080). Le serveur de développement de Vite n'est pas fait pour être exposé :
# il sert les sources, ne durcit rien et a eu des failles de lecture de fichiers.
FROM nginxinc/nginx-unprivileged:stable-alpine

# Origine du backend autorisée par la politique de sécurité du contenu (voir nginx.conf.template)
ENV API_ORIGIN="http://127.0.0.1:8000"

COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
  CMD wget --quiet --spider http://127.0.0.1:8080/ || exit 1
