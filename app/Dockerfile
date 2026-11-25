FROM node:20-alpine

WORKDIR /usr/src/app

# Pehle sirf package files copy karo taake Docker layer cache kaam kare
COPY package*.json ./
RUN npm ci --omit=dev && npm cache clean --force

COPY server.js ./
COPY public ./public

# Non-root user (node image mein pehle se maujood hai)
USER node

ENV PORT=3000
EXPOSE 3000

CMD ["node", "server.js"]
