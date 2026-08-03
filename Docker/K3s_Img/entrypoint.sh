#!/bin/sh

cat > oidc-rbac.yaml <<EOF
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: oidc-discovery-role
rules:
- nonResourceURLs:
  - "/.well-known/openid-configuration"
  - "/openid/v1/jwks"
  verbs:
  - "get"

---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: oidc-discovery-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: oidc-discovery-role
subjects:
- kind: Group
  name: system:unauthenticated
  apiGroup: rbac.authorization.k8s.io
EOF

cat <<EOF > serviceaccount.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: secrets-reader
  namespace: default
EOF

cat <<EOF > secretproviderclass.yaml
apiVersion: secrets-store.csi.x-k8s.io/v1
kind: SecretProviderClass
metadata:
  name: demo-secret-provider
  namespace: default
spec:
  provider: aws
  parameters:
    objects: |
      - objectName: "That1/Django_Secret"
        objectType: "secretsmanager"
EOF

export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

k3s server \
  --kube-apiserver-arg=service-account-issuer=https://element-hong-everywhere-era.trycloudflare.com \
  --kube-apiserver-arg=service-account-signing-key-file=/keys/private.key \
  --kube-apiserver-arg=service-account-key-file=/keys/public.pub \
  --kube-apiserver-arg=api-audiences=sts.amazonaws.com \
  --kube-apiserver-arg=external-hostname=element-hong-everywhere-era.trycloudflare.com \
  --kube-apiserver-arg=anonymous-auth=true

kubectl apply -f oidc-rbac.yaml
kubectl apply -f serviceaccount.yaml