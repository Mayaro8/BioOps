FROM python:3.12
WORKDIR /app

# Yandex Cloud CLI
RUN curl -sSL https://storage.yandexcloud.net/yandexcloud-yc/install.sh | bash 
ENV PATH="/root/yandex-cloud/bin:${PATH}"

COPY argoworkflow_authorized_key.json /app/
RUN yc config profile create sa-profile && \
	yc config set service-account-key argoworkflow_authorized_key.json && \
	yc config set cloud-id b1gi58g81vplnoa8tdbt && \
	yc config set folder-id b1ggjgcj0ci3dr0lohs6

COPY requirements.txt /app/
ENV PYTHONUNBUFFERED=1 
RUN pip install --upgrade pip && pip install --no-cache-dir -r /app/requirements.txt

# Kubectl
RUN curl -LO https://storage.googleapis.com/kubernetes-release/release/$(curl -s https://storage.googleapis.com/kubernetes-release/release/stable.txt)/bin/linux/amd64/kubectl && \
	chmod +x ./kubectl && \
	mv ./kubectl /usr/local/bin

# Argo CLI 
ARG ARGO_VERSION="v3.3.8"
RUN curl -sLO "https://github.com/argoproj/argo-workflows/releases/download/${ARGO_VERSION}/argo-linux-amd64.gz" \
    && gunzip argo-linux-amd64.gz \
    && chmod +x argo-linux-amd64 \
    && mv argo-linux-amd64 /usr/local/bin/argo

COPY . /app/
