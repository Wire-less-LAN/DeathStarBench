import traceback

from opentracing import global_tracer
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

from transformers import AutoModel, AutoTokenizer
import torch


class Server:
    def __init__(self, tracer, port, ip_addr, knative_dns, registry, model_path, agent_rank, nsearch_rank) -> None:
        self.tracer = tracer
        self.port = port
        self.ip_addr = ip_addr
        self.knative_dns = knative_dns
        self.registry = registry
        self.model_path = model_path
        self.agent_rank = agent_rank
        self.nsearch_rank = nsearch_rank
        pass

    def Query(self, prompt, context):
        try:
            print("Got prompt:", prompt)

            prompt = prompt.prompt
            
            inputs = self.tokenizer.encode(prompt, return_tensors="pt").cuda()
            print("encoded")
            outputs = self.model.generate(inputs, max_length=100, num_return_sequences=1)            

            print("generated")
            prompt = self.tokenizer.decode(outputs[0])
            print("LLM resp: ", prompt)

            resp = self.geo_client.pseudo_req()
            print("Pseudo geo resp:", resp.hotelIds)
            prompt += str(resp.hotelIds)

            resp = self.rate_client.pseudo_req()
            print("Pseudo rate resp:", resp.ratePlans)
            prompt += str(resp.ratePlans)

            resp = self.recommendation_client.pseudo_req()
            print("Pseudo rocommendation resp:", resp.HotelIds)
            prompt += str(resp.HotelIds)

            inputs = self.tokenizer.encode(prompt, return_tensors="pt").cuda()
            resp = self.agent_client.Query(inputs, self.tokenizer, self.hello_output) 
            print("Agent resp:", resp.new_prompt)
            prompt = resp.new_prompt 

            return pb.Result(new_prompt=prompt)
        except Exception as e:
            print("Error Query:", e)
            traceback.print_exc()
        # TODO

    def Search(self, prompt, context):
        try:
            print("Got prompt:", prompt)

            prompt = prompt.prompt
            
            inputs = self.tokenizer.encode(prompt, return_tensors="pt").cuda()
            print("encoded")
            outputs = self.model.generate(inputs, max_length=100, num_return_sequences=1)            

            print("generated")
            prompt = self.tokenizer.decode(outputs[0])
            print("LLM resp: ", prompt)

            resp = self.geo_client.pseudo_req()
            print("Pseudo geo resp:", resp.hotelIds)
            prompt += str(resp.hotelIds)

            resp = self.rate_client.pseudo_req()
            print("Pseudo rate resp:", resp.ratePlans)
            prompt += str(resp.ratePlans)

            resp = self.recommendation_client.pseudo_req()
            print("Pseudo rocommendation resp:", resp.HotelIds)
            prompt += str(resp.HotelIds)

            inputs = self.tokenizer.encode(prompt, return_tensors="pt").cuda()
            resp = self.nsearch_client.Query(inputs, self.tokenizer, self.hello_output) 
            print("NSearch resp:", resp.new_prompt)
            prompt = resp.new_prompt 

            return pb.Result(new_prompt=prompt)
        except Exception as e:
            print("Error Search:", e)
            traceback.print_exc()
        # TODO

            

    def run(self):
        if self.port == None:
            raise ValueError("server port must be set")
        self.uuid = str(uuid.uuid4())

        self.tokenizer = AutoTokenizer.from_pretrained(self.model_path, trust_remote_code=True)
        self.model = AutoModel.from_pretrained(self.model_path, trust_remote_code=True).quantize(4).cuda()
        self.model = self.model.eval()

        hello_inputs = self.tokenizer.encode("Hello", return_tensors="pt").cuda()
        self.hello_output = self.model.generate(hello_inputs, max_length=100, num_return_sequences=1)[0]            

        self.geo_client = unicomm.GeoClient("retriever")
        self.rate_client = unicomm.RateClient("retriever")
        self.recommendation_client = unicomm.RecommendationClient("retriever")

        self.nsearch_client = unicomm.NSearchClient("retriever", self.nsearch_rank)
        self.agent_client = unicomm.AgentClient("retriever", self.agent_rank)

        GrpcInstrumentorClient().instrument()
        opts = [
        ('grpc.keepalive_timeout_ms', 120 * 1000),  
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
            
