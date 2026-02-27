terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }

  # Bucket is passed via -backend-config to avoid hardcoding it.
  # Local:  terraform init -backend-config="bucket=YOUR_BUCKET"
  # CI:     see .github/workflows/terraform.yml
  backend "gcs" {
    prefix = "maildrain/terraform"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
