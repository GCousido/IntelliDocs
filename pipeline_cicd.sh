#!/bin/bash
set -e

pip install -q pytest httpx
pytest tests/ -v

cd ai_models
sudo podman build -t localhost/intellidocs-ai:v3 .
sudo podman save localhost/intellidocs-ai:v3 -o ../ai_v3.tar
cd ../backend
sudo podman build -t localhost/intellidocs-backend:v3 .
sudo podman save localhost/intellidocs-backend:v3 -o ../backend_v3.tar
cd ../frontend
sudo podman build -t localhost/intellidocs-frontend:v2 .
sudo podman save localhost/intellidocs-frontend:v2 -o ../frontend_v2.tar
cd ..

scp ai_v3.tar backend_v3.tar frontend_v2.tar user@172.16.167.142:/home/user/
ssh user@172.16.167.142 "sudo ctr -n k8s.io images import /home/user/ai_v3.tar && sudo ctr -n k8s.io images import /home/user/backend_v3.tar && sudo ctr -n k8s.io images import /home/user/frontend_v2.tar"

scp ai_v3.tar backend_v3.tar frontend_v2.tar user@172.16.167.143:/home/user/
ssh user@172.16.167.143 "sudo ctr -n k8s.io images import /home/user/ai_v3.tar && sudo ctr -n k8s.io images import /home/user/backend_v3.tar && sudo ctr -n k8s.io images import /home/user/frontend_v2.tar"

kubectl apply -f ai_models/ai-k8s.yaml
kubectl apply -f backend/backend-k8s.yaml
kubectl apply -f frontend/frontend-k8s.yaml

kubectl rollout restart deployment ocr-deployment layout-deployment classification-deployment extraction-deployment backend-deployment frontend-deployment
