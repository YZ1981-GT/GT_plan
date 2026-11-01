FROM node:20-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build
RUN npm run bundle:check

FROM nginx:1.27-alpine AS runtime-base
ENV GT_BACKEND_HOST=backend \
    GT_BACKEND_PORT=9980 \
    NGINX_ENVSUBST_FILTER=^GT_
COPY docker/default.conf.template /etc/nginx/templates/default.conf.template
EXPOSE 80
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1/frontend-health || exit 1

FROM runtime-base AS runtime-prebuilt-smoke
COPY dist /usr/share/nginx/html

FROM runtime-base AS runtime
COPY --from=build /app/dist /usr/share/nginx/html
