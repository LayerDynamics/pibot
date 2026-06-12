# Runbook — Nebula overlay (Mac ↔ Pi remote access)

PiBot uses a [Nebula](https://github.com/slackhq/nebula) overlay (replacing ZeroTier) to
give the Mac (M4 Max policy box) and the Pi (robot brain) stable, encrypted addresses that
work from anywhere — so `pibot` and the openpi policy link keep working off-LAN. Nebula is
certificate-based and self-hosted: the **Pi is the lighthouse**, the Mac is a node.

| Node | Overlay IP | Role |
|------|-----------|------|
| Mac  | `192.168.100.1` | policy server node |
| Pi   | `192.168.100.2` | lighthouse + robot brain |

The ESP32 stays on plain Wi-Fi (a microcontroller can't run an overlay client); the Pi
bridges to it on the LAN. Certs/keys live in `~/.config/pibot/nebula/` (machine-local,
never committed).

## 1. Mac (already set up)

`nebula` is installed and the CA + node certs are generated. Start it (needs root to
create the tun device):

```bash
sudo nebula -config ~/.config/pibot/nebula/mac-config.yml
```

To run it on login, install a LaunchDaemon that runs the same command (optional).

## 2. Pi (lighthouse)

Copy the prepared bundle to the Pi and install it. The Pi 5 is `aarch64`, so use the
arm64 Nebula build:

```bash
# from the Mac: copy the bundle (ca.crt, pi.crt, pi.key, config.yml, nebula.service)
scp ~/.config/pibot/nebula/pibot-nebula-pi.tar.gz <user>@192.168.1.99:/tmp/

# on the Pi:
curl -fsSL -o /tmp/nebula.tar.gz \
  https://github.com/slackhq/nebula/releases/latest/download/nebula-linux-arm64.tar.gz
sudo tar -C /usr/local/bin -xzf /tmp/nebula.tar.gz nebula nebula-cert
sudo mkdir -p /etc/nebula && sudo tar -C /etc/nebula -xzf /tmp/pibot-nebula-pi.tar.gz
sudo install -m 644 /etc/nebula/nebula.service /etc/systemd/system/nebula.service
sudo systemctl daemon-reload && sudo systemctl enable --now nebula
```

## 3. Remote access (off-LAN)

The lighthouse must be reachable from the internet. Either:

- **Home router:** forward UDP `4242` to the Pi (`192.168.1.99`), then add your public IP
  to the Mac's `static_host_map` in `mac-config.yml`:
  `"192.168.100.2": ["192.168.1.99:4242", "<public-ip>:4242"]`; or
- **VPS lighthouse:** run a third Nebula node with a public IP as the lighthouse and point
  both the Mac and Pi at it (most robust for a mobile robot).

## 4. Point PiBot at the overlay address

Once both nodes are up, use the Pi's overlay IP so it works on- or off-LAN:

```toml
# ~/.config/pibot/config.toml
robot_host = "192.168.100.2"
```

## Verify

With Nebula running on both nodes, the Mac reaches the Pi over the overlay and `pibot`
works through it:

```bash
ping -c 3 192.168.100.2          # overlay reachability (Mac -> Pi lighthouse)
pibot run pibot -- hostname      # SSH to the Pi over the overlay address
```
