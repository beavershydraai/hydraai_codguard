# Asterisk on the VM: softphone testing

This folder runs Asterisk on the VM (`codguard-asterisk`) and sets up softphone accounts, so the team can test calls without the phone network. See [docs/call-controller.md](../../docs/call-controller.md) for how the VM fits in.

| File | What it is |
|---|---|
| `Dockerfile`, `docker-compose.yml` | Asterisk 20 from Alpine's packages, on the VM's own network |
| `dev-setup.sh` | Softphone accounts and test extensions |

What `dev-setup.sh` does:

- Adds a SIP transport on the VM's Cloudflare Mesh IP, port **5070**. It is reachable only from devices enrolled in our Zero Trust org. The public transport on port 5060 (Twilio) is not touched.
- Creates one account per extension (default `6001`) with a random password. A re-run keeps existing passwords.
- Adds test extensions in the dialplan context `codguard-dev`:

| Dial | What happens |
|---|---|
| `200` | Echo test: you hear yourself |
| `300` | Plays the audio file |
| `301` | Plays the audio file, waits for one key, reads the key back (and logs `CODGUARD DTMF: <key>`) |

- Converts the audio file you give it (WAV or MP3) to 8 kHz mono. Without a file, it plays Asterisk's demo prompt.

The script writes `pjsip_codguard_dev.conf` and `extensions_codguard_dev.conf` next to Asterisk's config and adds an `#include` for each. It works with Asterisk on the host or in a Docker container that uses host networking.

## 1. Put the VM on Cloudflare Mesh (once)

In Zero Trust, add the VM as a Mesh node and copy its token. Then give the VM its own device profile:

| Setting | Value |
|---|---|
| Rule | User email is `warp_connector@<team>.cloudflareaccess.com` |
| Service mode | Traffic only |
| Split tunnels | Include mode, only `100.96.0.0/12` |
| Order | Above the other profiles, so it matches first |

Otherwise all of the VM's traffic goes through Cloudflare, and Twilio and Google APIs see the wrong source IP.

The profile for people's laptops and phones must also send `100.96.0.0/12` through Cloudflare. In Exclude mode, check that no excluded range covers it: the default list has `100.64.0.0/10`, which does.

On the VM:

```bash
curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg | sudo gpg --yes --dearmor -o /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] https://pkg.cloudflareclient.com/ $(. /etc/os-release; echo "$VERSION_CODENAME") main" |
  sudo tee /etc/apt/sources.list.d/cloudflare-client.list
sudo apt-get update && sudo apt-get install -y --no-install-recommends cloudflare-warp
sudo warp-cli --accept-tos connector new <TOKEN>
sudo warp-cli connect
ip -4 addr | grep 100.9      # the Mesh IP
curl -4 ifconfig.me          # must still be the VM's public IP
```

`--no-install-recommends` skips about 400 desktop packages that the VM does not need.

## 2. Run Asterisk

Copy this folder to the VM (for example with SFTP), then from inside it:

```bash
sudo docker compose up -d --build
```

Without the Compose plugin, the same with plain Docker:

```bash
sudo docker build -t codguard-asterisk .
sudo docker run -d --name asterisk --network host --restart unless-stopped \
  -v asterisk-etc:/etc/asterisk -v asterisk-lib:/var/lib/asterisk \
  -v asterisk-spool:/var/spool/asterisk -v asterisk-log:/var/log/asterisk \
  codguard-asterisk
```

The container uses the VM's network (SIP and RTP need the VM's own addresses, including the Mesh IP), and RTP stays on ports 10000-10100. Config, sounds and logs live in the `asterisk-*` volumes, so they survive a rebuild. Both ways use the same volumes.

Asterisk console: `sudo docker exec -it asterisk asterisk -rvvv`.

## 3. Run the script

```bash
sudo ./dev-setup.sh my-prompt.wav                              # one account, 6001
sudo EXTENSIONS="6001 6002 6003" ./dev-setup.sh my-prompt.wav  # one account per teammate
```

It converts the audio file with sox (on the VM, or inside the container if the VM has none) and prints each account's password and the server address (`<Mesh IP>:5070`).

## 4. Set up Zoiper

On a laptop or a phone, install the Cloudflare One client and sign in to the org, then install Zoiper 5.

| Setting | Value |
|---|---|
| Username / Password | `6001` / printed by the script |
| Domain / Server | `<Mesh IP>:5070` |
| Transport | UDP |
| STUN | Disabled |
| Codec | u-law (G.711) |
| DTMF | RFC-2833 |

Zoiper shows the account as registered, and `sudo docker exec asterisk asterisk -rx "pjsip show contacts"` lists it as available. Then dial `200`, `300` and `301`.

To have Asterisk call the softphone, as it will call a buyer:

```bash
sudo docker exec asterisk asterisk -rx "channel originate PJSIP/6001 extension 301@codguard-dev"
```

Keep Zoiper open in the foreground on a phone: the free app may not ring while it is in the background.

On Windows, allow calls in from the Mesh once, in PowerShell as administrator:

```powershell
New-NetFirewallRule -DisplayName "Zoiper via Cloudflare Mesh" -Direction Inbound -Protocol UDP -RemoteAddress 100.96.0.0/12 -Action Allow
```

## 5. Talk to the Gemini agent

The script also turns on ARI for the call controller: HTTP on `127.0.0.1:8088` only, user `codguard`, password kept across re-runs. It replaces Asterisk's `http.conf` and `ari.conf` (the originals stay as `*.orig`) and writes the controller's settings to `/etc/codguard/controller.env` (root only).

To have the Gemini agent call your softphone with a sample order, follow "Try a Gemini call from a softphone" in [docs/call-controller.md](../../docs/call-controller.md).

## 6. Run the call controller

The controller takes call jobs from the backend and places them through this Asterisk (docs/call-controller.md). It runs the backend image, so the VM must be able to pull it: `sudo gcloud auth configure-docker asia-southeast1-docker.pkg.dev` once.

```bash
sudo docker compose pull controller && sudo docker compose up -d controller
sudo docker logs -f codguard-controller
```

It is in the Compose profile `controller`, so a plain `docker compose up` starts only Asterisk. Run the same two commands after each merge to `main` to update it.

## Troubleshooting

| Problem | Check |
|---|---|
| Zoiper: request timeout | The device is not connected to Zero Trust, the server address is wrong, or the device's profile excludes `100.96.0.0/12` |
| Zoiper: 401 or 403 | Username or password |
| Call connects, no audio | STUN is on in Zoiper, or the codec is not u-law |
| Asterisk's call does not ring on Windows | The firewall rule above |
| `300` hangs up at once | Asterisk could not find the file: the Asterisk console shows the error |
| Keys do nothing on `301` | Zoiper DTMF must be RFC-2833 |
| The script stops at "ARI did not start" | `sudo docker exec asterisk asterisk -rx "http show status"`: ARI needs `res_ari` and the HTTP server on 127.0.0.1:8088 |
| The script stops at "dialplan did not load" | `sudo docker exec asterisk asterisk -rx "dialplan show codguard-dev"` |
