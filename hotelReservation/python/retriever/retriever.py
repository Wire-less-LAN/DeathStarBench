import traceback

from opentracing import global_tracer
from opentelemetry import trace
from grpc_opentracing import open_tracing_client_interceptor
from grpc_opentracing.grpcext import intercept_channel, intercept_server
from proto import retriever_pb2 as pb, retriever_pb2_grpc as pb_grpc

import uuid
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from unicomm import unicomm
from unicomm.proto import geo_pb2 as geo, geo_pb2_grpc as geo_grpc, rate_pb2 as rate, rate_pb2_grpc as rate_grpc, recommendation_pb2 as recommendation, recommendation_pb2_grpc as recommendation_grpc

import grpc
from opentelemetry.instrumentation.grpc import GrpcInstrumentorClient

from transformers import AutoModel, AutoTokenizer, DistilBertTokenizer, DistilBertModel
import torch

import threading

import logging
import time
class Server:
    def __init__(self, tracer, port, ip_addr, knative_dns, registry, model_path, bert_model_path, agent_rank, nsearch_rank, agent_workers, nsearch_workers, batch_size) -> None:
        self.tracer = tracer
        self.port = port
        self.ip_addr = ip_addr
        self.knative_dns = knative_dns
        self.registry = registry
        self.model_path = model_path
        self.bert_model_path = bert_model_path
        self.agent_rank = agent_rank
        self.agent_workers = agent_workers
        self.nsearch_rank = nsearch_rank
        self.nsearch_workers = nsearch_workers
        self.batch_size = batch_size

        self.lock = threading.Lock()
        self.tag = 0
        pass
    
    def get_tag(self):
        with self.lock:
            self.tag += 1
            return self.tag
        

    def Query(self, prompt, context):
        try:
            with self.tracer.start_as_current_span("Retriever/Query"):
                logging.debug("Got prompt")
                prompt = prompt.prompt
                resp = self.geo_client.pseudo_req()
                prompt += str(resp.hotelIds)
                resp = self.rate_client.pseudo_req()
                prompt += str(resp.ratePlans)
                resp = self.recommendation_client.pseudo_req()
                prompt += str(resp.HotelIds)

                input = self.tokenizer.encode("Hello World! " * 1000, return_tensors="pt", add_special_tokens=False).cuda()

                tag = self.get_tag()
                self.agent_receiver.push(unicomm.Msg(tag=tag, tensor=input[0]))
                new_prompt = self.result_q.get(tag)

                return pb.Result(new_prompt=new_prompt)
        except Exception as e:
            print("Error Query:", e)
            traceback.print_exc()

    def Search(self, prompt, context):
        try:
            logging.debug("Got prompt")
            prompt = prompt.prompt
            resp = self.geo_client.pseudo_req()
            prompt += str(resp.hotelIds)
            resp = self.rate_client.pseudo_req()
            prompt += str(resp.ratePlans)
            resp = self.recommendation_client.pseudo_req()
            prompt += str(resp.HotelIds)
            logging.debug("grpc finished")

            input = self.tokenizer.encode("Hello World! " * 1000, return_tensors="pt", add_special_tokens=False).cuda()
            logging.debug("input encoded")

            tag = self.get_tag()
            logging.debug(f"got tag={tag}")
            self.nsearch_receiver.push(unicomm.Msg(tag=tag, tensor=input[0]))
            new_prompt = self.result_q.get(tag)

            return pb.Result(new_prompt=new_prompt)
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
            self.pseudo_gen()
            sender.push(*msgs)

    def run_get_grpc_res(self, sender, result_q, client):
        while True:
            msg = sender.grpc_get_msg()
            prompt = self.tokenizer.decode(msg.tensor)
            result = client.Query(prompt, msg.tag)
            result_q.put(msg.tag, result.new_prompt)
        
    def run(self):
        if self.port == None:
            raise ValueError("server port must be set")
        self.uuid = str(uuid.uuid4())

        self.gen_q = unicomm.ThreadSafeQueue(self.batch_size)
        self.send_q = unicomm.ThreadSafeQueue(self.batch_size)

        self.tokenizer = AutoTokenizer.from_pretrained(self.model_path, trust_remote_code=True)
        # self.model = AutoModel.from_pretrained(self.model_path, trust_remote_code=True).quantize(4).cuda()
        # self.model = self.model.eval()

        self.geo_client = unicomm.GeoClient("retriever")
        self.rate_client = unicomm.RateClient("retriever")
        self.recommendation_client = unicomm.RecommendationClient("retriever")

        self.nsearch_client = unicomm.NSearchClient("retriever")
        self.agent_client = unicomm.AgentClient("retriever")

        self.agent_receiver = unicomm.Receiver(self.batch_size) # this needs no p2p listening thread
        self.nsearch_receiver = unicomm.Receiver(self.batch_size) # this needs no p2p listening thread
        self.agent_sender = unicomm.Sender(self.batch_size)        
        self.nsearch_sender = unicomm.Sender(1)        # cuz it's inter-node

        self.model = DistilBertModel.from_pretrained(self.bert_model_path).to(torch.device("cuda"))
        self.model = self.model.eval()

        # pseudo bert encoded input
        bert_tokenizer = DistilBertTokenizer.from_pretrained(self.bert_model_path) 
        self.bert_input = bert_tokenizer("Hello World! " * 100, return_tensors="pt").to(torch.device("cuda"))

        self.result_q = unicomm.ResultQueue(self.tokenizer)
        
        agent_gen_thread = threading.Thread(target=self.run_gen, args=[self.agent_receiver, self.agent_sender])
        agent_gen_thread.start()
        nsearch_gen_thread = threading.Thread(target=self.run_gen, args=[self.nsearch_receiver, self.nsearch_sender])
        nsearch_gen_thread.start()

        agent_send_thread = threading.Thread(target=self.agent_sender.send_recv_p2p, args=[self.agent_rank, self.result_q])
        agent_send_thread.start()

        nsearch_get_threads = [] 
        for i in range(self.batch_size):
            nsearch_get_thread = threading.Thread(target=self.run_get_grpc_res, args=[self.nsearch_sender, self.result_q, self.nsearch_client])
            nsearch_get_thread.start()
            nsearch_get_threads.append(nsearch_get_thread)

        self.tracer = trace.get_tracer(__name__)

        GrpcInstrumentorClient().instrument()
        opts = [
        ('grpc.keepalive_timeout_ms', 5 * 1000),  
        ('grpc.keepalive_permit_without_calls', 1),  
        ]
        hrs = unicomm.HRServer("srv-retriever",
                               self.uuid,
                               self.port,
                               self.ip_addr,
                               "/var/run/hrsock/retriever.sock",
                               self.registry,
                               pb_grpc.add_RetrieverServicer_to_server,
                               self)
        hrs.run_servers(opts)

        agent_gen_thread.join()
        nsearch_gen_thread.join()
        agent_send_thread.join()
        for t in nsearch_get_threads:
            t.join()
        
            
