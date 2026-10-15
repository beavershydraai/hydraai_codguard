#!/usr/bin/env bash
# Twilio Elastic SIP Trunking for the Asterisk VM, so calls can ring real phones (CallTarget
# kind `pstn`, ARI endpoint PJSIP/<E.164>@twilio). Safe to re-run.
#
#   sudo TWILIO_TERMINATION_URI=<name>.pstn.twilio.com CALLER_ID=<Twilio number, E.164> ./trunk-setup.sh
#
# Adds a public UDP transport on port 5060 (the VM's internal address, advertising the static
# external one: GCP's one-to-one NAT) and the endpoint `twilio`. Twilio lets the VM in by its
# external IP (the trunk's IP Access Control List). With TWILIO_USERNAME set, the script also
# sends the trunk's Credential List login; it asks for the password (input hidden) and keeps it
# across re-runs. The softphone transport (dev-setup.sh, port 5070) is not touched.
# Only outbound calls are used: a call from Twilio to the VM (origination) is hung up.
#
# Options (environment):
#   TWILIO_TERMINATION_URI   required: the trunk's Termination SIP URI
#   CALLER_ID                required: the number the callee sees, a number on the Twilio account
#   TWILIO_USERNAME          optional: Credential List user name
#   SIP_PORT=5060            must match the firewall rule codguard-sip-from-twilio
#   BIND_IP, EXTERNAL_IP     default: read from the GCE metadata server
# Keep the caller ID and any team phone number out of the repo: pass them on the command line.
set -euo pipefail

