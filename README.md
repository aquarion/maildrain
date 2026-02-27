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

### First-time setup

Run maildrain locally once to generate `etc/token.json`, then upload all secrets:

```sh
poetry run maildrain

gcloud secrets create maildrain-token       --data-file=etc/token.json
gcloud secrets create maildrain-servers     --data-file=etc/servers.toml
gcloud secrets create maildrain-credentials --data-file=etc/credentials.json
```

Grant the Cloud Run service account access to the secrets:

```sh
SA="your-service-account@your-project.iam.gserviceaccount.com"
for secret in maildrain-token maildrain-servers maildrain-credentials; do
  gcloud secrets add-iam-policy-binding $secret \
    --member="serviceAccount:$SA" --role="roles/secretmanager.secretAccessor"
done
# Token secret also needs write access so maildrain can persist refreshed tokens
gcloud secrets add-iam-policy-binding maildrain-token \
  --member="serviceAccount:$SA" --role="roles/secretmanager.secretVersionAdder"
```

### Build and deploy

Create the Cloud Run Job once. After this, GitHub Actions handles all future deployments.

```sh
# Build and push the initial image
gcloud builds submit --tag REGION-docker.pkg.dev/PROJECT/REPO/maildrain

gcloud run jobs create maildrain \
  --image REGION-docker.pkg.dev/PROJECT/REPO/maildrain:latest \
  --service-account $SA \
  --region REGION \
  --set-env-vars GOOGLE_TOKEN_SECRET=maildrain-token \
  --set-secrets /etc/maildrain/servers.toml=maildrain-servers:latest \
  --set-secrets /etc/maildrain/credentials.json=maildrain-credentials:latest \
  --set-env-vars SERVERS_FILE=/etc/maildrain/servers.toml \
  --set-env-vars GOOGLE_CREDENTIALS_FILE=/etc/maildrain/credentials.json
```

### GitHub Actions (CI/CD)

The workflow in `.github/workflows/deploy.yml` builds and deploys on every push to `main`.

**Set up Workload Identity Federation** so GitHub Actions can authenticate to GCP without storing a service account key:

```sh
# Create a Workload Identity Pool and Provider for GitHub
gcloud iam workload-identity-pools create github \
  --location=global --display-name="GitHub Actions"

gcloud iam workload-identity-pools providers create-oidc github-provider \
  --location=global \
  --workload-identity-pool=github \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository"

# Allow your specific repo to impersonate the service account
gcloud iam service-accounts add-iam-policy-binding $SA \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github/attribute.repository/YOUR_GITHUB_ORG/maildrain"

# The SA also needs permission to push images and update the Cloud Run Job
gcloud projects add-iam-policy-binding PROJECT \
  --member="serviceAccount:$SA" --role="roles/artifactregistry.writer"
gcloud projects add-iam-policy-binding PROJECT \
  --member="serviceAccount:$SA" --role="roles/run.developer"
```

Then configure these in GitHub (Settings → Secrets and variables → Actions):

| Type | Name | Value |
|---|---|---|
| Secret | `GCP_WORKLOAD_IDENTITY_PROVIDER` | `projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github/providers/github-provider` |
| Variable | `GCP_PROJECT_ID` | your project ID |
| Variable | `GCP_SERVICE_ACCOUNT` | `$SA` email |
| Variable | `GAR_LOCATION` | e.g. `europe-west2` |
| Variable | `GAR_REPOSITORY` | e.g. `maildrain` |
| Variable | `CLOUD_RUN_REGION` | e.g. `europe-west2` |

### Schedule hourly

```sh
gcloud scheduler jobs create http maildrain-hourly \
  --schedule "0 * * * *" \
  --uri "https://REGION-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/PROJECT/jobs/maildrain:run" \
  --oauth-service-account-email $SA
```

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
