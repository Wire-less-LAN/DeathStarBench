import grpc
import grpc.experimental
import socket
import os
import ipaddress
import traceback
import redis

import time

from concurrent import futures
from opentracing import global_tracer

import grpc_opentracing
from grpc_opentracing import open_tracing_client_interceptor
from grpc_opentracing.grpcext import intercept_channel, intercept_server

from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.instrumentation.grpc import GrpcInstrumentorServer
import os

import torch
import torch.distributed as dist

import threading

from unicomm.proto import geo_pb2 as geo, geo_pb2_grpc as geo_grpc, rate_pb2 as rate, rate_pb2_grpc as rate_grpc, recommendation_pb2 as recommendation, recommendation_pb2_grpc as recommendation_grpc, agent_pb2 as agent, agent_pb2_grpc as agent_grpc, nsearch_pb2 as nsearch, nsearch_pb2_grpc as nsearch_grpc

def get_rand_tensor():
    return torch.randint(0, 32766, (500, 1), dtype=torch.long).cuda()

def setup_tracer_provider(service_name, ratio, host):
    resource = Resource(attributes={
        SERVICE_NAME: service_name
    })
    sampler = TraceIdRatioBased(ratio)

    jaeger_exporter = JaegerExporter(
        agent_host_name=host.split(':')[0],
        agent_port=int(host.split(':')[1]),
    )

    trace_provider = TracerProvider(resource=resource, sampler=sampler)
    trace.set_tracer_provider(trace_provider)

    span_processor = BatchSpanProcessor(jaeger_exporter)
    trace_provider.add_span_processor(span_processor)


def get_local_ip():
    # Get the network CIDR for gRPC from the environment variable
    grpc_network_cidr = os.getenv('DSB_HOTELRES_GRPC_NETWORK')
    grpc_net = None

    if grpc_network_cidr:
        try:
            grpc_net = ipaddress.ip_network(grpc_network_cidr)
        except ValueError as e:
            print(f"Invalid network CIDR is set in environment DSB_HOTELRES_GRPC_NETWORK: {grpc_network_cidr}")
            print(e)
    
    # Gather all non-loopback IPv4 addresses
    ips = []
    for iface in socket.getaddrinfo(host=socket.gethostname(), port=None, family=socket.AF_INET):
        ip_addr = iface[4][0]
        if ip_addr != '127.0.0.1':  # Exclude loopback
            ips.append(ip_addr)
    
    # If no valid IPs are found, raise an error
    if not ips:
        raise ValueError("Cannot find local IP")

    # Check if any of the IPs is within the specified gRPC network
    if grpc_net:
        for ip in ips:
            if ipaddress.ip_address(ip) in grpc_net:
                print(f"gRPC traffic is routed to the dedicated network {ip}")
                return ip

    # Default to returning the first non-loopback IP address if no gRPC network match
    return ips[0]

class TracingInterceptor(grpc.UnaryUnaryClientInterceptor):
    def __init__(self, tracer):
        self.tracer = tracer

    def intercept_unary_unary(self, continuation, client_call_details, request):
        with self.tracer.start_active_span('grpc_call') as scope:
            return continuation(client_call_details, request)

class HRServer:
    def __init__(self, name, uuid, port, ip_addr, socket_path, registry, register_func, server):
        self.name = name
        self.uuid = uuid
        self.port = port
        self.ip_addr = ip_addr
        self.socket_path = socket_path
        self.registry = registry
        self.register_func = register_func
        self.server = server

    def run_servers(self, opts):
        GrpcInstrumentorServer().instrument()
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=16), options=opts)
        # server = intercept_server(server, grpc_opentracing.open_tracing_server_interceptor(self.server.tracer))
        unix_server = grpc.server(futures.ThreadPoolExecutor(max_workers=16), options=opts)
        # unix_server = intercept_server(unix_server, grpc_opentracing.open_tracing_server_interceptor(self.server.tracer))

        self.register_func(self.server, server)
        self.register_func(self.server, unix_server)

        server.add_insecure_port(f"[::]:{self.port}")
        unix_server.add_insecure_port(f"unix://{self.socket_path}")

        if self.ip_addr is None:
            self.ip_addr = get_local_ip()
        self.registry.agent.service.register(self.name, self.uuid, self.ip_addr, self.port)
        print("Successfully registered in consul")

        server.start()
        unix_server.start()
        print("Servers started")

        server.wait_for_termination()
        unix_server.wait_for_termination()
        # def serve_server():
        #     try:
        #         server.start()
        #         server.wait_for_termination()
        #     except Exception as e:
        #         print("Caught exception running server:", e)
        #         traceback.print_exc()

        # def serve_unix_server():
        #     try:
        #         unix_server.start()
        #         unix_server.wait_for_termination()
        #     except Exception as e:
        #         print("Caught exception running unix_server:", e)
        #         traceback.print_exc()

        # executor = futures.ThreadPoolExecutor()

        # server_future = executor.submit(serve_server)
        # unix_server_future = executor.submit(serve_unix_server)

        # done, not_done = futures.wait(
        #     [server_future, unix_server_future], 
        #     return_when=futures.FIRST_EXCEPTION
        # )

        # for future in done:
        #     if future.exception() is not None:
        #         print("Caught an exception:", future.exception())
        #     else:
        #         print("Server terminated without exception.")

        # for future in not_done:
        #     future.cancel()

        # return done, not_done

