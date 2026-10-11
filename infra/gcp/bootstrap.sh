#!/usr/bin/env bash
# One-time Google Cloud setup for COD Guard.
#
# Run in Cloud Shell (already signed in, gcloud installed), with the project selected:
#   gcloud config set project <PROJECT_ID>
#   bash bootstrap.sh
#
# Safe to re-run: each step checks whether its resource already exists.
# Override defaults with environment variables, e.g. VM_ZONE=asia-southeast1-b bash bootstrap.sh

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-asia-southeast1}"        # Cloud Run and Artifact Registry
VM_ZONE="${VM_ZONE:-us-central1-a}"        # e2-micro is free only in us-central1/us-east1/us-west1
VM_MACHINE="${VM_MACHINE:-e2-micro}"
GITHUB_REPO="${GITHUB_REPO:-beavershydraai/hydraai_codguard}"
BUDGET_AMOUNT="${BUDGET_AMOUNT:-}"         # in the billing account's currency; 20 by default for USD

AR_REPO=codguard
DEPLOYER_SA=codguard-deployer
RUNTIME_SA=codguard-runtime
POOL=github
PROVIDER=github-oidc
VM_NAME=codguard-asterisk
VM_IP_NAME=codguard-asterisk-ip
VM_TAG=asterisk
NETWORK=default
RTP_PORTS=10000-10100
# Twilio Elastic SIP Trunking: signaling per edge, and the global media range.
# Source: https://www.twilio.com/docs/sip-trunking/ip-addresses
TWILIO_SIGNALING=54.172.60.0/30,54.244.51.0/30,54.171.127.192/30,35.156.191.128/30,54.65.63.192/30,54.169.127.128/30,54.252.254.64/30,177.71.206.192/30
TWILIO_MEDIA=168.86.128.0/18
IAP_RANGE=35.235.240.0/20

