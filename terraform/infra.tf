locals {
  image_base = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.maildrain.repository_id}/maildrain"
}

# ---------------------------------------------------------------------------
# Artifact Registry
# ---------------------------------------------------------------------------

resource "google_artifact_registry_repository" "maildrain" {
  location      = var.region
  repository_id = "maildrain"
  format        = "DOCKER"
}

# ---------------------------------------------------------------------------
# Cloud Run Job
# ---------------------------------------------------------------------------

resource "google_cloud_run_v2_job" "maildrain" {
  name     = "maildrain"
  location = var.region
  deletion_protection=false

  template {
    template {
      service_account = google_service_account.maildrain.email

      containers {
        # CI updates this image on every deploy; Terraform ignores the tag.
        image = "${local.image_base}:latest"

        env {
          name  = "GOOGLE_CLOUD_PROJECT"
          value = var.project_id
        }
        env {
          name  = "GOOGLE_TOKEN_SECRET"
          value = google_secret_manager_secret.token.secret_id
        }
        env {
          name  = "SERVERS_FILE"
          value = "/run/secrets/servers/servers.toml"
        }
        env {
          name  = "GOOGLE_CREDENTIALS_FILE"
          value = "/run/secrets/credentials/credentials.json"
        }

        volume_mounts {
          name       = "servers"
          mount_path = "/run/secrets/servers"
        }
        volume_mounts {
          name       = "credentials"
          mount_path = "/run/secrets/credentials"
        }
      }

      volumes {
        name = "servers"
        secret {
          secret = google_secret_manager_secret.servers.secret_id
          items {
            version = "latest"
            path    = "servers.toml"
          }
        }
      }
      volumes {
        name = "credentials"
        secret {
          secret = google_secret_manager_secret.credentials.secret_id
          items {
            version = "latest"
            path    = "credentials.json"
          }
        }
      }
    }
  }

  lifecycle {
    # The image tag is managed by the deploy workflow, not Terraform.
    ignore_changes = [
      template[0].template[0].containers[0].image,
      launch_stage,
    ]
  }

  depends_on = [
    google_secret_manager_secret_iam_member.token_accessor,
    google_secret_manager_secret_iam_member.servers_accessor,
    google_secret_manager_secret_iam_member.credentials_accessor,
  ]
}

# ---------------------------------------------------------------------------
# Cloud Scheduler
# ---------------------------------------------------------------------------

resource "google_cloud_scheduler_job" "maildrain_hourly" {
  name     = "maildrain-hourly"
  schedule = "0 * * * *"
  region   = var.region

  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/${google_cloud_run_v2_job.maildrain.name}:run"

    oauth_token {
      service_account_email = google_service_account.maildrain.email
    }
  }
}
