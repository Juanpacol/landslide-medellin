FROM node:22-alpine

WORKDIR /app

# pnpm vía corepack (versión fijada por el campo packageManager si existe).
RUN corepack enable

# El proxy /api → backend se hornea en build (Next evalúa rewrites en build time).
# Dentro de la red Docker el backend responde por su nombre de servicio.
ARG BACKEND_URL=http://backend:8000
ENV BACKEND_URL=$BACKEND_URL \
    NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production

# Instalar deps primero para cachear capas. --ignore-scripts evita compilar sharp
# (no se usa: images.unoptimized=true) y binarios nativos opcionales.
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile --ignore-scripts

COPY . .

RUN pnpm build

EXPOSE 3000

CMD ["pnpm", "start"]
