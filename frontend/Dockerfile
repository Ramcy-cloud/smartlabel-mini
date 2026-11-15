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

# Origine de cette adresse, mise de côté pour l'étage de service : c'est elle que la politique de
# sécurité du contenu doit autoriser. La déduire ici évite d'avoir à répéter à la main, dans une
# variable d'exécution, une valeur déjà figée à la construction.
RUN node -e "const u = new URL(process.argv[1] || 'http://127.0.0.1:8000/api'); require('fs').writeFileSync('/app/api-origin', u.origin);" "$VITE_API_BASE_URL"

# ---------------------------------------------------------------- service
# Fichiers statiques servis par nginx, sous un utilisateur sans privilège (image « unprivileged »,
# qui écoute sur 8080). Le serveur de développement de Vite n'est pas fait pour être exposé :
# il sert les sources, ne durcit rien et a eu des failles de lecture de fichiers.
FROM nginxinc/nginx-unprivileged:stable-alpine

# Origine du backend autorisée par la politique de sécurité du contenu (voir nginx.conf.template).
# Déduite de VITE_API_BASE_URL au démarrage ; API_ORIGIN ne sert plus qu'à la contredire
# volontairement, et le conteneur refuse alors de démarrer (voir 15-api-origin.envsh).
COPY --from=build /app/api-origin /etc/nginx/api-origin.built

# Suffixe .envsh et non .sh : l'entrypoint de l'image nginx source ces fichiers au lieu de les
# exécuter, donc l'export est visible par 20-envsubst-on-templates.sh qui traite le modèle ensuite.
# Le chmod est explicite : cet entrypoint ignore un .envsh non exécutable avec une simple ligne de
# journal, ce qui redonnerait silencieusement une politique de sécurité incohérente. Le droit
# d'exécution ne peut donc pas dépendre de ce que le système de fichiers d'origine a su conserver.
COPY docker-entrypoint.d/15-api-origin.envsh /docker-entrypoint.d/15-api-origin.envsh
RUN chmod 0755 /docker-entrypoint.d/15-api-origin.envsh

COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
  CMD wget --quiet --spider http://127.0.0.1:8080/ || exit 1
