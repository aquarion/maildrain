# Terraform manages the secret structure only — not the values.
# Upload values manually after first apply (see README).

resource "google_secret_manager_secret" "token" {
  secret_id = "maildrain-token"
  replication {
    auto {}
  }
  # Automatically destroy disabled versions after 1 day.
  # _write_token_to_secret() disables previous versions on each write,
  # so old token versions are cleaned up without manual intervention.
  version_destroy_ttl = "86400s"
}

resource "google_secret_manager_secret" "servers" {
  secret_id = "maildrain-servers"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "credentials" {
  secret_id = "maildrain-credentials"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "slack_webhook" {
  secret_id = "maildrain-slack-webhook"
  replication {
    auto {}
  }
}
