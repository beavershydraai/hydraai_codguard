# Google Cloud setup

`bootstrap.sh` sets up the project once. It is safe to re-run.

## Run it

1. Open [Cloud Shell](https://console.cloud.google.com/?cloudshell=true) as a project Owner.
2. Select the project: `gcloud config set project <PROJECT_ID>`.
3. Upload `infra/gcp/bootstrap.sh` (Cloud Shell menu ⋮ → Upload), then run `bash bootstrap.sh`.
4. Copy the block printed at the end into the PR or issue that adds the deploy job.

Defaults can be overridden with environment variables, for example
`VM_ZONE=asia-southeast1-b VM_MACHINE=e2-small bash bootstrap.sh`.

| Variable | Default | Meaning |
|---|---|---|
| `REGION` | `asia-southeast1` | Cloud Run and Artifact Registry |
| `VM_ZONE` | `us-central1-a` | Asterisk VM. `e2-micro` is free only in `us-central1`, `us-east1`, `us-west1` |
| `VM_MACHINE` | `e2-micro` | Asterisk VM machine type |
| `BUDGET_AMOUNT` | `20` if the billing currency is USD | Budget alert amount, in the billing account's currency |

## What it creates

| Resource | Name | Notes |
|---|---|---|
| APIs | Cloud Run, Artifact Registry, IAM, STS, Compute, Speech-to-Text, Text-to-Speech, Vertex AI, Budgets | |
| Artifact Registry | `codguard` (Docker) | Keeps the 10 newest images, deletes older ones after 7 days |
| Service account | `codguard-deployer` | `run.admin`, `artifactregistry.writer`, acts as the runtime account. Used only by GitHub Actions |
| Service account | `codguard-runtime` | `aiplatform.user`, `speech.client`, `serviceusage.serviceUsageConsumer`. The backend and the VM run as this account |
| Workload Identity Federation | pool `github`, provider `github-oidc` | Only `beavershydraai/hydraai_codguard` on `refs/heads/main` can act as the deployer. No key is stored in GitHub |
| Static IP + VM | `codguard-asterisk-ip`, `codguard-asterisk` | Debian 12, Docker installed on first boot |
| Firewall | `codguard-sip-from-twilio` | UDP 5060, TCP 5060/5061 from Twilio signaling ranges only |
| Firewall | `codguard-rtp-from-twilio` | UDP 10000–10100 from Twilio's media range only |
| Firewall | `codguard-ssh-from-iap` | SSH only through Identity-Aware Proxy |
| Budget | `codguard` | Email alerts at 50%, 90% and 100% |

Asterisk's ARI port (8088) is never opened. Reach it through an SSH tunnel:

```bash
gcloud compute ssh codguard-asterisk --zone us-central1-a --tunnel-through-iap -- -L 8088:localhost:8088
```

Twilio's IP ranges come from <https://www.twilio.com/docs/sip-trunking/ip-addresses>; update the
firewall rules if Twilio changes them.
