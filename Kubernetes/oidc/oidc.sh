#!/bin/bash

scp -i my-key-pair.pem Docker/K3s_Img/private.key ec2-user@107.22.110.108:~
scp -i my-key-pair.pem Docker/K3s_Img/public.pub ec2-user@107.22.110.108:~

ssh -i my-key-pair.pem ec2-user@107.22.110.108

curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="server \
  --write-kubeconfig-mode 644 \
  --kube-apiserver-arg=service-account-issuer=https://oidc.sankhari.shop \
  --kube-apiserver-arg=service-account-signing-key-file=/home/ec2-user/private.key \
  --kube-apiserver-arg=service-account-key-file=/home/ec2-user/public.pub \
  --kube-apiserver-arg=api-audiences=sts.amazonaws.com" sh -

kubectl apply -f https://raw.githubusercontent.com/BikramSankhari/That-1/refs/heads/Auth_Backend/Kubernetes/oidc/oidc-discovery-configmap.yaml
kubectl apply -f https://raw.githubusercontent.com/BikramSankhari/That-1/refs/heads/Auth_Backend/Kubernetes/oidc/oidc-jwks-configmap.yaml
kubectl apply -f https://raw.githubusercontent.com/BikramSankhari/That-1/refs/heads/Auth_Backend/Kubernetes/oidc/oidc-nginx-config.yaml
kubectl apply -f https://raw.githubusercontent.com/BikramSankhari/That-1/refs/heads/Auth_Backend/Kubernetes/oidc/oidc-nginx-deployment.yaml
kubectl apply -f https://raw.githubusercontent.com/BikramSankhari/That-1/refs/heads/Auth_Backend/Kubernetes/oidc/oidc-nginx-service.yaml
kubectl apply -f https://raw.githubusercontent.com/BikramSankhari/That-1/refs/heads/Auth_Backend/Kubernetes/oidc/service-account.yaml

sudo yum install git make -y

git clone https://github.com/aws/amazon-eks-pod-identity-webhook.git

kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.21.1/cert-manager.yaml
make cluster-up IMAGE=amazon/amazon-eks-pod-identity-webhook:latest

kubectl apply -f https://raw.githubusercontent.com/BikramSankhari/That-1/refs/heads/Auth_Backend/Kubernetes/oidc/test-pod.yaml

# Add this line in the AWS Role's json
# "oidc.sankhari.shop:sub": "system:serviceaccount:default:secrets-reader-sa"