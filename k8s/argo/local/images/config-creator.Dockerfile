FROM python:3.11

WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl \
    zip \
    nano \
    parallel \
    bc \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN curl -s "https://awscli.amazonaws.com/awscli-exe-linux-x86_64-2.15.34.zip" \
    -o "/tmp/awscliv2.zip" \
    && unzip -q "/tmp/awscliv2.zip" -d "/tmp/" \
    && bash "/tmp/aws/install" \
    && rm -rf /tmp/aws /tmp/awscliv2.zip

RUN pip install --no-cache-dir numpy pandas

COPY . /app/

RUN chmod +x /app/*.sh || true

ENV PYTHONUNBUFFERED=1

CMD ["bash", "handler.sh"]
