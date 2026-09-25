# PM Research Ledger — browser side panel extension

Chrome/Edge/Brave (Manifest V3) side-panel extension showing the live paper-
trading ledger from the pbquant server. Read-only: it fetches `ledger.json`
and `prices.json` from the dashboard (LAN `192.168.50.88:8794`, falling back
to Tailscale `100.125.213.17:8794`) and refreshes every 60 s. It places no
trades and holds no credentials.

## Install (unpacked)

1. Open `chrome://extensions` (or `edge://extensions`).
2. Enable **Developer mode** (top right).
3. Click **Load unpacked** and select this `extension/` folder
   (or unzip `pm-ledger-extension.zip` and select the unzipped folder).
4. Click the puzzle-piece icon → pin **PM Research Ledger**.
5. Click its toolbar icon — the ledger opens in the browser side panel and
   stays there while you browse.

## Notes

- Works away from home over Tailscale automatically (LAN is tried first).
- "offline: no endpoint reachable" means neither the LAN nor the Tailscale
  address answered — check that the `pm-research-dashboard` container is up
  and, remotely, that Tailscale is connected.
- Firefox uses a different sidebar API (`sidebar_action`) and is not covered
  by this manifest.
