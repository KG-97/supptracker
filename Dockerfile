# Multi-stage build: build frontend with Node, then package with Python+nginx
FROM node:20-alpine AS build-frontend
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

# Install python deps
COPY requirements.txt ./requirements.txt
RUN python -m pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copy backend app and data
COPY api ./api
COPY data ./data

# Copy built frontend from previous stage into nginx default html
COPY --from=build-frontend /app/dist /usr/share/nginx/html

# Install nginx and curl (curl used by start.sh for health checks)
RUN apt-get update && apt-get install -y nginx curl && rm -rf /var/lib/apt/lists/*

# Remove default site and default conf to avoid duplicate/conflicting server blocks
RUN rm -f /etc/nginx/sites-enabled/default || true
RUN rm -f /etc/nginx/conf.d/default.conf || true

# Copy nginx site config and start script
COPY docker/supptracker.conf /etc/nginx/conf.d/supptracker.conf
COPY docker/start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 80 8000

CMD ["/start.sh"]
FROM node:20-alpine AS frontend-build
WORKDIR /app

# install node deps and build the frontend (Vite)
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . ./
RUN npm run build

FROM python:3.12-slim

# install nginx and python deps
RUN apt-get update && apt-get install -y --no-install-recommends nginx ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN python -m pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# copy backend code and data
COPY api ./api
COPY data ./data

# copy built frontend into nginx html root
COPY --from=frontend-build /app/dist /usr/share/nginx/html

# nginx config and start script
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY docker/start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 80

CMD ["/start.sh"]
