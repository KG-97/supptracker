FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . ./
RUN npm run build

FROM nginx:stable-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY frontend/wait-for-health.sh /usr/local/bin/wait-for-health.sh
RUN chmod +x /usr/local/bin/wait-for-health.sh
EXPOSE 80
# Wait for backend health then start nginx
CMD ["/bin/sh", "-c", "/usr/local/bin/wait-for-health.sh backend 8000 /api/health 30 && exec nginx -g 'daemon off;'"]
