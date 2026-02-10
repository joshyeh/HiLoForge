FROM node:20-slim AS build

WORKDIR /app
COPY package.json ./
COPY postcss.config.cjs ./
COPY tailwind.config.ts ./
COPY tsconfig.json ./
COPY vite.config.ts ./
COPY index.html ./
COPY src ./src

RUN npm install

ARG VITE_API_BASE
ENV VITE_API_BASE=${VITE_API_BASE}
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
