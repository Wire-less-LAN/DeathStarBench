#!/bin/bash

cd $(dirname $0)
EXEC="docker build"

# $EXEC create --name mybuilder1 --use
$EXEC --pull=false -t "anliu/hr-agents:static" -f Dockerfile . --platform linux/amd64 --load 

docker save anliu/hr-agents:static -o /home/ubuntu/ahra.tar.gz 
scp /home/ubuntu/ahra.tar.gz ubuntu@10.2.32.141:~
ssh root@10.2.32.141 "docker image load -i /home/ubuntu/ahra.tar.gz"

kubectl delete -Rf ../kubernetes/retriever/
kubectl delete -Rf ../kubernetes/agent/
kubectl delete -Rf ../kubernetes/nsearch/
kubectl apply -Rf ../kubernetes/retriever/
kubectl apply -Rf ../kubernetes/agent/
kubectl apply -Rf ../kubernetes/nsearch/

cd - >/dev/null
