FROM oven/bun:1.1.0-alpine AS frontend-builder
WORKDIR /app
COPY frontend/package.json frontend/bun.lock ./
RUN bun install
COPY frontend/ .
RUN apk add --no-cache nodejs npm
# Set build-time environment variables for Next.js
ENV NEXT_PUBLIC_BACKEND_URL=https://ws2.fly.dev
ENV NEXT_PUBLIC_CENTRIFUGO_WS_URL=wss://ws2.fly.dev/centrifugo/connection/websocket
RUN npm run build

FROM node:20-alpine

RUN apk add --no-cache redis supervisor wget curl bash nginx

RUN wget https://github.com/centrifugal/centrifugo/releases/download/v5.4.0/centrifugo_5.4.0_linux_amd64.tar.gz \
    && tar -xzf centrifugo_5.4.0_linux_amd64.tar.gz \
    && mv centrifugo /usr/local/bin/ \
    && rm centrifugo_5.4.0_linux_amd64.tar.gz

# Install global dependencies and Bun
RUN npm install -g tsx
RUN curl -fsSL https://bun.sh/install | bash
ENV PATH="/root/.bun/bin:$PATH"

WORKDIR /app

# Copy and install backend dependencies
COPY backend/package.json ./backend/
RUN cd backend && npm install

# Copy backend source
COPY backend/ ./backend/
COPY config.json ./

# Copy built frontend
COPY --from=frontend-builder /app/.next ./frontend/.next
COPY --from=frontend-builder /app/public ./frontend/public
COPY --from=frontend-builder /app/package.json ./frontend/
COPY --from=frontend-builder /app/node_modules ./frontend/node_modules

# Create nginx config
RUN mkdir -p /etc/nginx/http.d
COPY <<EOF /etc/nginx/http.d/default.conf
map \$http_upgrade \$connection_upgrade {
    default upgrade;
    '' close;
}

upstream frontend {
    server 127.0.0.1:3001;
}

upstream backend {
    server 127.0.0.1:8787;
}

upstream centrifugo {
    server 127.0.0.1:8000;
}

server {
    listen 3000;
    server_name _;

    # Frontend (default)
    location / {
        proxy_pass http://frontend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_cache_bypass \$http_upgrade;
    }

    # Backend API
    location /api/ {
        proxy_pass http://backend/api/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # Centrifugo WebSocket and API
    location /centrifugo/ {
        proxy_pass http://centrifugo/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \$connection_upgrade;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_cache_bypass \$http_upgrade;
        proxy_read_timeout 86400;
    }
}
EOF

# Create supervisor config
RUN mkdir -p /etc/supervisor/conf.d

# Supervisor configuration
COPY <<EOF /etc/supervisor/conf.d/supervisord.conf
[supervisord]
nodaemon=true
user=root
logfile=/dev/stdout
logfile_maxbytes=0
pidfile=/var/run/supervisord.pid

[program:nginx]
command=nginx -g "daemon off;"
autostart=true
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0

[program:redis]
command=redis-server --appendonly yes --dir /data
autostart=true
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0

[program:centrifugo]
command=centrifugo --config=/app/config.json --engine=redis --redis_address=localhost:6379
autostart=true
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0

[program:backend]
command=tsx /app/backend/index.ts
directory=/app
autostart=true
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0

[program:frontend]
command=bun start
directory=/app/frontend
autostart=true
autorestart=true
environment=NODE_ENV=production,PORT=3001,HOSTNAME=0.0.0.0
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
EOF

RUN mkdir -p /data

# Set environment variables
ENV NODE_ENV=production
ENV PORT=8787
ENV CENTRIFUGO_HTTP_URL=http://localhost:8000

EXPOSE 3000 8787 8000 6379

# Start supervisor
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
