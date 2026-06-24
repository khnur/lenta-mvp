# syntax=docker/dockerfile:1

# ---- Stage 1: build the static site ----------------------------------------
FROM node:22-alpine AS build
WORKDIR /app

# VITE_API_URL is baked into the static bundle at build time.
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=${VITE_API_URL}

# Install deps from the committed lockfile for reproducible builds.
COPY package.json package-lock.json ./
RUN npm ci

# Build.
COPY . .
RUN npm run build

# ---- Stage 2: serve the static bundle --------------------------------------
FROM node:22-alpine AS runtime
WORKDIR /app

RUN npm i -g serve

COPY --from=build /app/dist ./dist

ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "serve -s dist -l ${PORT:-8080}"]