class CommType:
    INTERNODE = 0
    INTERCPU = 1
    INTERGPU = 2
    INTRAGPU = 3

def get_comm_type(srv_a, srv_b):
    r = redis.Redis(unix_socket_path="/var/run/redis/redis.sock")
    a_loc = r.get(srv_a)
    b_loc = r.get(srv_b)

    if a_loc == b_loc:  # TODO: handle inter-gpu, intra-gpu
        return CommType.INTERCPU
    else:
        return CommType.INTERNODE

options = [
        ('grpc.keepalive_time_ms', 120000),  
        ('grpc.keepalive_timeout_ms', 20000),  
        ('grpc.keepalive_permit_without_calls', 1),  
    ]
class GeoClient:
    def __init__(self, srv_name):
        chan = grpc.insecure_channel("geo:8083", options)
        unix_chan = grpc.insecure_channel("unix:///var/run/hrsock/geo.sock", options)
        self.stub = geo_grpc.GeoStub(chan)
        self.unix_stub = geo_grpc.GeoStub(unix_chan)
        self.srv_name = srv_name
    def pseudo_req(self):
        comm_type = get_comm_type(self.srv_name, "geo")
        req = geo.Request(lat=38.0235, lon=-122.095)
        if comm_type == CommType.INTERNODE:
            return self.stub.Nearby(req)
        elif comm_type == CommType.INTERCPU:
            return self.unix_stub.Nearby(req)
            
        
class RateClient:
    def __init__(self, srv_name):
        self.srv_name = srv_name
        chan = grpc.insecure_channel("rate:8084", options)
        unix_chan = grpc.insecure_channel("unix:///var/run/hrsock/rate.sock", options)
        self.stub = rate_grpc.RateStub(chan)
        self.unix_stub = rate_grpc.RateStub(unix_chan)
    def pseudo_req(self):
        comm_type = get_comm_type(self.srv_name, "rate")
        req = rate.Request(hotelIds=["1", "2", "3", "9"], inDate="2015-04-09", outDate="2015-04-10")
        if comm_type == CommType.INTERNODE:
            return self.stub.GetRates(req)
        elif comm_type == CommType.INTERCPU:
            return self.unix_stub.GetRates(req)

class RecommendationClient:
    def __init__(self, srv_name):
        self.srv_name = srv_name
        chan = grpc.insecure_channel("recommendation:8085", options)
        unix_chan = grpc.insecure_channel("unix:///var/run/hrsock/recommendation.sock", options)
        self.stub = recommendation_grpc.RecommendationStub(chan)
        self.unix_stub = recommendation_grpc.RecommendationStub(unix_chan)
    def pseudo_req(self):
        comm_type = get_comm_type(self.srv_name, "recommendation")
        req = recommendation.Request(require="dis", lat=38.0235, lon=-122.095)
        if comm_type == CommType.INTERNODE:
            return self.stub.GetRecommendations(req)
        elif comm_type == CommType.INTERCPU:
            return self.unix_stub.GetRecommendations(req)
        
def init_process(master_addr, master_port, rank, size, backend='nccl'):
    os.environ['MASTER_ADDR'] = master_addr
    os.environ['MASTER_PORT'] = master_port
    dist.init_process_group(backend, rank=rank, world_size=size)

class ThreadSafeTag:
    def __init__(self, max, value=0):
        self.value = value
        self.lock = threading.Lock()
        self.max = max

    def next(self):
        with self.lock:
           self.value = (self.value + 1) % self.max
           return self.value

class AgentClient:
    def __init__(self, srv_name, dst, max_tag):
        self.srv_name = srv_name
        
        chan = grpc.insecure_channel("agent:8089", options)
        # unix_chan = grpc.insecure_channel("unix:///var/run/hrsock/agent.sock", options)
        self.stub = agent_grpc.AgentStub(chan)
        # self.unix_stub = agent_grpc.AgentStub(unix_chan)

        self.dst = dst

        self.tag = ThreadSafeTag(max_tag)

    def Query(self, prompt_tensor, tokenizer, hello_outputs):
        comm_type = get_comm_type(self.srv_name, "agent")

        if comm_type == CommType.INTERNODE:
            prompt = tokenizer.decode(prompt_tensor)
            req = agent.AgentRequest(prompt="Hello"*100)
            return self.stub.Query(req)

        elif comm_type == CommType.INTERCPU:
            # print("INTERGPU to agent, dst rank=", self.dst)
            # shape_tensor = torch.tensor(prompt_tensor.shape).cuda()
            # print("Sending shape_tensor:", shape_tensor)
            # dist.send(tensor=shape_tensor, dst=self.dst)

            # prompt_tensor = prompt_tensor.cuda()
            # print("Sending tensor:", prompt_tensor)
            # dist.send(tensor=prompt_tensor, dst=self.dst)

            # shape_tensor = torch.zeros(1, dtype=torch.long).cuda()
            # dist.recv(tensor=shape_tensor, src=self.dst)
            # print("Recv shape_tensor:", shape_tensor)

            # tensor = torch.zeros(size=tuple(shape_tensor.tolist()), dtype=torch.long).cuda()
            # dist.recv(tensor=tensor, src=self.dst)
            # print("Recv tensor:", tensor)
            tag = self.tag.next()
            tensor = get_rand_tensor()
            dist.send(tensor=tensor, dst=self.dst, tag=tag)

            dist.recv(tensor=tensor, src=self.dst, tag=tag)

            resp_str = tokenizer.decode(hello_outputs)
            resp = agent.AgentResult(new_prompt=resp_str)
            return resp
            

