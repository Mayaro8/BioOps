FROM python:3.12

WORKDIR /app

COPY k8s/argo/local/bin/argo-linux-amd64 /usr/local/bin/argo

RUN chmod +x /usr/local/bin/argo \
    && argo version --short

COPY submit_master_files/argo-submit-master/requirements.txt /app/requirements.txt

RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r /app/requirements.txt

COPY submit_master_files/argo-submit-master/ /app/

ENV PYTHONUNBUFFERED=1
