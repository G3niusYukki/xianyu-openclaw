FROM node:20-alpine AS build
WORKDIR /app
ARG VITE_NODE_API_URL=/api
ARG VITE_PY_API_URL=/py
ENV VITE_NODE_API_URL=$VITE_NODE_API_URL
ENV VITE_PY_API_URL=$VITE_PY_API_URL
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
