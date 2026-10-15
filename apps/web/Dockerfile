# Builder: compiles the SPA with pinned Node 22.
FROM node:22.11.0-alpine AS builder
WORKDIR /build
RUN apk add --no-cache tini
# Install deps first, then source: faster rebuilds.
COPY package.json package-lock.json* ./
# Allow the build to proceed when the lockfile is absent (first bootstrap). CI commits one.
RUN if [ -f package-lock.json ]; then npm ci; else npm install --no-audit --no-fund; fi
COPY . .
RUN npm run build

# Runtime: nginx with the compiled assets, non-root, healthcheck.
FROM nginx:1.27.2-alpine AS runtime
RUN apk add --no-cache curl \
    && addgroup -S -g 1001 webapp \
    && adduser  -S -u 1001 -G webapp webapp
COPY --from=builder /build/dist /usr/share/nginx/html
COPY --from=builder /build/public/brand /usr/share/nginx/html/brand
RUN chown -R webapp:webapp /usr/share/nginx/html /var/cache/nginx /var/run \
    && chmod -R u=rwX,g=rX /usr/share/nginx/html
USER webapp
EXPOSE 80
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -fsS http://127.0.0.1/healthz || exit 1
CMD ["nginx", "-g", "daemon off;"]
