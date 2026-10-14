# Frontend image for Cloud Run: the Vite build, served by nginx, which forwards /api to the backend.
# Build from frontend/:  docker build -t codguard-web .
# Run:                   docker run -p 8080:8080 -e API_ORIGIN=https://<backend host> codguard-web

FROM node:22-alpine AS build
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
# pnpm at the version pinned in package.json ("packageManager").
RUN npm install -g "pnpm@$(node -p "require('./package.json').packageManager.split('@')[1]")" \
    && pnpm install --frozen-lockfile
COPY . .
RUN pnpm build

# Runs as an unprivileged user and renders /etc/nginx/templates/*.template from the environment at start.
FROM nginxinc/nginx-unprivileged:1.28-alpine
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
# Cloud Run sets PORT. API_ORIGIN (scheme and host of the backend, no path) is required.
ENV PORT=8080
EXPOSE 8080
