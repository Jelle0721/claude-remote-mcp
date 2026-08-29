#!/usr/bin/env sh
set -e

TOKEN=$(jq -r '.tunnel_token // empty' /data/options.json)

if [ -z "$TOKEN" ]; then
    echo "FOUT: tunnel_token is niet ingesteld. Vul 'm in via de add-on configuratie" \
         "(kopieer de token uit het 'docker run' commando dat Cloudflare je gaf" \
         "bij het aanmaken van de tunnel)."
    exit 1
fi

exec cloudflared tunnel --no-autoupdate run --token "$TOKEN"
