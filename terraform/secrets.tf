# Terraform manages the secret structure only — not the values.
# Upload values manually after first apply (see README).

resource "google_secret_manager_secret" "token" {
  secret_id = "maildrain-token"
  replication {
    auto {}
  }
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
