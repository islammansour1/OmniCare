# syntax=docker/dockerfile:1

# ---- build stage ----
FROM node:20-alpine AS build

WORKDIR /app

# Install dependencies. package-lock.json is committed, so use `npm ci` for a
# clean, reproducible install (devDependencies are required to build).
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

# Copy the rest of the source and build the production bundle into `dist/`.
COPY . .
RUN npm run build

# ---- serve stage ----
FROM nginx:alpine

# SPA + API proxy config. `/api/` (including the `/api/v1/voice` WebSocket)
# is proxied to the backend service; everything else falls back to index.html.
COPY <<'EOF' /etc/nginx/conf.d/default.conf
server {
    listen 80;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    # Single-page application fallback.
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Proxy REST + voice WebSocket to the backend service.
    location /api/ {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $http_host;
        proxy_buffering off;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
}
EOF

# Serve the built SPA.
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
