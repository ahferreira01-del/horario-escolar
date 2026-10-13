FROM node:22-alpine AS build
WORKDIR /app
ARG API_BACKEND_URL=http://api:8000
ENV API_BACKEND_URL=$API_BACKEND_URL
COPY package*.json ./
RUN npm install --no-audit --no-fund
COPY . .
RUN npm run build
FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
EXPOSE 3000
CMD ["node", "server.js"]
