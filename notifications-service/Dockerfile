FROM node:20-alpine
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
WORKDIR /app
COPY package*.json ./
RUN npm install --omit=dev
COPY app.js ./
USER appuser
EXPOSE 4002
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD wget -qO- http://localhost:4002/healthz || exit 1
CMD ["node", "app.js"]