class NSearchClient:
    def __init__(self, srv_name, dst, max_tag):
        self.srv_name = srv_name
        
        chan = grpc.insecure_channel("nsearch:8090", options)
        # unix_chan = grpc.insecure_channel("unix:///var/run/hrsock/agent.sock", options)
        self.stub = nsearch_grpc.NSearchStub(chan)
        # self.unix_stub = agent_grpc.AgentStub(unix_chan)

        self.dst = dst
        
        self.tag = ThreadSafeTag(max_tag)

    def Query(self, prompt_tensor, tokenizer, hello_outputs):
        comm_type = get_comm_type(self.srv_name, "nsearch")

        if comm_type == CommType.INTERNODE:
            prompt = tokenizer.decode(prompt_tensor)
            req = nsearch.NSRequest(prompt="Hello"*100)
            return self.stub.Query(req)

        elif comm_type == CommType.INTERCPU:
            # print("INTERGPU to agent, dst rank=", self.dst)
            # shape_tensor = torch.tensor(prompt_tensor.shape).cuda()
            # print("Sending shape_tensor:", shape_tensor)
            # dist.send(tensor=shape_tensor, dst=self.dst)

            # prompt_tensor = prompt_tensor.cuda()
            # print("Sending tensor:", prompt_tensor)
            # dist.send(tensor=prompt_tensor, dst=self.dst)

            # shape_tensor = torch.zeros(1, dtype=torch.long).cuda()
            # dist.recv(tensor=shape_tensor, src=self.dst)
            # print("Recv shape_tensor:", shape_tensor)

            # tensor = torch.zeros(size=tuple(shape_tensor.tolist()), dtype=torch.long).cuda()
            # dist.recv(tensor=tensor, src=self.dst)
            # print("Recv tensor:", tensor)
            tag = self.tag.next()
            tensor = get_rand_tensor()
            dist.send(tensor=tensor, dst=self.dst, tag=tag)

            dist.recv(tensor=tensor, src=self.dst, tag=tag)

            resp_str = tokenizer.decode(hello_outputs)
            resp = nsearch.NSResult(new_prompt=resp_str)
            return resp
            

# class UniClient:
#     def __init__(self, cmd_name, tgt_cmd_name, func_prefix):
#         self.cmd_name = cmd_name
#         self.tgt_cmd_name = tgt_cmd_name
#         self.func_prefix = func_prefix
#         self.conn = None
#         self.unix_conn = None

#     def init_client(self, tgt_srv_name, knative_dns, tracer, rc):
#         options = [
#                 ('grpc.keepalive_time_ms', 120000),  
#                 ('grpc.keepalive_timeout_ms', 20000),  
#                 ('grpc.keepalive_permit_without_calls', 1),  
#             ]
#         if knative_dns:
#             self.conn = grpc.insecure_channel(f"{tgt_srv_name}.{knative_dns}", options=options)
#         else:
#             self.conn = grpc.insecure_channel(tgt_srv_name, options=options)

#         self.unix_conn = grpc.insecure_channel("unix:///var/run/hrsock/" + self.tgt_cmd_name + ".sock", options=options)

#         interceptor = TracingInterceptor(tracer)
#         self.conn = intercept_channel(self.conn, interceptor)
#         self.unix_conn = intercept_channel(self.unix_conn, interceptor)

#     def call_method(channel, service_name, method_name, request):
#         stub_class = grpc.dynamic_stub(channel, service_name)
#         stub = stub_class(channel)
#         method = getattr(stub, method_name)
#         return method(request)
#     def call(self, ctx, func_name, in_message, req_s, resp_s, *opts):
#         out = resp_type()

#         comm_type = get_comm_type(self.cmd_name, self.tgt_cmd_name)

#         if comm_type == CommType.INTERNODE:
#             self.conn.unary_unary(self.func_prefix + func_name, request_serializer=req_s, response_deserializer=resp_s)()
#         elif comm_type == CommType.INTERCPU:
#             grpc.invoke(self.unix_conn, self.func_prefix + func_name, in_message, out, ctx, *opts)

#         # INTERGPU and INTRAGPU handling would go here

#         return out
