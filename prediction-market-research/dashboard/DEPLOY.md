# Dashboard deployment (pbquant-v2-core-vm)

Deployed as an isolated static-nginx container; the web root is a host
directory so ledger updates are plain file copies (no rebuild).

    # web root
    mkdir -p /opt/pbSolutions/prediction-market-research/www
    cp index.html ledger.json /opt/pbSolutions/prediction-market-research/www/

    # container (image already present on host for ml-omega-ui)
    docker run -d --name pm-research-dashboard --restart unless-stopped \
      -v /opt/pbSolutions/prediction-market-research/www:/usr/share/nginx/html:ro \
      -p 192.168.50.88:8794:80 -p 100.125.213.17:8794:80 \
      nginx:1.27-alpine

    # update after each research session
    cp ledger.json /opt/pbSolutions/prediction-market-research/www/ledger.json

Access: http://192.168.50.88:8794 (LAN) · http://100.125.213.17:8794 (Tailscale).
Port 8794 chosen as unused at deploy time. LAN/Tailscale binds only — not
exposed on the public interface (192.168.1.90) or via cloudflared.
