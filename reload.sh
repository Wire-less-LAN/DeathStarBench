#!/bin/bash
hotelReservation/kubernetes/scripts/build-docker-images.sh
docker tag hhutw157/hotelreservation deathstarbench/hotel-reservation:static
docker save deathstarbench/hotel-reservation:static -o /home/ubuntu/ahr.tar.gz 
scp /home/ubuntu/ahr.tar.gz ubuntu@10.2.32.141:~
ssh root@10.2.32.141 "docker image load -i /home/ubuntu/ahr.tar.gz"
# read -n 1 -s -p "按任意键继续..."
# echo "继续执行脚本..."
kubectl delete -Rf hotelReservation/kubernetes/
kubectl apply -Rf hotelReservation/kubernetes/

kubectl delete -Rf hotelReservation/kubernetes/
kubectl apply -Rf hotelReservation/kubernetes/