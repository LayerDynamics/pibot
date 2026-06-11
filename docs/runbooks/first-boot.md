# Runbook — First boot & passwordless SSH

A freshly flashed Pi has no account and no authorized key, so the suite embeds your SSH
public key (and hostname/user) into the image at flash time. This avoids the
"publickey-only, key not authorized" lockout entirely.

## Embed your key at flash time

The mechanism differs by OS and the suite picks the right one:

- **Ubuntu** → `cloud-init` user-data (`#cloud-config` with `ssh_authorized_keys`).
- **Raspberry Pi OS** → `custom.toml` first-boot config (user + `ssh.authorized_keys`).

```bash
pibot flash --device /dev/disk4 \
  --image ~/images/ubuntu-24.04.img.xz \
  --os ubuntu \
  --hostname pibot \
  --username ubuntu \
  --authorized-key-file ~/.ssh/id_ed25519.pub \
  --confirm
```

See [flash.md](flash.md) for the full flashing procedure (removable vs onboard NVMe).

## If you're already locked out (key not authorized)

Reflash with the key embedded (above), or install the key once a password login exists:

```bash
pibot keys install pibot --dry-run    # preview the authorized_keys edit
pibot keys install pibot              # prompts for the password once, then records the identity
```

## Verify

The Pi should accept your key without a password on first contact:

```bash
pibot discover                 # the Pi appears with its hostname
pibot run pibot -- whoami      # passwordless; prints the first user (ubuntu / pi)
```
