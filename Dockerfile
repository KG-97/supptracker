# Multi-stage build: Build React frontend first
FROM node:20-alpine AS frontend-build
WORKDIR /app

# Install Node.js dependencies
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

# Copy source code and build frontend
COPY . ./
RUN npm run build

# Production stage: Python FastAPI backend
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt ./
RUN python -m pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copy backend code and data
COPY api ./api
COPY data ./data

# Copy built frontend from the build stage
COPY --from=frontend-build /app/dist ./frontend_dist

# Expose port 8000 for FastAPI
EXPOSE 8000

# Run FastAPI with uvicorn
CMD ["uvicorn", "api.risk_api:app", "--host", "0.0.0.0", "--port", "8000"]
