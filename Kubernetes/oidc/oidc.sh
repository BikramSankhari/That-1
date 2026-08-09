#!/bin/bash

scp -i my-key-pair.pem Docker/K3s_Img/private.key ec2-user@44.211.95.137:~
scp -i my-key-pair.pem Docker/K3s_Img/public.pub ec2-user@44.211.95.137:~

ssh -i my-key-pair.pem ec2-user@44.211.95.137

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
