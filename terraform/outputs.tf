output "service_account_email" {
  description = "Set as GCP_SERVICE_ACCOUNT in GitHub Actions variables."
  value       = google_service_account.maildrain.email
}

output "workload_identity_provider" {
  description = "Set as GCP_WORKLOAD_IDENTITY_PROVIDER in GitHub Actions secrets."
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "artifact_registry_location" {
  description = "Set as GAR_LOCATION in GitHub Actions variables."
  value       = var.region
}

output "artifact_registry_repository" {
  description = "Set as GAR_REPOSITORY in GitHub Actions variables."
  value       = google_artifact_registry_repository.maildrain.repository_id
}
