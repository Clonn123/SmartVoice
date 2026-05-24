FROM python:3.10-slim

WORKDIR /smartvoice

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y \
    gcc \
    ffmpeg \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY ./backend/pyproject.toml ./

RUN pip install --upgrade pip setuptools wheel

RUN pip install --no-cache-dir .

COPY . .
