# maildrain

Drain legacy IMAP/POP3 mailboxes into Gmail and archive the originals.
## Development

### Testing

Run tests locally:
```bash
poetry install --with dev
poetry run pytest
poetry run pytest --cov=maildrain.gmail_client --cov=maildrain.models --cov-report=term
```

### Code Quality

Check code formatting and linting:
```bash
poetry run ruff check .
poetry run ruff format --check .
```

Auto-fix issues:
```bash
poetry run ruff check . --fix
poetry run ruff format .
```

### Continuous Integration

The project uses GitHub Actions for continuous integration:

- **Tests** ([.github/workflows/test.yml](.github/workflows/test.yml)): Runs on all pushes and pull requests affecting Python code
  - Tests on Python 3.11 and 3.12
  - Checks test coverage (95%+ required for tested modules)
  - Runs linting and formatting checks
  - Caches dependencies for faster builds

- **Terraform** ([.github/workflows/terraform.yml](.github/workflows/terraform.yml)): Manages infrastructure
- **Deploy** ([.github/workflows/deploy.yml](.github/workflows/deploy.yml)): Handles deployments
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
cp .env.example .env                            # adjust paths if needed (includes Slack config)
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
| `GOOGLE_CLOUD_PROJECT` | — | GCP project ID (set explicitly in Terraform; required when `GOOGLE_TOKEN_SECRET` is set) |
| `SLACK_WEBHOOK_URL` | — | Slack webhook URL for error notifications (see **Slack Notifications** below) |

---

## Slack Notifications

maildrain can send critical error notifications to a Slack channel via webhook. When configured, notifications are sent for:

- Configuration errors (missing servers file, malformed TOML)
- Authentication failures (missing credentials, expired tokens)
- Fatal download errors for any server
- Run completion with failures (Gmail upload or archive failures)

### Local Setup

1. **Create a Slack App** in your workspace:
   - Go to [api.slack.com/apps](https://api.slack.com/apps) → Create New App → From scratch
   - Choose an app name (e.g., "maildrain") and your workspace

2. **Enable Incoming Webhooks**:
   - In your app settings → Features → Incoming Webhooks → Activate Incoming Webhooks
   - Click Add New Webhook to Workspace → choose your channel → Allow

3. **Configure maildrain**:
   ```sh
   # Add to your .env file
   SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX
   ```

### GCP Deployment

For Cloud Run deployments, the webhook URL is stored securely in Secret Manager:

```sh
# Upload the webhook URL to Secret Manager
gcloud secrets versions add maildrain-slack-webhook --data-file=<(echo -n "https://hooks.slack.com/services/...")
```

The webhook URL is automatically injected as the `SLACK_WEBHOOK_URL` environment variable by Terraform.

### Disabling Notifications

Omit `SLACK_WEBHOOK_URL` entirely to disable notifications. maildrain will continue running normally but won't send any messages to Slack.

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

**2. Create a GCS bucket for Terraform state** (skip if one already exists):
```sh
gcloud storage buckets create gs://YOUR_STATE_BUCKET --location=REGION
```

**3. Create a service account and grant it permissions to manage infrastructure:**
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

**4. Authenticate locally:**
```sh
gcloud auth application-default login
```

**5. Run Terraform locally:**
```sh
cp terraform/terraform.tfvars.example terraform/terraform.tfvars  # fill in values
cd terraform
terraform init -backend-config="bucket=YOUR_STATE_BUCKET"
terraform apply
```

Terraform outputs the values you need for GitHub Actions configuration.

**6. Create OAuth credentials and generate the token:**

In Google Cloud Console → APIs & Services → Credentials → Create Credentials → OAuth client ID:
- Application type: **Desktop app**
- Download the JSON and save it as `etc/credentials.json`

Then run maildrain locally to trigger the browser OAuth consent flow:
```sh
poetry run maildrain          # opens browser, saves etc/token.json on completion
```

**7. Upload secret values** (Terraform creates the secret structure, not the values):
```sh
gcloud secrets versions add maildrain-token       --data-file=etc/token.json
gcloud secrets versions add maildrain-servers     --data-file=etc/servers.toml
gcloud secrets versions add maildrain-credentials --data-file=etc/credentials.json

# Optional: Slack webhook URL for error notifications
# gcloud secrets versions add maildrain-slack-webhook --data-file=<(echo -n "https://hooks.slack.com/services/...")
```

**8. Configure GitHub Actions:**

```sh
# Secret (sensitive — stored encrypted)
gh secret set GCP_WORKLOAD_IDENTITY_PROVIDER \
  --body "$(terraform -chdir=terraform output -raw workload_identity_provider)"

# Variables (non-sensitive — visible in logs)
gh variable set GCP_SERVICE_ACCOUNT \
  --body "$(terraform -chdir=terraform output -raw service_account_email)"
gh variable set GAR_LOCATION \
  --body "$(terraform -chdir=terraform output -raw artifact_registry_location)"
gh variable set GAR_REPOSITORY \
  --body "$(terraform -chdir=terraform output -raw artifact_registry_repository)"

# Fill these in manually
gh variable set GCP_PROJECT_ID    --body "YOUR_PROJECT_ID"
gh variable set CLOUD_RUN_REGION  --body "YOUR_REGION"
gh variable set GITHUB_REPO       --body "owner/repo"
gh variable set TF_STATE_BUCKET   --body "YOUR_STATE_BUCKET"
```

**9. Push to `main`** — the deploy workflow builds and pushes the first image.

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

Each run that refreshes the access token adds a new version to the `maildrain-token` secret. Old versions are automatically handled: maildrain disables previous versions on each write, and Terraform configures a 1-day `version_destroy_ttl` so disabled versions are destroyed automatically. No manual cleanup needed.

### Updating configuration

**Servers config:** Edit your local `etc/servers.toml`, then push a new version:

```sh
gcloud secrets versions add maildrain-servers --data-file=etc/servers.toml
```

**Slack webhook:** To update the Slack webhook URL:

```sh
gcloud secrets versions add maildrain-slack-webhook --data-file=<(echo -n "NEW_WEBHOOK_URL")
```

The next scheduled run picks up changes automatically.
