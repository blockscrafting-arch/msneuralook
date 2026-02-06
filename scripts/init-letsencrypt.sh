#!/bin/sh
# One-time: create certbot volumes and get certificate for n8n.neurascope.pro
# Run from project root. Requires nginx to be running and domain pointing to server.
# Usage: ./scripts/init-letsencrypt.sh

set -e
DOMAIN=n8n.neurascope.pro
EMAIL=admin@neurascope.pro

# Use same volume names as docker-compose (parser_* when project name is parser)
docker run -it --rm \
  -v "parser_certbot_www:/var/www/certbot" \
  -v "parser_certbot_conf:/etc/letsencrypt" \
  certbot/certbot certonly --webroot -w /var/www/certbot \
  -d "$DOMAIN" --email "$EMAIL" --agree-tos --no-eff-email
echo "Certificate obtained. Add n8n.ssl.conf to nginx and reload."
