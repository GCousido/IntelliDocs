#!/bin/bash
set -e


cd IA
sudo podman build -t localhost/intellidocs-ai:v3 .
sudo podman save localhost/intellidocs-ai:v3 -o ../ai_v3.tar
cd ../Backend
sudo podman build -t localhost/intellidocs-backend:v3 .
sudo podman save localhost/intellidocs-backend:v3 -o ../backend_v3.tar
cd ../frontend
sudo podman build -t localhost/intellidocs-frontend:v2 .
sudo podman save localhost/intellidocs-frontend:v2 -o ../frontend_v2.tar
cd ..

sudo podman pull quay.io/minio/minio:latest
sudo podman save quay.io/minio/minio:latest -o minio_latest.tar

sudo podman pull bitnami/spark:latest
sudo podman save bitnami/spark:latest -o spark_latest.tar

scp ai_v3.tar backend_v3.tar frontend_v2.tar minio_latest.tar spark_latest.tar user@172.16.167.142:/home/user/
ssh user@172.16.167.142 "sudo ctr -n k8s.io images import /home/user/ai_v3.tar && sudo ctr -n k8s.io images import /home/user/backend_v3.tar && sudo ctr -n k8s.io images import /home/user/frontend_v2.tar && sudo ctr -n k8s.io images import /home/user/minio_latest.tar && sudo ctr -n k8s.io images import /home/user/spark_latest.tar"

scp ai_v3.tar backend_v3.tar frontend_v2.tar minio_latest.tar spark_latest.tar user@172.16.167.143:/home/user/
ssh user@172.16.167.143 "sudo ctr -n k8s.io images import /home/user/ai_v3.tar && sudo ctr -n k8s.io images import /home/user/backend_v3.tar && sudo ctr -n k8s.io images import /home/user/frontend_v2.tar && sudo ctr -n k8s.io images import /home/user/minio_latest.tar && sudo ctr -n k8s.io images import /home/user/spark_latest.tar"
