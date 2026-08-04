# ---------------------------------------------------------------------------
# Service account used by:
#   - the Cloud Run Job at runtime (access secrets, call Gmail API)
#   - GitHub Actions via WIF (push images, update Cloud Run Job, run Terraform)
# ---------------------------------------------------------------------------

resource "google_service_account" "maildrain" {
  account_id   = "maildrain"
  display_name = "maildrain"
}

# ---------------------------------------------------------------------------
# Secret Manager — runtime access
# ---------------------------------------------------------------------------

resource "google_secret_manager_secret_iam_member" "token_accessor" {
  secret_id = google_secret_manager_secret.token.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.maildrain.email}"
}

# Token also needs write access so the refreshed token can be persisted,
# and version manager access to disable old versions for cleanup.
resource "google_secret_manager_secret_iam_member" "token_version_adder" {
  secret_id = google_secret_manager_secret.token.secret_id
  role      = "roles/secretmanager.secretVersionAdder"
  member    = "serviceAccount:${google_service_account.maildrain.email}"
}

resource "google_secret_manager_secret_iam_member" "token_version_manager" {
  secret_id = google_secret_manager_secret.token.secret_id
  role      = "roles/secretmanager.secretVersionManager"
  member    = "serviceAccount:${google_service_account.maildrain.email}"
}

resource "google_secret_manager_secret_iam_member" "servers_accessor" {
  secret_id = google_secret_manager_secret.servers.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.maildrain.email}"
}

resource "google_secret_manager_secret_iam_member" "credentials_accessor" {
  secret_id = google_secret_manager_secret.credentials.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.maildrain.email}"
}

resource "google_secret_manager_secret_iam_member" "slack_webhook_accessor" {
  secret_id = google_secret_manager_secret.slack_webhook.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.maildrain.email}"
}

# ---------------------------------------------------------------------------
# CI/CD — GitHub Actions needs to push images and update the Cloud Run Job
# ---------------------------------------------------------------------------
#
# BOOTSTRAP NOTE: the SA cannot apply this resource on its first run because
# it doesn't yet have access to the state bucket. Bootstrap by running once
# locally with personal credentials (or via gcloud):
#
#   gcloud storage buckets add-iam-policy-binding gs://<bucket> \
#     --member="serviceAccount:maildrain@maildrain.iam.gserviceaccount.com" \
#     --role="roles/storage.admin"
#
# After that, the SA can manage its own bucket IAM via Terraform.
#
# roles/storage.admin (not objectAdmin) because Terraform's
# google_storage_bucket_iam_member resource needs storage.buckets.getIamPolicy
# / setIamPolicy on the bucket to plan and apply this binding — objectAdmin
# only covers object payloads. Scoped to this one bucket, not project-wide.

resource "google_storage_bucket_iam_member" "maildrain_state_bucket" {
  bucket = var.state_bucket
  role   = "roles/storage.admin"
  member = "serviceAccount:${google_service_account.maildrain.email}"
}

# Terraform (running as this SA via WIF) needs to manage the
# google_secret_manager_secret resources in secrets.tf. The
# secretAccessor/secretVersion* grants above only cover reading/writing
# secret *payloads* at runtime — they don't include secretmanager.secrets.get,
# which Terraform needs just to read the resource for planning. Without this,
# every `terraform plan`/`apply` touching secrets.tf fails with
# IAM_PERMISSION_DENIED on secretmanager.secrets.get.
#
# BOOTSTRAP NOTE: same chicken-and-egg problem as the state bucket above —
# grant this manually once with elevated credentials before CI can rely on it:
#
#   gcloud projects add-iam-policy-binding <project> \
#     --member="serviceAccount:maildrain@maildrain.iam.gserviceaccount.com" \
#     --role="roles/secretmanager.admin"

resource "google_project_iam_member" "maildrain_secretmanager_admin" {
  project = var.project_id
  role    = "roles/secretmanager.admin"
  member  = "serviceAccount:${google_service_account.maildrain.email}"
}

