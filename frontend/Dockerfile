# ── Build Stage ─────────────────────────────────────────────────────────────
FROM node:26.8-alpine AS builder

WORKDIR /app

# Copy dependency manifests
COPY package*.json ./

# Install dependencies cleanly
RUN npm ci

# Copy frontend source files
COPY . .

# Build optimized production bundle
RUN npm run build

# ── Runtime Stage (Nginx Reverse Proxy & Static Host) ───────────────────────
# nginx-unprivileged: the official nginx image can't bind port 80 as a
# non-root user (that needs CAP_NET_BIND_SERVICE / root); this image is
# built to run as the non-root "nginx" user on port 8080 instead, with the
# handful of runtime directories nginx needs to write to (cache, pid,
# temp) already owned by that user — no manual chown list required.
FROM nginxinc/nginx-unprivileged:1.31.5-alpine

USER root

# Remove default nginx static files
RUN rm -rf /usr/share/nginx/html/*

# Copy built static assets and config, owned by the non-root nginx user
COPY --chown=nginx:nginx --from=builder /app/dist /usr/share/nginx/html
COPY --chown=nginx:nginx nginx.conf /etc/nginx/conf.d/default.conf

USER nginx

EXPOSE 8080

# Health check verifying Nginx and backend connectivity
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/health || exit 1

CMD ["nginx", "-g", "daemon off;"]
