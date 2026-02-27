variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "region" {
  description = "GCP region for all resources."
  type        = string
}

variable "github_repo" {
  description = "GitHub repository in 'owner/repo' format. Used to scope Workload Identity Federation."
  type        = string
}
