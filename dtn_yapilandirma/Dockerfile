FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates git build-essential cmake pkg-config \
    python3 python3-pip python3-venv python3-dev \
    iproute2 procps iputils-ping tcpdump \
    && rm -rf /var/lib/apt/lists/*

# Build µD3TN
RUN git clone --depth 1 --branch v0.15.0 https://github.com/umr-ds/uD3TN.git /opt/ud3tn \
    && make -C /opt/ud3tn posix -j"$(nproc)" \
    && test -x /opt/ud3tn/build/posix/ud3tn \
    && ln -sf /opt/ud3tn/build/posix/ud3tn /usr/local/bin/ud3tn

# AAP2 client utilities used by takvim_yukle.py through docker exec
RUN python3 -m venv /opt/ud3tn-venv \
    && /opt/ud3tn-venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/ud3tn-venv/bin/pip install --no-cache-dir pyd3tn==0.15.0 ud3tn-utils==0.15.0 \
    && ln -sf /opt/ud3tn-venv/bin/aap2-config /usr/local/bin/aap2-config

WORKDIR /proje

# Intentionally no ENTRYPOINT: Compose starts the network setup script,
# which should finish with: exec "$@"
