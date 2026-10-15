#!/usr/bin/env bash
# Softphone test setup for the Asterisk VM (dev only). Safe to re-run.
#
#   sudo ./dev-setup.sh [audio-file]
#
# Creates SIP accounts for softphones (Zoiper, Linphone) on a separate transport bound to the
# VM's Cloudflare Mesh IP, port 5070, so they are reachable only from devices enrolled in Zero
# Trust. The Twilio side (port 5060) is left untouched. Test extensions:
#   200  echo test
#   300  plays the audio file
#   301  plays the audio file, waits for one key, reads the key back
# Asterisk can also call a softphone:  asterisk -rx "channel originate PJSIP/6001 extension 301@codguard-dev"
# It also turns on ARI on 127.0.0.1:8088 for the call controller and writes the controller's
# settings to /etc/codguard/controller.env (docs/call-controller.md).
#
# Options (environment):
#   EXTENSIONS="6001 6002"   accounts to create (default 6001)
#   BIND_IP=100.96.x.x       address for the softphone transport (default: the Mesh IP)
#   SIP_PORT=5070            port for the softphone transport
# audio-file: any WAV or MP3; converted to 8 kHz mono. Without it, Asterisk's demo prompt plays.
set -euo pipefail

EXTENSIONS=${EXTENSIONS:-6001}
SIP_PORT=${SIP_PORT:-5070}
AUDIO=${1:-}
CONTEXT=codguard-dev
TRANSPORT=codguard-dev-transport
PJSIP_FILE=pjsip_codguard_dev.conf
DIALPLAN_FILE=extensions_codguard_dev.conf

die() { echo "ERROR: $*" >&2; exit 1; }
[[ $EUID -eq 0 ]] || die "run with sudo"

# Asterisk runs on the host or in a Docker container; RUN is the prefix to reach it.
RUN=()
if command -v asterisk >/dev/null 2>&1 && asterisk -rx "core show version" >/dev/null 2>&1; then
  WHERE="host"
elif command -v docker >/dev/null 2>&1; then
  C=$(docker ps --format '{{.Names}} {{.Image}}' | awk 'tolower($0) ~ /asterisk/ {print $1; exit}')
  [[ -n "$C" ]] || die "Asterisk is not running on this VM (no asterisk process or container)"
  RUN=(docker exec -i "$C")
  WHERE="container $C"
  [[ "$(docker inspect -f '{{.HostConfig.NetworkMode}}' "$C")" == host ]] ||
    echo "WARNING: container $C does not use host networking; SIP and RTP will not reach it."
else
  die "Asterisk is not running on this VM"
fi
inside() { "${RUN[@]}" "$@"; }
ast() { inside asterisk -rx "$1"; }
setting() { ast "core show settings" | awk -F': +' -v k="$1" '$1 ~ k {print $2; exit}'; }

CONF=$(setting "Configuration directory")
VARLIB=$(setting "VarLib directory")
[[ -n "$CONF" && -n "$VARLIB" ]] || die "could not read Asterisk settings"
echo "Asterisk: $(ast 'core show version' | awk '{print $2; exit}') on $WHERE, config in $CONF"

if [[ -z "${BIND_IP:-}" ]]; then
  BIND_IP=$(ip -4 -o addr show | awk '{split($4, a, "/"); print a[1]}' |
    grep -E '^100\.(9[6-9]|10[0-9]|11[01])\.' | head -1 || true)
  [[ -n "$BIND_IP" ]] || die "no Cloudflare Mesh address (100.96.0.0/12) on this VM.
  Install the Mesh node first (Zero Trust > Networks > Mesh > add a node), or pass BIND_IP=<address>."
fi

