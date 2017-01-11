#!/usr/bin/env python3
# runs a haproxy instance that listens on some TCP port(s) and forwards (load-balances) all connections
# to some ports on some target nodes.
# Continuously tracks existing nodes and restarts the proxy if anything changes.
# Must be run in the host network.

import pykube
import re
import os
import signal
import sys
import time
import argparse
import traceback
import json
import logging

parser = argparse.ArgumentParser()

parser.add_argument('-i', '--interval', type=int, default=30, help='interval between updates, in seconds')

# TODO: allow for label matching
parser.add_argument('-t', '--target', default='.*', help='target nodes name pattern')

# TODO: also allow for name-based mapping (virtual hosting)
parser.add_argument('-p', '--port-mapping',
                    dest='port_mappings',
                    action='append',
                    required=True,
                    help='specify a port mapping (<proxy port>:<target port>)')

parser.add_argument('-e', '--exec', default='/usr/local/sbin/haproxy-systemd-wrapper', help='haproxy executable to run')
parser.add_argument('-c', '--config', default='/usr/local/etc/haproxy/haproxy.cfg', help='location of haproxy.cfg to generate and run the executable with (via -f <file>)')

parser.add_argument('--kube-config', dest='kube_conf', help='Specify kubernetes client config file for accessing the API. Default is to use the service account.')

parser.add_argument('-d', '--debug', action='store_true', help='debug mode')
parser.add_argument('--nodes-json', dest='nodes_json', help='for debugging, read the list of nodes from this json file rather than from k8s')

args = parser.parse_args()

port_mappings = []
pm_pat = re.compile('([0-9]+):([0-9]+)')
for pm in args.port_mappings:
    m = pm_pat.match(pm)
    assert m, "Illegal port mapping: {0}".format(pm)
    port_mappings.append(dict(proxy_port=int(m.group(1)), dest_port=int(m.group(2))))


class K8SConfigSource:

    def __init__(self):
        if args.kube_conf:
            api = pykube.HTTPClient(pykube.KubeConfig.from_file(args.kube_conf))
        else:
            api = pykube.HTTPClient(pykube.KubeConfig.from_service_account())

        self._nodes_query = pykube.Node.objects(api)

    def _get_node_data(self, node):
        try:
            iips = [a for a in node.obj['status']['addresses'] if a['type'] == 'InternalIP']
            if not iips:
                logging.error("no IP address found for node {0}".format(node.name))
                return None
            return dict(name=node.name, ip=iips[0]['address'])
        except KeyError:
            logging.error("no IP address found for node {0}".format(node.name))
            return None

    def get_config_variables(self):

        target_nodes = [n for n in self._nodes_query if target_node_name_pattern.match(n.name)]
        # assert target_nodes, "no target nodes found"
        target_nodes = filter(bool, [self._get_node_data(n) for n in target_nodes])

        return dict(
            target_nodes=list(target_nodes),
            port_mappings=port_mappings
        )


class DebugConfigSource:

    def __init__(self, filename):
        self._filename = filename

    def get_config_variables(self):
        js = json.load(open(self._filename))
        return dict(
            target_nodes=list(js),
            port_mappings=port_mappings
        )


if args.nodes_json:
    config_source = DebugConfigSource(args.nodes_json)
else:
    config_source = K8SConfigSource()

target_node_name_pattern = re.compile(args.target)

from jinja2 import Environment, FileSystemLoader

script_dir = os.path.dirname(os.path.realpath(__file__))
env = Environment(loader=FileSystemLoader([script_dir]))
proxy_conf_template = env.get_template('haproxy.cfg.template')

proxy_pid = 0

def update_proxy(config_variables):
    global proxy_pid

    config = proxy_conf_template.render(config_variables)

    if args.debug:
        print(config)
        return

    with open(args.config, 'w') as cf:
        cf.write(config)

    if proxy_pid:
        os.kill(proxy_pid, signal.SIGHUP)
    else:
        proxy_pid = os.fork()
        if proxy_pid == 0:
            try:
                # the -p /run/haproxy.pid is needed so haproxy writes its pid into that. The haproxy-systemd-wrapper,
                #  when we send it a SIGHUP, reads the pid to pass to haproxy -sf from that file.
                os.execlp(args.exec, args.exec, "-p", "/run/haproxy.pid", "-f", args.config)
            except:
                logging.error("Failed to run {0} {1} {2}: {3}\n".format(args.exec, "-f", args.config, traceback.format_exc()))
                os._exit(1)

previous_config = None

while True:
    try:
        config = config_source.get_config_variables()
        if config != previous_config:
            previous_config = config
            update_proxy(config)
    except:
        logging.error("Unexpected error: {0}\n".format(traceback.format_exc()))

    time.sleep(args.interval)
