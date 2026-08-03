# Terraform manages the secret structure only — not the values.
# Upload values manually after first apply (see README).

resource "google_secret_manager_secret" "token" {
  secret_id = "maildrain-token"
  replication {
    auto {}
  }
  # _write_token_to_secret() destroys previous versions outright on each
  # write (disabling alone doesn't stop Secret Manager from billing for
  # storage — only DESTROYED versions are free). This TTL just delays the
  # irreversible data purge by 1 day as a safety window for recovery.
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
