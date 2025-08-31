FROM python:3.12-slim

WORKDIR /app

# Install runtime deps
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy app and data
COPY app.py ./app.py
COPY data ./data

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
