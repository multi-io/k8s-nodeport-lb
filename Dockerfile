FROM haproxy:1.7.1

LABEL description="Meant to run in a Kubernetes cluster in the host network. \
Runs haproxy, accepting incoming connections and forwarding them to some ports on some nodes"

MAINTAINER Olaf Klischat <o.klischat@syseleven.de>

RUN apt-get update && apt-get install -y python3-pip && pip3 install --upgrade pip && rm -rf /var/lib/apt/lists/*

COPY manage_lb_continuously.py haproxy.cfg.template requirements.txt /
RUN pip install -U -r /requirements.txt

ENTRYPOINT ["/manage_lb_continuously.py"]
CMD ["-t", "^node", "-p", "80:30000"]
