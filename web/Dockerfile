FROM node:20-alpine

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
EXPOSE 5173
# Dev server (hot reload); /api is proxied to VITE_API_TARGET (http://api:8000 in Compose).
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
