# nodeport-lb

This image is meant to be run in a Kubernetes cluster. It runs a haproxy
instance that's listening on some TCP ports and load balancing incoming HTTP
connections to a bunch of nodes in the cluster.

Configuration works mainly via the RUN parameters of the container (which
runs a wrapper script which runs haproxy). You'll usually change those to
suit your needs.

Example: The parameters: `["-t", "^node", "-p", "80:30000"]` start the proxy
listening on port 80, load balancing all incoming requests to port 30000
on all nodes whose names match the pattern `^node`.

The wrapper will notice (via the K8S API) when the set of nodes changes and
adjust the proxy accordingly.