# roles/artifactregistry.repoAdmin (not writer) because Terraform's
# google_artifact_registry_repository_iam_member resource needs
# artifactregistry.repositories.getIamPolicy/setIamPolicy on the repo to plan
# and apply this binding — writer only covers pushing images. Scoped to this
# one repo, not project-wide.
resource "google_artifact_registry_repository_iam_member" "maildrain_ar_writer" {
  location   = var.region
  repository = google_artifact_registry_repository.maildrain.name
  role       = "roles/artifactregistry.repoAdmin"
  member     = "serviceAccount:${google_service_account.maildrain.email}"
}

resource "google_project_iam_member" "maildrain_run_developer" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${google_service_account.maildrain.email}"
}

# Cloud Run requires the deployer to have actAs on the runtime SA.
# Since the same SA is used for both CI/CD and runtime, it needs this on itself.
resource "google_service_account_iam_member" "maildrain_act_as_self" {
  service_account_id = google_service_account.maildrain.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.maildrain.email}"
}

# Terraform's google_service_account_iam_member resources (this one and
# github_wif below) need iam.serviceAccounts.getIamPolicy/setIamPolicy on the
# maildrain SA to plan and apply — granted here scoped to just that one SA,
# not roles/iam.securityAdmin project-wide.
#
# BOOTSTRAP NOTE: same chicken-and-egg problem as the state bucket above —
# grant this manually once with elevated credentials before CI can rely on it:
#
#   gcloud iam service-accounts add-iam-policy-binding \
#     maildrain@<project>.iam.gserviceaccount.com \
#     --member="serviceAccount:maildrain@<project>.iam.gserviceaccount.com" \
#     --role="roles/iam.serviceAccountAdmin"
resource "google_service_account_iam_member" "maildrain_sa_admin_self" {
  service_account_id = google_service_account.maildrain.name
  role               = "roles/iam.serviceAccountAdmin"
  member             = "serviceAccount:${google_service_account.maildrain.email}"
}

# ---------------------------------------------------------------------------
# Workload Identity Federation — lets GitHub Actions impersonate the SA
# ---------------------------------------------------------------------------
#
# roles/iam.workloadIdentityPoolAdmin is inherently project-scoped — the pool
# doesn't exist yet for Terraform to bind a narrower, resource-level grant to.
#
# BOOTSTRAP NOTE: same chicken-and-egg problem as above — grant manually once:
#
#   gcloud projects add-iam-policy-binding <project> \
#     --member="serviceAccount:maildrain@<project>.iam.gserviceaccount.com" \
#     --role="roles/iam.workloadIdentityPoolAdmin"
resource "google_project_iam_member" "maildrain_workload_identity_pool_admin" {
  project = var.project_id
  role    = "roles/iam.workloadIdentityPoolAdmin"
  member  = "serviceAccount:${google_service_account.maildrain.email}"
}

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github-actions"
  display_name              = "GitHub Actions"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
  }

  # Only this specific repo can impersonate the service account.
  attribute_condition = "attribute.repository == '${var.github_repo}'"
}

resource "google_service_account_iam_member" "github_wif" {
  service_account_id = google_service_account.maildrain.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repo}"
}

# ---------------------------------------------------------------------------
# Cloud Scheduler
# ---------------------------------------------------------------------------
#
# roles/cloudscheduler.admin is inherently project-scoped — Cloud Scheduler
# doesn't support resource-level IAM bindings on individual jobs.
#
# BOOTSTRAP NOTE: same chicken-and-egg problem as above — grant manually once:
#
#   gcloud projects add-iam-policy-binding <project> \
#     --member="serviceAccount:maildrain@<project>.iam.gserviceaccount.com" \
#     --role="roles/cloudscheduler.admin"
resource "google_project_iam_member" "maildrain_cloudscheduler_admin" {
  project = var.project_id
  role    = "roles/cloudscheduler.admin"
  member  = "serviceAccount:${google_service_account.maildrain.email}"
}