# Keep each account's password across re-runs, so softphones stay registered.
old_password() {
  inside sh -c "cat '$CONF/$PJSIP_FILE' 2>/dev/null" |
    awk -v s="[$1-auth]" '$0 == s {f = 1; next} /^\[/ {f = 0} f && /^password=/ {sub(/^password=/, ""); print; exit}' || true
}

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
declare -A PASSWORDS
{
  echo "; Softphone accounts for testing. Written by infra/asterisk/dev-setup.sh; edits are overwritten."
  echo "[$TRANSPORT]"
  echo "type=transport"
  echo "protocol=udp"
  echo "bind=$BIND_IP:$SIP_PORT"
  echo
  echo "[codguard-dev-endpoint](!)"
  echo "type=endpoint"
  echo "transport=$TRANSPORT"
  echo "context=$CONTEXT"
  echo "disallow=all"
  echo "allow=ulaw,alaw"
  echo "dtmf_mode=rfc4733"
  echo "direct_media=no"
  echo "rtp_symmetric=yes"
  echo "force_rport=yes"
  echo "rewrite_contact=yes"
  echo "media_address=$BIND_IP"
  echo "language=en"
  for ext in $EXTENSIONS; do
    [[ "$ext" =~ ^[0-9]{3,6}$ ]] || die "extension '$ext' must be 3 to 6 digits"
    pw=$(old_password "$ext")
    [[ -n "$pw" ]] || pw=$(head -c 18 /dev/urandom | base64 | tr -d '/+=' | head -c 20)
    PASSWORDS[$ext]=$pw
    echo
    echo "[$ext](codguard-dev-endpoint)"
    echo "auth=$ext-auth"
    echo "aors=$ext"
    echo
    echo "[$ext-auth]"
    echo "type=auth"
    echo "auth_type=userpass"
    echo "username=$ext"
    echo "password=$pw"
    echo
    echo "[$ext]"
    echo "type=aor"
    echo "max_contacts=2"
    echo "remove_existing=yes"
    echo "qualify_frequency=30"
  done
} > "$tmp/$PJSIP_FILE"

