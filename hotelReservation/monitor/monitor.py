from kubernetes import client, config, watch
import redis

def main():
    config.load_kube_config()
    v1 = client.CoreV1Api()
    redis_client = redis.Redis(unix_socket_path="/var/run/redis/redis.sock", db=0)
    w = watch.Watch()

    redis_client.flushall()
    for event in w.stream(v1.list_namespaced_pod, namespace='default'):
        pod = event['object']
        pod_name = str(pod.metadata.name).split('-')[0]
        pod_node = str(pod.spec.node_name)

        if event['type'] == 'DELETED':
            redis_client.delete(pod_name)
        else:
            redis_client.set(pod_name, pod_node)

        print(f"Event: {event['type']}, Pod Name: {pod_name}, Node: {pod_node}")

if __name__ == '__main__':
    main()
