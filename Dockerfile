FROM node:18-alpine AS runner

WORKDIR /app

COPY  index.js package.json ./

RUN npm install

EXPOSE 8080

ENV PORT=8080

CMD ["npm", "start"]
