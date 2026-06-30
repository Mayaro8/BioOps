FROM python:3.12

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       curl \
       ca-certificates \
       gzip \
    && rm -rf /var/lib/apt/lists/*

ARG ARGO_VERSION="v3.7.14"

RUN curl --fail --location --retry 5 --retry-delay 5 \
      -o /tmp/argo-linux-amd64.gz \
      "https://github.com/argoproj/argo-workflows/releases/download/${ARGO_VERSION}/argo-linux-amd64.gz" \
    && gunzip /tmp/argo-linux-amd64.gz \
    && chmod +x /tmp/argo-linux-amd64 \
    && mv /tmp/argo-linux-amd64 /usr/local/bin/argo \
    && argo version --client

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

ENV PYTHONUNBUFFERED=1
