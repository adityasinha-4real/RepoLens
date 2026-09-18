# RepoLens web UI (Next.js standalone output).
FROM node:25-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:25-alpine AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:25-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
RUN addgroup -S repolens && adduser -S repolens -G repolens
COPY --from=build --chown=repolens:repolens /app/.next/standalone ./
COPY --from=build --chown=repolens:repolens /app/.next/static ./.next/static
USER repolens
EXPOSE 3000
# REPOLENS_API_URL (backend base URL) is read at runtime by the /api route handlers.
CMD ["node", "server.js"]
