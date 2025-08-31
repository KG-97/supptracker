FROM python:3.12

WORKDIR /app

# Copy requirements and install Python deps
COPY requirements.txt ./requirements.txt
RUN python -m pip install --upgrade pip setuptools wheel && \
	pip install --no-cache-dir --prefer-binary -r requirements.txt

# Copy app and data
COPY app.py ./app.py

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
