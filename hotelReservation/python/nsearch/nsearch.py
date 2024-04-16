import logging
import threading
import concurrent.futures
import asyncio
import traceback

from opentracing import global_tracer
from grpc_opentracing import open_tracing_client_interceptor
from grpc_opentracing.grpcext import intercept_channel, intercept_server

import uuid
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from unicomm import unicomm
from unicomm.proto import geo_pb2 as geo, geo_pb2_grpc as geo_grpc, rate_pb2 as rate, rate_pb2_grpc as rate_grpc, recommendation_pb2 as recommendation, recommendation_pb2_grpc as recommendation_grpc
from unicomm.proto import nsearch_pb2 as pb, nsearch_pb2_grpc as pb_grpc

import grpc
from opentelemetry.instrumentation.grpc import GrpcInstrumentorClient

from transformers import AutoModel, AutoTokenizer
import torch
import torch.distributed as dist


class Server:
    def __init__(self, tracer, port, ip_addr, knative_dns, registry, model_path, retriever_rank, workers) -> None:
        self.tracer = tracer
        self.port = port
        self.ip_addr = ip_addr
        self.knative_dns = knative_dns
        self.registry = registry
        self.model_path = model_path
        self.retriever_rank = retriever_rank
        self.workers = workers

    def Query(self, prompt, context):
        try:
            print("Got prompt:", prompt)

            prompt = prompt.prompt
            
            hello_inputs = self.tokenizer.encode("Hello", return_tensors="pt").cuda()
            outputs = self.model.generate(hello_inputs, max_length=100, num_return_sequences=1)
            prompt += self.tokenizer.decode(outputs[0])
            
            print("LLM resp: ", prompt)
            
            return pb.NSResult(new_prompt=prompt)
        except Exception as e:
            print("Error Query:", e)
            traceback.print_exc()

    def run_pseudo_p2p_server(self, src, tag):
        while True:
            tensor = torch.zeros([500, 1], dtype=torch.long).cuda()
            dist.recv(tensor=tensor, src=src, tag=tag)
            outputs = self.model.generate(self.hello_inputs, max_length=100, num_return_sequences=1)
            tensor = unicomm.get_rand_tensor()
            dist.send(tensor=tensor, dst=src, tag=tag)
            

    def run_p2p_server(self, src):
        while True:
            print("Listening p2p tensor from src=", src)
            shape_tensor = torch.zeros(2, dtype=torch.long).cuda()
            dist.recv(tensor=shape_tensor, src=src)
            print("P2P recv shape: ", shape_tensor.cpu())

            tensor = torch.zeros(size=tuple(shape_tensor.tolist()), dtype=torch.long).cuda()
            dist.recv(tensor=tensor, src=src)
            print("P2P recv tensor: ", tensor.cpu())

            outputs = self.model.generate(tensor, max_length=1000, num_return_sequences=1)
            print("LLM resp:", outputs)

            shape_tensor = torch.tensor(outputs[0].shape).cuda()
            dist.send(tensor=shape_tensor, dst=src)
            print("P2P resp shape: ", shape_tensor)
            tensor = outputs[0].cuda()
            dist.send(tensor=tensor, dst=src)
            print("P2P resp: ", tensor)


    def run(self):
        if self.port == None:
            raise ValueError("server port must be set")
        self.uuid = str(uuid.uuid4())

        self.tokenizer = AutoTokenizer.from_pretrained(self.model_path, trust_remote_code=True)
        self.model = AutoModel.from_pretrained(self.model_path, trust_remote_code=True).quantize(4).cuda()
        self.model = self.model.eval()

        self.hello_inputs = self.tokenizer.encode("Hello", return_tensors="pt").cuda()

        GrpcInstrumentorClient().instrument()
        opts = [
        ('grpc.keepalive_timeout_ms', 120 * 1000),  
        ('grpc.keepalive_permit_without_calls', 1),  
        ]
        hrs = unicomm.HRServer("srv-nsearch",
                               self.uuid,
                               self.port,
                               self.ip_addr,
                               "/var/run/hrsock/nsearch.sock",
                               self.registry,
                               pb_grpc.add_NSearchServicer_to_server,
                               self)


        threads = []
        for i in range(self.workers):
            t = threading.Thread(target=self.run_pseudo_p2p_server, args=[self.retriever_rank, i])
            t.start()
            threads.append(t)
        hrs.run_servers(opts)
        for t in threads:
            t.join()
        # with concurrent.futures.ThreadPoolExecutor(max_workers=32*4) as executor:
        #     future1 = executor.submit(hrs.run_servers, opts)
        #     future2 = executor.submit(self.run_p2p_server, self.retriever_rank)

        #     try:
        #         done, not_done = concurrent.futures.wait(
        #             [future1, future2], 
        #             return_when=concurrent.futures.FIRST_COMPLETED,
        #         )

        #         for future in not_done:
        #             future.cancel()
        
        #     except KeyboardInterrupt:
        #         future1.cancel()
        #         future2.cancel()

