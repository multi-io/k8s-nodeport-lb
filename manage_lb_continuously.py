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

parser = argparse.ArgumentParser()

parser.add_argument('-d', '--debug', action='store_true', help='debug mode')
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

args = parser.parse_args()

port_mappings = []
pm_pat = re.compile('([0-9]+):([0-9]+)')
for pm in args.port_mappings:
    m = pm_pat.match(pm)
    assert m, "Illegal port mapping: {0}".format(pm)
    port_mappings.append(dict(proxy_port=int(m.group(1)), dest_port=int(m.group(2))))

if args.kube_conf:
    api = pykube.HTTPClient(pykube.KubeConfig.from_file(args.kube_conf))
else:
    api = pykube.HTTPClient(pykube.KubeConfig.from_service_account())

nodes_query = pykube.Node.objects(api)

target_node_name_pattern = re.compile(args.target)

def get_config_variables():

    def get_node_data(node):
        try:
            iips = [a for a in node.obj['status']['addresses'] if a['type'] == 'InternalIP']
            if not iips:
                sys.stderr.write("no IP address found for node {0}".format(node.name))
                return None
            return dict(name=node.name, ip=iips[0]['address'])
        except KeyError:
            sys.stderr.write("no IP address found for node {0}".format(node.name))
            return None

    target_nodes = [n for n in nodes_query if target_node_name_pattern.match(n.name)]
    #assert target_nodes, "no target nodes found"
    target_nodes = filter(bool, [get_node_data(n) for n in target_nodes])

    return dict(
        target_nodes    = list(target_nodes),
        port_mappings   = port_mappings
    )


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
                os.execlp(args.exec, args.exec, "-f", args.config)
            except:
                sys.stderr.write("Failed to run {0} {1} {2}: {3}\n".format(args.exec, "-f", args.config, traceback.format_exc()))
                os._exit(1)

previous_config = None

while True:
    try:
        config = get_config_variables()
        if config != previous_config:
            previous_config = config
            update_proxy(config)
    except:
        sys.stderr.write("Unexpected error: {0}\n".format(traceback.format_exc()))

    time.sleep(args.interval)
