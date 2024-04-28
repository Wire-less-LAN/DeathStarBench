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

from transformers import AutoModel, AutoTokenizer, DistilBertModel, DistilBertTokenizer
import torch
import torch.distributed as dist


class Server:
    def __init__(self, tracer, port, ip_addr, knative_dns, registry, model_path, retriever_rank, workers, bert_model_path, batch_size) -> None:
        self.tracer = tracer
        self.port = port
        self.ip_addr = ip_addr
        self.knative_dns = knative_dns
        self.registry = registry
        self.model_path = model_path
        self.retriever_rank = retriever_rank
        self.workers = workers

        self.bert_model_path = bert_model_path
        self.batch_size = batch_size        

    def Query(self, prompt, context):
        try:
            logging.debug("Got prompt")
            tag = prompt.tag
            prompt = prompt.prompt
            
            input = self.tokenizer.encode(prompt, return_tensors="pt", add_special_tokens=False).cuda()
            self.receiver.push(unicomm.Msg(tag=tag, tensor=input[0]))
            new_prompt = self.result_q.get(tag)
            
            return pb.NSResult(new_prompt=prompt, tag=tag)
        except Exception as e:
            print("Error Query:", e)
            traceback.print_exc()

    def pseudo_gen(self):
        input = {
            "input_ids": torch.stack([self.bert_input['input_ids'][0]]*self.batch_size, dim=0),
            "attention_mask": torch.stack([self.bert_input['attention_mask'][0]]*self.batch_size, dim=0),
        }
        self.model(**input)
            
    def run_gen(self, receiver, sender):
        while True:
            msgs = receiver.pop()
            logging.debug("[RUNGEN] popped msgs")
            self.pseudo_gen()
            logging.debug("[RUNGEN] generated")
            sender.push(*msgs)
            logging.debug("[RUNGEN] pushed to sender")

    def run_get_grpc_res(self, sender, result_q):
        while True:
            msg = sender.grpc_get_msg()
            prompt = self.tokenizer.decode(msg.tensor)
            logging.debug(f"[RUNGRPC] decoded: {prompt}")
            result_q.put(msg.tag, prompt)
            logging.debug(f"[RUNGRPC] put tag: {msg.tag}")


    def run(self):
        if self.port == None:
            raise ValueError("server port must be set")
        self.uuid = str(uuid.uuid4())

        self.tokenizer = AutoTokenizer.from_pretrained(self.model_path, trust_remote_code=True)
        # self.model = AutoModel.from_pretrained(self.model_path, trust_remote_code=True).quantize(4).cuda()
        self.model = DistilBertModel.from_pretrained(self.bert_model_path).to(torch.device("cuda"))
        self.model = self.model.eval()

        # pseudo bert encoded input
        bert_tokenizer = DistilBertTokenizer.from_pretrained(self.bert_model_path) 
        self.bert_input = bert_tokenizer("Hello World!" * 100, return_tensors="pt").to(torch.device("cuda"))

        self.receiver = unicomm.Receiver(self.batch_size) 
        # receive_p2p_thread = threading.Thread(target=self.receiver.listen_p2p, args=[self.retriever_rank])
    
        self.sender = unicomm.Sender(self.batch_size)        
        gen_thread = threading.Thread(target=self.run_gen, args=[self.receiver, self.sender])
        gen_thread.start()

        self.result_q = unicomm.ResultQueue(self.tokenizer)
        
        get_threads = [] 
        for i in range(10):
            get_thread = threading.Thread(target=self.run_get_grpc_res, args=[self.sender, self.result_q])
            get_thread.start()
            get_threads.append(get_thread)
        # send_thread = threading.Thread(target=self.sender.send_p2p, args=[self.retriever_rank])

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


        hrs.run_servers(opts)

        # receive_p2p_thread.join()
        gen_thread.join()
        for t in get_threads:
            t.join()
        # send_thread.join()