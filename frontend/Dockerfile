# ---------- Build stage ----------
FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

# Build the Vite app. VITE_API_BASE_URL is NOT set here because the frontend
# uses relative /api paths. In Docker, nginx proxies /api → backend service.
# For local dev, vite.config.js proxy handles it.
RUN npm run build

# ---------- Production stage ----------
FROM nginx:alpine

# Custom nginx config with SPA fallback + /api proxy to backend
COPY nginx.conf /etc/nginx/conf.d/default.conf

COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
