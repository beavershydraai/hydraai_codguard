# Asterisk on the VM: softphone testing

`dev-setup.sh` sets up softphone accounts on the Asterisk VM (`codguard-asterisk`), so the team can test calls without the phone network. See [docs/call-controller.md](../../docs/call-controller.md) for how the VM fits in.

What it does:

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

In Zero Trust, add the VM as a Mesh node and copy its token. Give the VM a device profile whose split tunnel **includes only `100.96.0.0/12`**. Otherwise all of the VM's traffic goes through Cloudflare, and Twilio and Google APIs see the wrong source IP.

```bash
curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg | sudo gpg --yes --dearmor -o /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] https://pkg.cloudflareclient.com/ $(. /etc/os-release; echo "$VERSION_CODENAME") main" |
  sudo tee /etc/apt/sources.list.d/cloudflare-client.list
sudo apt-get update && sudo apt-get install -y cloudflare-warp
sudo warp-cli --accept-tos connector new <TOKEN>
sudo warp-cli connect
ip -4 addr | grep 100.9      # the Mesh IP
curl -4 ifconfig.me          # must still be 34.60.118.169
```

## 2. Run the script

Copy this folder to the VM (for example with SFTP), then:

```bash
sudo apt-get install -y sox                                  # only needed for your own audio file
sudo ./dev-setup.sh my-prompt.wav                            # one account, 6001
sudo EXTENSIONS="6001 6002 6003" ./dev-setup.sh my-prompt.wav  # one account per teammate
```

It prints each account's password and the server address (`<Mesh IP>:5070`).

## 3. Set up Zoiper

On a laptop or a phone, install the Cloudflare One client and sign in to the org, then install Zoiper 5.

| Setting | Value |
|---|---|
| Username / Password | `6001` / printed by the script |
| Domain / Server | `<Mesh IP>:5070` |
| Transport | UDP |
| STUN | Disabled |
| Codec | u-law (G.711) |
| DTMF | RFC-2833 |

Zoiper shows the account as registered; on the VM, `sudo asterisk -rx "pjsip show contacts"` lists it as available. Then dial `200`, `300` and `301`.

To have Asterisk call the softphone, as it will call a buyer:

```bash
sudo asterisk -rx "channel originate PJSIP/6001 extension 301@codguard-dev"
```

Keep Zoiper open in the foreground on a phone: the free app may not ring while it is in the background.

## Troubleshooting

| Problem | Check |
|---|---|
| Zoiper: request timeout | The device is not connected to Zero Trust, or the server address is wrong |
| Zoiper: 401 or 403 | Username or password |
| Call connects, no audio | STUN is on in Zoiper, or the codec is not u-law |
| `300` hangs up at once | Asterisk could not find the file: `sudo asterisk -rvvv` shows the error |
| Keys do nothing on `301` | Zoiper DTMF must be RFC-2833 |
