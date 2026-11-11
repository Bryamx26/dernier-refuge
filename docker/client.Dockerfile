# Image de développement du client (serveur Vite avec rechargement à chaud).
# Le client lit aussi shared/ (alias @shared), maps/ et assets/ à la racine du dépôt (/srv).
FROM node:22-slim
WORKDIR /srv/client
COPY client/package.json client/package-lock.json ./
RUN npm ci
COPY shared/ /srv/shared/
COPY maps/ /srv/maps/
COPY assets/ /srv/assets/
COPY client/ ./
ENV DR_REPO_ROOT=/srv
EXPOSE 5173
CMD ["npm", "run", "dev"]
