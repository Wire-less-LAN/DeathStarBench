kubectl delete -Rf ../kubernetes/retriever/ --wait=true
kubectl delete -Rf ../kubernetes/agent/ --wait=true
kubectl delete -Rf ../kubernetes/nsearch/ --wait=true
kubectl apply -Rf ../kubernetes/retriever/
kubectl apply -Rf ../kubernetes/agent/
kubectl apply -Rf ../kubernetes/nsearch/