log() { printf '\n==> %s\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }
exists() { "$@" >/dev/null 2>&1; }
# New service accounts take a few seconds to become visible to IAM.
retry() { for _ in 1 2 3 4 5 6; do "$@" && return 0; sleep 5; done; return 1; }

if [ -z "$PROJECT_ID" ]; then
  echo "No project selected. Run: gcloud config set project <PROJECT_ID>" >&2
  exit 1
fi
gcloud config set project "$PROJECT_ID" >/dev/null
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
VM_REGION="${VM_ZONE%-*}"
DEPLOYER_EMAIL="$DEPLOYER_SA@$PROJECT_ID.iam.gserviceaccount.com"
RUNTIME_EMAIL="$RUNTIME_SA@$PROJECT_ID.iam.gserviceaccount.com"

log "Project $PROJECT_ID (number $PROJECT_NUMBER)"
if [ "$(gcloud billing projects describe "$PROJECT_ID" --format='value(billingEnabled)')" != "True" ]; then
  echo "Billing is not enabled on $PROJECT_ID. Link a billing account first." >&2
  exit 1
fi
BILLING_ACCOUNT=$(gcloud billing projects describe "$PROJECT_ID" --format='value(billingAccountName)')
BILLING_ACCOUNT="${BILLING_ACCOUNT#billingAccounts/}"

log "Enabling APIs (takes a minute)"
gcloud services enable \
  run.googleapis.com artifactregistry.googleapis.com \
  iam.googleapis.com iamcredentials.googleapis.com sts.googleapis.com \
  cloudresourcemanager.googleapis.com compute.googleapis.com \
  speech.googleapis.com texttospeech.googleapis.com aiplatform.googleapis.com \
  billingbudgets.googleapis.com

log "Artifact Registry: $REGION/$AR_REPO"
if ! exists gcloud artifacts repositories describe "$AR_REPO" --location "$REGION"; then
  gcloud artifacts repositories create "$AR_REPO" --repository-format docker \
    --location "$REGION" --description "COD Guard container images"
fi
POLICY_FILE=$(mktemp)
cat > "$POLICY_FILE" <<'JSON'
[
  {"name": "keep-recent", "action": {"type": "Keep"}, "mostRecentVersions": {"keepCount": 10}},
  {"name": "delete-old", "action": {"type": "Delete"}, "condition": {"olderThan": "7d"}}
]
JSON
gcloud artifacts repositories set-cleanup-policies "$AR_REPO" --location "$REGION" \
  --policy "$POLICY_FILE" >/dev/null
rm -f "$POLICY_FILE"

log "Service accounts"
for sa in "$DEPLOYER_SA:Deploys COD Guard from GitHub Actions" "$RUNTIME_SA:Runs the COD Guard backend"; do
  name="${sa%%:*}"
  exists gcloud iam service-accounts describe "$name@$PROJECT_ID.iam.gserviceaccount.com" \
    || gcloud iam service-accounts create "$name" --display-name "${sa#*:}"
done

bind_project_role() {
  retry gcloud projects add-iam-policy-binding "$PROJECT_ID" --member "serviceAccount:$1" \
    --role "$2" --condition=None --quiet >/dev/null \
    || warn "Could not grant $2 to $1"
}
# Deployer: push images, deploy Cloud Run, run the service as the runtime account.
bind_project_role "$DEPLOYER_EMAIL" roles/run.admin
bind_project_role "$DEPLOYER_EMAIL" roles/artifactregistry.writer
retry gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_EMAIL" \
  --member "serviceAccount:$DEPLOYER_EMAIL" --role roles/iam.serviceAccountUser --quiet >/dev/null
# Runtime: Gemini on Vertex AI, Speech-to-Text, Text-to-Speech (API usage).
bind_project_role "$RUNTIME_EMAIL" roles/aiplatform.user
bind_project_role "$RUNTIME_EMAIL" roles/speech.client
bind_project_role "$RUNTIME_EMAIL" roles/serviceusage.serviceUsageConsumer

log "Workload Identity Federation for $GITHUB_REPO (main branch only)"
exists gcloud iam workload-identity-pools describe "$POOL" --location global \
  || gcloud iam workload-identity-pools create "$POOL" --location global --display-name "GitHub Actions"
exists gcloud iam workload-identity-pools providers describe "$PROVIDER" \
    --workload-identity-pool "$POOL" --location global \
  || gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" \
    --workload-identity-pool "$POOL" --location global --display-name "GitHub OIDC" \
    --issuer-uri "https://token.actions.githubusercontent.com" \
    --attribute-mapping "google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
    --attribute-condition "assertion.repository=='$GITHUB_REPO' && assertion.ref=='refs/heads/main'"
retry gcloud iam service-accounts add-iam-policy-binding "$DEPLOYER_EMAIL" \
  --role roles/iam.workloadIdentityUser \
  --member "principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL/attribute.repository/$GITHUB_REPO" \
  --quiet >/dev/null

log "Network and firewall for the Asterisk VM"
# Enabling Compute Engine creates the default network; wait for it before creating one.
retry gcloud compute networks describe "$NETWORK" >/dev/null 2>&1 \
  || gcloud compute networks create "$NETWORK" --subnet-mode auto
create_rule() {
  local name=$1 rules=$2 sources=$3
  exists gcloud compute firewall-rules describe "$name" \
    || gcloud compute firewall-rules create "$name" --network "$NETWORK" --direction INGRESS \
      --action allow --rules "$rules" --source-ranges "$sources" --target-tags "$VM_TAG"
}
create_rule codguard-sip-from-twilio udp:5060,tcp:5060,tcp:5061 "$TWILIO_SIGNALING"
create_rule codguard-rtp-from-twilio "udp:$RTP_PORTS" "$TWILIO_MEDIA"
create_rule codguard-ssh-from-iap tcp:22 "$IAP_RANGE"
if exists gcloud compute firewall-rules describe default-allow-ssh; then
  warn "default-allow-ssh opens SSH to the whole internet. SSH through IAP works without it:"
  warn "  gcloud compute firewall-rules delete default-allow-ssh"
fi

log "Asterisk VM: $VM_NAME ($VM_MACHINE, $VM_ZONE)"
exists gcloud compute addresses describe "$VM_IP_NAME" --region "$VM_REGION" \
  || gcloud compute addresses create "$VM_IP_NAME" --region "$VM_REGION"
VM_IP=$(gcloud compute addresses describe "$VM_IP_NAME" --region "$VM_REGION" --format='value(address)')
if ! exists gcloud compute instances describe "$VM_NAME" --zone "$VM_ZONE"; then
  STARTUP_FILE=$(mktemp)
  cat > "$STARTUP_FILE" <<'STARTUP'
#!/bin/bash
# Installs Docker on first boot. Asterisk itself is deployed as a container later.
if ! command -v docker >/dev/null 2>&1; then
  apt-get update && apt-get install -y docker.io
  systemctl enable --now docker
fi
STARTUP
  gcloud compute instances create "$VM_NAME" --zone "$VM_ZONE" --machine-type "$VM_MACHINE" \
    --image-family debian-12 --image-project debian-cloud \
    --boot-disk-size 30GB --boot-disk-type pd-standard \
    --address "$VM_IP" --tags "$VM_TAG" \
    --service-account "$RUNTIME_EMAIL" --scopes cloud-platform \
    --metadata-from-file startup-script="$STARTUP_FILE"
  rm -f "$STARTUP_FILE"
fi

log "Budget alert"
CURRENCY=$(gcloud billing accounts describe "$BILLING_ACCOUNT" --format='value(currencyCode)' 2>/dev/null || true)
if [ -z "$BUDGET_AMOUNT" ] && [ "$CURRENCY" = "USD" ]; then BUDGET_AMOUNT=20; fi
if [ -z "$BUDGET_AMOUNT" ]; then
  warn "Billing currency is ${CURRENCY:-unknown}; set BUDGET_AMOUNT (in $CURRENCY) and re-run to add a budget alert."
elif [ -n "$(gcloud billing budgets list --billing-account "$BILLING_ACCOUNT" \
        --filter 'displayName=codguard' --format 'value(name)' 2>/dev/null)" ]; then
  echo "Budget 'codguard' already exists."
else
  gcloud billing budgets create --billing-account "$BILLING_ACCOUNT" --display-name codguard \
    --budget-amount "${BUDGET_AMOUNT}${CURRENCY}" --filter-projects "projects/$PROJECT_ID" \
    --threshold-rule percent=0.5 --threshold-rule percent=0.9 --threshold-rule percent=1.0 \
    || warn "Could not create the budget (needs Billing Account Administrator). Add it in Billing > Budgets & alerts."
fi

cat <<SUMMARY

==================================================================
Done. Send these values back (none of them is a secret):

GCP_PROJECT_ID=$PROJECT_ID
GCP_PROJECT_NUMBER=$PROJECT_NUMBER
GCP_REGION=$REGION
GCP_ARTIFACT_REPO=$REGION-docker.pkg.dev/$PROJECT_ID/$AR_REPO
GCP_WIF_PROVIDER=projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL/providers/$PROVIDER
GCP_DEPLOYER_SA=$DEPLOYER_EMAIL
GCP_RUNTIME_SA=$RUNTIME_EMAIL
ASTERISK_VM=$VM_NAME ($VM_ZONE)
ASTERISK_IP=$VM_IP
==================================================================
SUMMARY
