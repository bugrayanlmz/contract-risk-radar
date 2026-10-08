FROM node:22-bookworm-slim
WORKDIR /workspace/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--port", "5173"]