TRUNK_URI=${TWILIO_TERMINATION_URI:-}
TRUNK_URI=${TRUNK_URI#sip:}
CALLER_ID=${CALLER_ID:-}
USERNAME=${TWILIO_USERNAME:-}
SIP_PORT=${SIP_PORT:-5060}
CONTEXT=codguard-twilio-in
TRANSPORT=codguard-twilio-transport
PJSIP_FILE=pjsip_codguard_twilio.conf
DIALPLAN_FILE=extensions_codguard_twilio.conf
# Twilio's signalling addresses (all edges); media comes from 168.86.128.0/18.
# https://www.twilio.com/docs/sip-trunking/ip-addresses
TWILIO_SIGNALING="54.172.60.0/30 54.244.51.0/30 54.171.127.192/30 35.156.191.128/30
  54.65.63.192/30 54.169.127.128/30 54.252.254.64/30 177.71.206.192/30"

die() { echo "ERROR: $*" >&2; exit 1; }
[[ $EUID -eq 0 ]] || die "run with sudo"
[[ "$TRUNK_URI" =~ ^[a-z0-9-]+\.pstn(\.[a-z0-9-]+)?\.twilio\.com$ ]] ||
  die "set TWILIO_TERMINATION_URI to the trunk's Termination SIP URI, like codguard-xyz.pstn.twilio.com"
[[ "$CALLER_ID" =~ ^\+[1-9][0-9]{7,14}$ ]] ||
  die "set CALLER_ID to a number on the Twilio account in E.164 form, like +1XXXXXXXXXX"
[[ -z "$USERNAME" || "$USERNAME" =~ ^[A-Za-z0-9._-]{1,64}$ ]] || die "TWILIO_USERNAME has odd characters"

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
    die "container $C does not use host networking; SIP and RTP from Twilio would not reach it"
else
  die "Asterisk is not running on this VM"
fi
inside() { "${RUN[@]}" "$@"; }
ast() { inside asterisk -rx "$1"; }
setting() { ast "core show settings" | awk -F': +' -v k="$1" '$1 ~ k {print $2; exit}'; }

CONF=$(setting "Configuration directory")
[[ -n "$CONF" ]] || die "could not read Asterisk settings"
echo "Asterisk: $(ast 'core show version' | awk '{print $2; exit}') on $WHERE, config in $CONF"

metadata() {
  curl -fsS -m 5 -H "Metadata-Flavor: Google" \
    "http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/$1" 2>/dev/null || true
}
BIND_IP=${BIND_IP:-$(metadata ip)}
EXTERNAL_IP=${EXTERNAL_IP:-$(metadata access-configs/0/external-ip)}
[[ -n "$BIND_IP" && -n "$EXTERNAL_IP" ]] ||
  die "no GCE metadata server: pass BIND_IP=<internal address> EXTERNAL_IP=<external address>"

# Twilio sends media to the ports in the SDP; the firewall rule codguard-rtp-from-twilio opens
# 10000-10100 only, as the image in this folder sets in rtp.conf.
rtp=$(ast "rtp show settings" | awk -F': +' '/Port start/ {s=$2} /Port end/ {e=$2} END {print s "-" e}')
[[ "$rtp" == "10000-10100" ]] ||
  echo "WARNING: Asterisk uses RTP ports $rtp, the firewall opens 10000-10100: callers may hear nothing."

PASSWORD=""
if [[ -n "$USERNAME" ]]; then
  PASSWORD=$(inside sh -c "cat '$CONF/$PJSIP_FILE' 2>/dev/null" |
    awk '$0 == "[twilio-auth]" {f = 1; next} /^\[/ {f = 0} f && /^password=/ {sub(/^password=/, ""); print; exit}' || true)
  if [[ -z "$PASSWORD" ]]; then
    read -rsp "Password of Twilio credential $USERNAME: " PASSWORD </dev/tty
    echo
    [[ -n "$PASSWORD" ]] || die "no password given"
  fi
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
(
  umask 077
  {
    echo "; Twilio Elastic SIP Trunking. Written by infra/asterisk/trunk-setup.sh; edits are overwritten."
    echo "[$TRANSPORT]"
    echo "type=transport"
    echo "protocol=udp"
    echo "bind=$BIND_IP:$SIP_PORT"
    echo "external_signaling_address=$EXTERNAL_IP"
    echo "external_media_address=$EXTERNAL_IP"
    for net in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 100.64.0.0/10 127.0.0.0/8; do
      echo "local_net=$net"
    done
    echo "allow_reload=yes"
    echo
    echo "[twilio]"
    echo "type=endpoint"
    echo "transport=$TRANSPORT"
    echo "context=$CONTEXT"
    echo "aors=twilio"
    echo "disallow=all"
    echo "allow=ulaw"
    echo "dtmf_mode=rfc4733"
    echo "direct_media=no"
    echo "rtp_symmetric=yes"
    echo "force_rport=yes"
    echo "from_user=$CALLER_ID"
    echo "from_domain=$TRUNK_URI"
    echo "send_pai=no"
    echo "send_rpid=no"
    echo "trust_id_outbound=no"
    echo "language=en"
    [[ -n "$USERNAME" ]] && echo "outbound_auth=twilio-auth"
    echo
    echo "[twilio]"
    echo "type=aor"
    echo "contact=sip:$TRUNK_URI"
    echo "qualify_frequency=0"
    echo
    echo "[twilio-identify]"
    echo "type=identify"
    echo "endpoint=twilio"
    for net in $TWILIO_SIGNALING; do
      echo "match=$net"
    done
    if [[ -n "$USERNAME" ]]; then
      echo
      echo "[twilio-auth]"
      echo "type=auth"
      echo "auth_type=userpass"
      echo "username=$USERNAME"
      echo "password=$PASSWORD"
    fi
  } > "$tmp/$PJSIP_FILE"
)

cat > "$tmp/$DIALPLAN_FILE" <<EOF
; Calls from Twilio to the VM are not used. Written by infra/asterisk/trunk-setup.sh; edits are overwritten.
[$CONTEXT]
exten => _[+0-9a-zA-Z].,1,Hangup(21)
exten => s,1,Hangup(21)
EOF

for f in "$PJSIP_FILE:pjsip.conf" "$DIALPLAN_FILE:extensions.conf"; do
  file=${f%%:*} main=${f##*:}
  inside sh -c "umask 077; cat > '$CONF/$file'" < "$tmp/$file"
  inside sh -c "chown asterisk: '$CONF/$file' 2>/dev/null || true"
  inside sh -c "grep -qx '#include $file' '$CONF/$main' || printf '\n#include %s\n' '$file' >> '$CONF/$main'"
done

ast "pjsip reload" >/dev/null
ast "dialplan reload" >/dev/null
retry() { for _ in $(seq 1 20); do "$@" && return 0; sleep 1; done; return 1; }
transport_up() { ast "pjsip show transports" | grep -q "$TRANSPORT"; }
endpoint_up() { ast "pjsip show endpoint twilio" | grep -q "from_user *: *$CALLER_ID"; }
dialplan_up() { ast "dialplan show s@$CONTEXT" | grep -q Hangup; }
retry transport_up ||
  die "transport $TRANSPORT did not start: is $BIND_IP:$SIP_PORT free? Check: asterisk -rx 'pjsip show transports'"
retry endpoint_up || die "endpoint twilio did not load. Check: asterisk -rx 'pjsip show endpoint twilio'"
retry dialplan_up || die "dialplan $CONTEXT did not load. Check: asterisk -rx 'dialplan show $CONTEXT'"

echo
echo "Ready: PJSIP/<E.164>@twilio dials through $TRUNK_URI from $EXTERNAL_IP, caller ID $CALLER_ID."
echo "Twilio console, once: the trunk's IP Access Control List has $EXTERNAL_IP/32, the caller ID"
echo "is a number on the account, and Voice geo permissions allow the destination country."
echo "Gemini call to a phone (sample order):"
echo "  sudo docker run --rm --network host --env-file /etc/codguard/controller.env \\"
echo "    asia-southeast1-docker.pkg.dev/ai-codguard/codguard/backend:main python -m app.telephony.dial +84XXXXXXXXX"
