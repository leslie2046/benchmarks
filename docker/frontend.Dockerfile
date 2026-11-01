FROM node:22-alpine AS build
WORKDIR /app
RUN corepack enable && corepack prepare pnpm@10.28.2 --activate
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm run build

FROM nginx:1.29-alpine
RUN apk add --no-cache apache2-utils
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --chmod=755 docker/25-admin-auth.sh /docker-entrypoint.d/25-admin-auth.sh
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
