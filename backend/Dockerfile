FROM python:3.12-slim

WORKDIR /app

# Install runtime deps
COPY requirements.txt ./requirements.txt

# Install system build deps required for some Python packages (wheel compilation)
RUN apt-get update \
	&& apt-get install -y --no-install-recommends \
	   build-essential \
	   gcc \
	   python3-dev \
	   libyaml-dev \
	   libffi-dev \
	   libssl-dev \
	   ca-certificates \
	 && python -m pip install --upgrade pip setuptools wheel \
	 && pip install --no-cache-dir -r requirements.txt \
	 && apt-get purge -y --auto-remove build-essential gcc \
	 && rm -rf /var/lib/apt/lists/*

# Copy app and data
COPY app.py ./app.py

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
