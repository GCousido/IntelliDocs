#!/bin/bash
set -e

IP_ADDR_WORKER1="192.168.153.137"
IP_ADDR_WORKER2="192.168.153.133"

USER="user"

if ! command -v podman &> /dev/null
then
    echo "Podman could not be found, installing..."
    sudo dnf install -y podman
fi

cd "$(dirname "$0")"

cd ../IA
sudo podman build -t localhost/intellidocs-ai:v1 .
rm -f ../ai_v1.tar
sudo podman save localhost/intellidocs-ai:v1 -o ../ai_v1.tar

cd ../backend
sudo podman build -t localhost/intellidocs-backend:v1 .
rm -f ../backend_v1.tar
sudo podman save localhost/intellidocs-backend:v1 -o ../backend_v1.tar

cd ../frontend
sudo podman build -t localhost/intellidocs-frontend:v1 .
rm -f ../frontend_v1.tar
sudo podman save localhost/intellidocs-frontend:v1 -o ../frontend_v1.tar

cd ..

sudo podman pull quay.io/minio/minio:latest
rm -f minio_latest.tar
sudo podman save quay.io/minio/minio:latest -o minio_latest.tar

sudo podman pull docker.io/spark:3.5.6
rm -f spark_3.5.6.tar
sudo podman save docker.io/spark:3.5.6 -o spark_3.5.6.tar

scp ai_v1.tar backend_v1.tar frontend_v1.tar minio_latest.tar spark_3.5.6.tar ${USER}@${IP_ADDR_WORKER1}:/home/${USER}/
ssh -t ${USER}@${IP_ADDR_WORKER1} "sudo ctr -n k8s.io images import /home/${USER}/ai_v1.tar && sudo ctr -n k8s.io images import /home/${USER}/backend_v1.tar && sudo ctr -n k8s.io images import /home/${USER}/frontend_v1.tar && sudo ctr -n k8s.io images import /home/${USER}/minio_latest.tar && sudo ctr -n k8s.io images import /home/${USER}/spark_3.5.6.tar"

scp ai_v1.tar backend_v1.tar frontend_v1.tar minio_latest.tar spark_3.5.6.tar ${USER}@${IP_ADDR_WORKER2}:/home/${USER}/
ssh -t ${USER}@${IP_ADDR_WORKER2} "sudo ctr -n k8s.io images import /home/${USER}/ai_v1.tar && sudo ctr -n k8s.io images import /home/${USER}/backend_v1.tar && sudo ctr -n k8s.io images import /home/${USER}/frontend_v1.tar && sudo ctr -n k8s.io images import /home/${USER}/minio_latest.tar && sudo ctr -n k8s.io images import /home/${USER}/spark_3.5.6.tar"

mkdir -p /data/minio
chmod 777 /data/minio

read -p "Do you want to deploy the application to Kubernetes? (y/n) " answer
if [[ "$answer" == "y" ]]; then
kubectl apply -f ./k8s/intellidocs.yaml
else
kubectl rollout restart deployment ocr-deployment layout-deployment classification-deployment extraction-deployment frontend-deployment backend-deployment minio spark-worker spark-master-svc 
fi