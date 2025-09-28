FROM python:3.12

WORKDIR /app

# Copy requirements and install Python deps
COPY requirements.txt ./requirements.txt
RUN python -m pip install --upgrade pip setuptools wheel && \
	pip install --no-cache-dir --prefer-binary -r requirements.txt

# Copy app and data
# Copy API module
COPY api ./api
COPY data ./data

EXPOSE 8000

# Run the risk API
CMD ["uvicorn", "api.risk_api:app", "--host", "0.0.0.0", "--port", "8000"]
