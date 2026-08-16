#!/bin/bash

scp -i my-key-pair.pem Docker/K3s_Img/private.key ec2-user@100.30.231.161:~
scp -i my-key-pair.pem Docker/K3s_Img/public.pub ec2-user@100.30.231.161:~

ssh -i my-key-pair.pem ec2-user@100.30.231.161

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

# IDP Audience: sts.amazonaws.com

# Add this line in the AWS Role's json
# "oidc.sankhari.shop:sub": "system:serviceaccount:default:secrets-reader-sa"

curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-4
chmod 700 get_helm.sh
./get_helm.sh

export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

helm repo add aws-secrets-manager https://aws.github.io/secrets-store-csi-driver-provider-aws
helm install -n kube-system secrets-provider-aws aws-secrets-manager/secrets-store-csi-driver-provider-aws

