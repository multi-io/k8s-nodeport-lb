#!/usr/bin/env python
# creates a container on a specific node (proxy node) that runs a haproxy instance in the
# host network that listens on some TCP port(s) on the proxy node and forwards (load-balances)
# all connections to some ports on some target nodes.
# Continuously tracks existing nodes and updates the haproxy container if anything changes.

### config

target_namespace = 'default'

proxy_node_name = 'node0'
target_node_name_pattern = '^node'

# TODO: also allow for name-based mapping (virtual hosting)

port_mappings = {
    80: 30000
}

interval = 30 # todo events/notifications?

###

import pykube
import re
import os
import sys
import time

#api = pykube.HTTPClient(pykube.KubeConfig.from_service_account())
api = pykube.HTTPClient(pykube.KubeConfig.from_file(os.path.dirname(os.path.realpath(__file__)) + "/../admin.conf"))

nodes_query = pykube.Node.objects(api)

try:
    nodes_query.get_by_name(proxy_node_name)
except pykube.ObjectDoesNotExist:
    sys.stderr.write("warning: proxy node {0} currently not found\n".format(proxy_node_name))

target_node_name_pattern = re.compile(target_node_name_pattern)

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
        proxy_node_name = proxy_node_name,
        target_nodes    = list(target_nodes),
        port_mappings   = port_mappings
    )

def update_proxy(config_variables):
    print(config_variables)

previous_config = None

while True:
    config = get_config_variables()
    if config != previous_config:
        previous_config = config
        update_proxy(config)

    time.sleep(interval)
