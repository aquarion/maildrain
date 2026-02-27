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

# ---------------------------------------------------------------------------
# CI/CD — GitHub Actions needs to push images and update the Cloud Run Job
# ---------------------------------------------------------------------------

resource "google_artifact_registry_repository_iam_member" "maildrain_ar_writer" {
  location   = var.region
  repository = google_artifact_registry_repository.maildrain.name
  role       = "roles/artifactregistry.writer"
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

# ---------------------------------------------------------------------------
# Workload Identity Federation — lets GitHub Actions impersonate the SA
# ---------------------------------------------------------------------------

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
