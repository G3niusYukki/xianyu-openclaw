FROM node:20-alpine
WORKDIR /app
RUN addgroup -S appgrp && adduser -S appusr -G appgrp
COPY package*.json ./
RUN npm ci --omit=dev
COPY src/ ./src/
RUN mkdir -p /app/data && chown -R appusr:appgrp /app
USER appusr
EXPOSE 3001
CMD ["node", "src/app.js"]
