# Image de développement du client (serveur Vite avec rechargement à chaud).
FROM node:22-slim
WORKDIR /srv/client
COPY client/package.json client/package-lock.json ./
RUN npm ci
COPY client/ ./
EXPOSE 5173
CMD ["npm", "run", "dev"]
