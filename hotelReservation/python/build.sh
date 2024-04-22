#!/bin/bash

rsync -rlvz --exclude "chatglm3-6b" --exclude "distilbert-base-uncased" --exclude "build.sh" /home/ubuntu/DeathStarBench/hotelReservation/python/ root@10.2.32.141:/home/ubuntu/DeathStarBench/hotelReservation/python/

cd $(dirname $0)
EXEC="docker build"

# $EXEC create --name mybuilder1 --use
$EXEC --pull=false -t "anliu/hr-agents:static" -f Dockerfile . --platform linux/amd64 --load 

ssh root@10.2.32.141 "cd /home/ubuntu/DeathStarBench/hotelReservation/python && ./build.sh"

kubectl delete -Rf ../kubernetes/retriever/ --wait=true
kubectl delete -Rf ../kubernetes/agent/ --wait=true
kubectl delete -Rf ../kubernetes/nsearch/ --wait=true
kubectl apply -Rf ../kubernetes/retriever/
kubectl apply -Rf ../kubernetes/agent/
kubectl apply -Rf ../kubernetes/nsearch/

cd - >/dev/null
