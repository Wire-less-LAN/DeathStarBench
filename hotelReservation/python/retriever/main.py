import json
import logging
import argparse
import traceback
import os
import logging
from DeathStarBench.hotelReservation.python import nsearch
import retriever
from jaeger_client.config import Config

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from unicomm import unicomm

import consul

def new_consul_client(addr):
    try:
        c = consul.Consul(host=addr)
        return c, None
    except Exception as e:
        return None, e

default_sample_ratio = 0.01

def init_jaeger_tracer(service_name, host):
    ratio = default_sample_ratio  

    val = os.getenv("JAEGER_SAMPLE_RATIO")
    if val is not None:
        try:
            ratio = float(val)
            if ratio > 1:
                ratio = 1.0
        except ValueError:
            pass  

    logging.info(f"Jaeger client: adjusted sample ratio {ratio}")

    temp_cfg = {
        'service_name': service_name,
        'sampler': {
            'type': 'probabilistic',
            'param': ratio,
        },
        'local_agent': {
            'reporting_host': host,
        },
        'logging': True,  
    }

    logging.info("Overriding Jaeger config with env variables")
    cfg = Config(temp_cfg, validate=True, service_name=service_name)

    try:
        tracer = cfg.initialize_tracer()
        return tracer
    except Exception as e:
        return None, e

def main():
    logging.basicConfig(format='%(asctime)s %(message)s', datefmt='%Y-%m-%dT%H:%M:%S', level=logging.DEBUG)
    logging.info("Reading config...")
    
    try:
        with open("config.json", 'r') as json_file:
            config = json.load(json_file)
    except Exception as err:
        logging.error(f"Got error while reading config: {err}")
        return
    
    serv_port = int(config["RetrieverPort"])
    serv_ip = None
    knative_dns = config["KnativeDomainName"]

    master_addr = config["MasterAddr"]
    master_port = config["MasterPort"]
    world_size = int(config["WorldSize"])
    rank = int(config["RetrieverRank"])
    agent_rank = int(config["AgentRank"])
    nsearch_rank = int(config["NSearchRank"])

    unicomm.init_process(master_addr, master_port, rank, world_size)
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--jaegerAddr", default=config["jaegerAddress"], help="Jaeger address")
    parser.add_argument("--consulAddr", default=config["consulAddress"], help="Consul address")
    args = parser.parse_args()
    
    logging.info(f"Initializing jaeger agent [service name: search | host: {args.jaegerAddr}]...")
    try:
        # tracer = init("search", args.jaegerAddr)
        unicomm.setup_tracer_provider("retriever", 0.01, args.jaegerAddr)
    except Exception as err:
        logging.critical(f"Got error while initializing jaeger agent: {err}")
        return
    logging.info("Jaeger agent initialized")
    
    logging.info(f"Initializing consul agent [host: {args.consulAddr}]...")
    try:
        registry_client, _ = new_consul_client(args.consulAddr)
    except Exception as err:
        logging.critical(f"Got error while initializing consul agent: {err}")
        return
    logging.info("Consul agent initialized")
    
    srv = retriever.Server(
        tracer=None,
        port=serv_port,
        ip_addr=serv_ip,
        knative_dns=knative_dns,
        registry=registry_client,
        model_path="/chatglm3-6b",
        agent_rank=agent_rank,
        nsearch_rank=nsearch_rank
    )

    logging.info("Starting server...")
    try:
        srv.run()
    except Exception as err:
        logging.critical(f"Server failed to start: {err}")
        traceback.print_exc()

if __name__ == "__main__":
    main()
