# Use an appropriate base image
FROM python:3.11

# Install necessary packages
RUN apt-get update && apt-get install -y \
    curl \ 
    zip \ 
    nano \
    parallel \
    bc \
    && apt-get clean 

# Install aws
RUN curl -s "https://awscli.amazonaws.com/awscli-exe-linux-x86_64-2.15.34.zip" -o "/tmp/awscliv2.zip" && \
    unzip -q "/tmp/awscliv2.zip" -d "/tmp/" && \
    bash "/tmp/aws/install" 

# Install Python dependencies
RUN pip install numpy pandas

COPY *.sh . 
COPY *.py .  
COPY methods.tsv . 

RUN chmod +x *.sh *.py 
