#!/bin/bash

curl -sfL https://get.k3s.io | sh -
cd /etc/rancher/k3s/
udo chown ec2-user:ec2-user k3s.yaml 
sudo systemctl restart k3s
sudo mkdir k8s_configs
cd k8s_configs/
