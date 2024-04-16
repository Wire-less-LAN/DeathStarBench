#!/bin/bash

cd $(dirname $0)/..


EXEC="docker buildx"

USER="hhutw157"

TAG="latest"

# ENTER THE ROOT FOLDER
cd ../
ROOT_FOLDER=$(pwd)
$EXEC create --name mybuilder0 --use

for i in hotelreservation #frontend geo profile rate recommendation reserve search user #uncomment to build multiple images
do
  IMAGE=${i}
  echo Processing image ${IMAGE}
  cd $ROOT_FOLDER
  $EXEC build --no-cache --progress=plain -t "$USER"/"$IMAGE":"$TAG" -f Dockerfile . --platform linux/amd64 --load 
  cd $ROOT_FOLDER

  echo
done


cd - >/dev/null
