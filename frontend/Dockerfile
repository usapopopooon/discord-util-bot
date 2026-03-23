FROM node:22-alpine AS base

WORKDIR /app

# Install dependencies
COPY package.json package-lock.json ./
RUN npm ci

# Copy source
COPY . .

# Build
RUN npm run build

# Production image
FROM node:22-alpine AS production

WORKDIR /app

# standalone output is nested under the package directory name
COPY --from=base /app/.next/standalone/frontend ./
COPY --from=base /app/.next/static ./.next/static

ENV NODE_ENV=production
ENV HOSTNAME=0.0.0.0

EXPOSE 3000

CMD ["node", "server.js"]

# Development image
FROM base AS dev

EXPOSE 3000

CMD ["npm", "run", "dev", "--", "--port", "3000"]
