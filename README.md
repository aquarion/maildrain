# maildrain

Drain legacy IMAP/POP3 mailboxes into Gmail and archive the originals.

For each configured account, maildrain:
1. Downloads messages via IMAP (or POP3 if configured)
2. Uploads them to Gmail, applying any configured labels
3. Moves the originals to an archive folder on the source server

---

## Local setup

**Prerequisites:** Python 3.11+, [Poetry](https://python-poetry.org/)

```sh
poetry install
cp etc/servers.toml.example etc/servers.toml   # fill in your accounts
cp .env.example .env                            # adjust paths if needed
```

Download OAuth credentials from Google Cloud Console → APIs & Services → Credentials → OAuth 2.0 Client IDs and save as `etc/credentials.json`.

First run opens a browser for OAuth consent and caches the token to `etc/token.json`:

```sh
poetry run maildrain
```

Subsequent runs use the cached token silently.

---

## Configuration

### `etc/servers.toml`

One `[[servers]]` block per source account. IMAP fields are always required (used for archiving). POP3 fields are optional; omit them to use IMAP for both download and archive.

```toml
[[servers]]
name        = "Old work account"
imap_host   = "mail.example.com"
imap_port   = 993
imap_username = "user@example.com"
imap_password = "secret"
archive_folder = "Archive"       # created automatically; defaults to "Archive"
labels      = ["Work (old)"]     # Gmail labels to apply; created if missing
```

See `etc/servers.toml.example` for a full POP3+IMAP example.

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `SERVERS_FILE` | `etc/servers.toml` | Path to the servers config |
| `GOOGLE_CREDENTIALS_FILE` | `etc/credentials.json` | OAuth client credentials from Google Cloud Console |
| `GOOGLE_TOKEN_FILE` | `etc/token.json` | Local token cache (ignored when `GOOGLE_TOKEN_SECRET` is set) |
| `GOOGLE_TOKEN_SECRET` | — | Secret Manager secret name holding the OAuth token (GCP only) |
| `GOOGLE_CLOUD_PROJECT` | — | GCP project ID (set automatically by Cloud Run) |

---

## GCP deployment (Cloud Run Jobs + Cloud Scheduler)

Infrastructure is managed by Terraform (`terraform/`). GitHub Actions applies it automatically when `terraform/` changes, and deploys new images on every push to `main`.

### Bootstrap (one time, done manually)

Terraform can't create itself, so a few things must exist before the first `terraform apply`:

**1. Enable required APIs:**

| API | Purpose |
|---|---|
| `gmail.googleapis.com` | Gmail insert + label management |
| `secretmanager.googleapis.com` | Store OAuth token, servers config, credentials |
| `run.googleapis.com` | Cloud Run Job |
| `cloudscheduler.googleapis.com` | Hourly trigger |
| `artifactregistry.googleapis.com` | Docker image registry |
| `iam.googleapis.com` | Service accounts |
| `iamcredentials.googleapis.com` | Workload Identity Federation token exchange |
| `sts.googleapis.com` | Security Token Service (WIF) |
| `cloudresourcemanager.googleapis.com` | Project-level IAM bindings (used by Terraform) |

```sh
gcloud services enable \
  gmail.googleapis.com \
  secretmanager.googleapis.com \
  run.googleapis.com \
  cloudscheduler.googleapis.com \
  artifactregistry.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  sts.googleapis.com \
  cloudresourcemanager.googleapis.com
```

**2. Create a GCS bucket for Terraform state:**
```sh
gcloud storage buckets create gs://YOUR_STATE_BUCKET --location=REGION
```

**2. Create a service account and grant it permissions to manage infrastructure:**
```sh
gcloud iam service-accounts create maildrain-bootstrap \
  --display-name="maildrain Terraform bootstrap"

# Editor + security roles covers everything Terraform needs to create
gcloud projects add-iam-policy-binding PROJECT \
  --member="serviceAccount:maildrain-bootstrap@PROJECT.iam.gserviceaccount.com" \
  --role="roles/editor"
gcloud projects add-iam-policy-binding PROJECT \
  --member="serviceAccount:maildrain-bootstrap@PROJECT.iam.gserviceaccount.com" \
  --role="roles/iam.securityAdmin"
gcloud projects add-iam-policy-binding PROJECT \
  --member="serviceAccount:maildrain-bootstrap@PROJECT.iam.gserviceaccount.com" \
  --role="roles/iam.workloadIdentityPoolAdmin"
```

**3. Run Terraform locally** (authenticated as yourself or the bootstrap SA):
```sh
cp terraform/terraform.tfvars.example terraform/terraform.tfvars  # fill in values
cd terraform
terraform init -backend-config="bucket=YOUR_STATE_BUCKET"
terraform apply
```

Terraform outputs the values you need for GitHub Actions configuration.

**4. Upload secret values** (Terraform creates the secret structure, not the values):
```sh
poetry run maildrain          # generates etc/token.json via browser OAuth flow

gcloud secrets versions add maildrain-token       --data-file=etc/token.json
gcloud secrets versions add maildrain-servers     --data-file=etc/servers.toml
gcloud secrets versions add maildrain-credentials --data-file=etc/credentials.json
```

**5. Configure GitHub Actions** (Settings → Secrets and variables → Actions):

| Type | Name | Value |
|---|---|---|
| Secret | `GCP_WORKLOAD_IDENTITY_PROVIDER` | from `terraform output workload_identity_provider` |
| Variable | `GCP_PROJECT_ID` | your project ID |
| Variable | `GCP_SERVICE_ACCOUNT` | from `terraform output service_account_email` |
| Variable | `GAR_LOCATION` | from `terraform output artifact_registry_location` |
| Variable | `GAR_REPOSITORY` | from `terraform output artifact_registry_repository` |
| Variable | `CLOUD_RUN_REGION` | your region |
| Variable | `GITHUB_REPO` | `owner/repo` |
| Variable | `TF_STATE_BUCKET` | your state bucket name |

**6. Push to `main`** — the deploy workflow builds and pushes the first image.

### Ongoing

- **Code changes** → push to `main` → `deploy.yml` builds and updates the Cloud Run Job image
- **Infrastructure changes** → edit `terraform/` → open a PR to see the plan → merge to apply
- **Config changes** → update `etc/servers.toml` locally, then: `gcloud secrets versions add maildrain-servers --data-file=etc/servers.toml`

---

## Maintenance

### Token refresh

The OAuth token contains a short-lived **access token** (~60 min) and a long-lived **refresh token**. maildrain refreshes the access token automatically on each run and writes the updated token back to Secret Manager. No manual intervention needed under normal circumstances.

### If the refresh token expires

Google refresh tokens expire if:
- Unused for 6 months
- The user revokes access
- The OAuth app is in **Testing** mode — refresh tokens may expire after 7 days

If the refresh token expires, maildrain will crash on startup with an auth error. To recover, re-authenticate locally and push the new token:

```sh
rm etc/token.json
poetry run maildrain        # opens browser, generates new token
gcloud secrets versions add maildrain-token --data-file=etc/token.json
```

### OAuth app Testing mode

If your Google Cloud OAuth app is in Testing status, refresh tokens may expire after 7 days. Options:

- **Google Workspace users:** set the OAuth consent screen to "Internal" — unlimited refresh token lifetime, no verification needed
- **Personal Gmail users:** keep Testing mode and re-authenticate manually when needed (see above), or publish the app (requires a Google security review for the `gmail.insert` restricted scope)

### Secret Manager version accumulation

Each run that refreshes the access token adds a new version to the `maildrain-token` secret. Old versions are harmless but accumulate. To clean up, set a [secret version destroy policy](https://cloud.google.com/secret-manager/docs/automatically-destroying-secret-versions) in Secret Manager, or periodically disable old versions:

```sh
gcloud secrets versions list maildrain-token
gcloud secrets versions disable VERSION --secret=maildrain-token
```

### Updating the servers config

Edit your local `etc/servers.toml`, then push a new version:

```sh
gcloud secrets versions add maildrain-servers --data-file=etc/servers.toml
```

The next scheduled run picks it up automatically.
