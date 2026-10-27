FROM debian:bookworm-slim

ARG TARGETARCH
# Vaste versie: verhoog deze (en "version" in config.yaml) om cloudflared bij te werken.
ARG CLOUDFLARED_VERSION=2026.10.4

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl jq \
    && curl -fsSL -o /usr/local/bin/cloudflared \
       "https://github.com/cloudflare/cloudflared/releases/download/${CLOUDFLARED_VERSION}/cloudflared-linux-${TARGETARCH}" \
    && chmod +x /usr/local/bin/cloudflared \
    && apt-get purge -y curl \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]