# Prompt: the given audio file, or Asterisk's own demo prompt.
PROMPT=demo-congrats
if [[ -n "$AUDIO" ]]; then
  [[ -f "$AUDIO" ]] || die "audio file not found: $AUDIO"
  if command -v sox >/dev/null 2>&1; then
    sox "$AUDIO" -r 8000 -c 1 -b 16 "$tmp/codguard-demo.wav"
  elif command -v ffmpeg >/dev/null 2>&1; then
    ffmpeg -loglevel error -y -i "$AUDIO" -ar 8000 -ac 1 -c:a pcm_s16le "$tmp/codguard-demo.wav"
  elif [[ ${#RUN[@]} -gt 0 ]] && inside sh -c "command -v sox" >/dev/null 2>&1; then
    # The image in this folder has sox: convert inside the container.
    in="/tmp/codguard-in.${AUDIO##*.}"
    inside sh -c "cat > '$in'" < "$AUDIO"
    inside sox "$in" -r 8000 -c 1 -b 16 -t wav - > "$tmp/codguard-demo.wav"
    inside rm -f "$in"
  else
    die "install sox to convert the audio file: apt-get install -y sox"
  fi
  inside mkdir -p "$VARLIB/sounds/custom"
  inside sh -c "cat > '$VARLIB/sounds/custom/codguard-demo.wav'" < "$tmp/codguard-demo.wav"
  inside sh -c "chown asterisk: '$VARLIB/sounds/custom/codguard-demo.wav' 2>/dev/null || true"
  PROMPT="$VARLIB/sounds/custom/codguard-demo"
fi

cat > "$tmp/$DIALPLAN_FILE" <<'EOF'
; Test extensions for softphones. Written by infra/asterisk/dev-setup.sh; edits are overwritten.
[codguard-dev]
exten => 200,1,Answer()
 same => n,Echo()

exten => 300,1,Answer()
 same => n,Wait(1)
 same => n,Playback(@PROMPT@)
 same => n,Hangup()

exten => 301,1,Answer()
 same => n,Wait(1)
 same => n,Read(DIGIT,@PROMPT@,1,,2,5)
 same => n,Verbose(1,CODGUARD DTMF: ${DIGIT})
 same => n,GotoIf($["${DIGIT}" = ""]?end)
 same => n,SayDigits(${DIGIT})
 same => n(end),Hangup()
EOF
sed -i "s|@PROMPT@|$PROMPT|g" "$tmp/$DIALPLAN_FILE"

for f in "$PJSIP_FILE:pjsip.conf" "$DIALPLAN_FILE:extensions.conf"; do
  file=${f%%:*} main=${f##*:}
  inside sh -c "cat > '$CONF/$file'" < "$tmp/$file"
  inside sh -c "grep -qx '#include $file' '$CONF/$main' || printf '\n#include %s\n' '$file' >> '$CONF/$main'"
done

# ARI for the call controller (docs/call-controller.md): HTTP on 127.0.0.1 only, one user.
# Asterisk's own http.conf and ari.conf are replaced; the originals are kept once as *.orig.
ARI_USER=codguard
ari_password() {
  inside sh -c "cat '$CONF/ari.conf' 2>/dev/null" |
    awk -v s="[$ARI_USER]" '$0 == s {f = 1; next} /^\[/ {f = 0} f && /^password=/ {sub(/^password=/, ""); print; exit}' || true
}
ARI_PASSWORD=$(ari_password)
[[ -n "$ARI_PASSWORD" ]] || ARI_PASSWORD=$(head -c 24 /dev/urandom | base64 | tr -d '/+=' | head -c 24)
for f in http.conf ari.conf; do
  inside sh -c "[ -f '$CONF/$f.orig' ] || cp '$CONF/$f' '$CONF/$f.orig' 2>/dev/null || true"
done
inside sh -c "cat > '$CONF/http.conf'" <<EOF
; Written by infra/asterisk/dev-setup.sh: ARI for the call controller, local only.
[general]
enabled=yes
bindaddr=127.0.0.1
bindport=8088
EOF
inside sh -c "cat > '$CONF/ari.conf'" <<EOF
; Written by infra/asterisk/dev-setup.sh. The password is also in /etc/codguard/controller.env.
[general]
enabled=yes

[$ARI_USER]
type=user
read_only=no
password=$ARI_PASSWORD
EOF

ast "pjsip reload" >/dev/null
ast "dialplan reload" >/dev/null
ast "module reload http" >/dev/null
ast "module reload res_ari.so" >/dev/null
# A reload can take several seconds when the sample configs are large.
retry() { for _ in $(seq 1 20); do "$@" && return 0; sleep 1; done; return 1; }
transport_up() { ast "pjsip show transports" | grep -q "$TRANSPORT"; }
dialplan_up() { ast "dialplan show 301@$CONTEXT" | grep -q Read; }
retry transport_up ||
  die "transport $TRANSPORT did not start: is $BIND_IP:$SIP_PORT free? Check: asterisk -rx 'pjsip show transports'"
retry dialplan_up || die "dialplan $CONTEXT did not load. Check: asterisk -rx 'dialplan show $CONTEXT'"
ari_up() { ast "ari show users" | grep -qw "$ARI_USER" && ast "http show status" | grep -q "127.0.0.1:8088"; }
retry ari_up || die "ARI did not start. Check: asterisk -rx 'http show status'; asterisk -rx 'module show like res_ari'"

# Settings for the call controller and app.telephony.dial (docker run --env-file).
mkdir -p /etc/codguard
(
  umask 077
  cat > /etc/codguard/controller.env <<EOF
ARI_URL=http://127.0.0.1:8088
ARI_USER=$ARI_USER
ARI_PASSWORD=$ARI_PASSWORD
CONTROLLER_ID=codguard-asterisk
GOOGLE_CLOUD_PROJECT=${GOOGLE_CLOUD_PROJECT:-ai-codguard}
GEMINI_LIVE_LOCATION=${GEMINI_LIVE_LOCATION:-us-central1}
GEMINI_LIVE_MODEL=${GEMINI_LIVE_MODEL:-gemini-3.8-live}
EOF
)

echo
echo "Ready. Softphone settings (Zoiper: account type SIP, transport UDP, STUN off, codec u-law, DTMF RFC-2833):"
for ext in $EXTENSIONS; do
  printf '  user %s   password %s   server %s:%s\n' "$ext" "${PASSWORDS[$ext]}" "$BIND_IP" "$SIP_PORT"
done
echo "Dial 200 (echo), 300 (prompt) or 301 (prompt + key)."
first=${EXTENSIONS%% *}
prefix=""
[[ ${#RUN[@]} -gt 0 ]] && prefix="docker exec $C "
echo "Have Asterisk call the softphone: sudo ${prefix}asterisk -rx \"channel originate PJSIP/$first extension 301@$CONTEXT\""
echo "Registered? sudo ${prefix}asterisk -rx \"pjsip show contacts\""
echo "ARI is on 127.0.0.1:8088; the controller's settings are in /etc/codguard/controller.env."
echo "Gemini call to $first: sudo docker run --rm --network host --env-file /etc/codguard/controller.env \\"
echo "  asia-southeast1-docker.pkg.dev/ai-codguard/codguard/backend:main python -m app.telephony.dial $first"
