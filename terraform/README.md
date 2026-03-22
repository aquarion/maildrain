# maildrain Terraform

Manages the GCP infrastructure for maildrain: Artifact Registry, Cloud Run Job, Cloud Scheduler, Secret Manager secrets, service account, and Workload Identity Federation.

<!-- BEGIN_TF_DOCS -->
## Requirements

| Name | Version |
|------|---------|
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | >= 1.5 |
| <a name="requirement_google"></a> [google](#requirement\_google) | ~> 6.0 |

## Providers

| Name | Version |
|------|---------|
| <a name="provider_google"></a> [google](#provider\_google) | 6.50.0 |

## Modules

No modules.

## Resources

| Name | Type |
|------|------|
| [google_artifact_registry_repository.maildrain](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/artifact_registry_repository) | resource |
| [google_artifact_registry_repository_iam_member.maildrain_ar_writer](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/artifact_registry_repository_iam_member) | resource |
| [google_cloud_run_v2_job.maildrain](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/cloud_run_v2_job) | resource |
| [google_cloud_scheduler_job.maildrain_hourly](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/cloud_scheduler_job) | resource |
| [google_iam_workload_identity_pool.github](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/iam_workload_identity_pool) | resource |
| [google_iam_workload_identity_pool_provider.github](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/iam_workload_identity_pool_provider) | resource |
| [google_project_iam_member.maildrain_run_developer](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/project_iam_member) | resource |
| [google_secret_manager_secret.credentials](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/secret_manager_secret) | resource |
| [google_secret_manager_secret.servers](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/secret_manager_secret) | resource |
| [google_secret_manager_secret.slack_webhook](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/secret_manager_secret) | resource |
| [google_secret_manager_secret.token](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/secret_manager_secret) | resource |
| [google_secret_manager_secret_iam_member.credentials_accessor](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/secret_manager_secret_iam_member) | resource |
| [google_secret_manager_secret_iam_member.servers_accessor](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/secret_manager_secret_iam_member) | resource |
| [google_secret_manager_secret_iam_member.slack_webhook_accessor](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/secret_manager_secret_iam_member) | resource |
| [google_secret_manager_secret_iam_member.token_accessor](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/secret_manager_secret_iam_member) | resource |
| [google_secret_manager_secret_iam_member.token_version_adder](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/secret_manager_secret_iam_member) | resource |
| [google_secret_manager_secret_iam_member.token_version_manager](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/secret_manager_secret_iam_member) | resource |
| [google_service_account.maildrain](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/service_account) | resource |
| [google_service_account_iam_member.github_wif](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/service_account_iam_member) | resource |
| [google_service_account_iam_member.maildrain_act_as_self](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/service_account_iam_member) | resource |
| [google_storage_bucket_iam_member.maildrain_state_bucket](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/storage_bucket_iam_member) | resource |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_github_repo"></a> [github\_repo](#input\_github\_repo) | GitHub repository in 'owner/repo' format. Used to scope Workload Identity Federation. | `string` | n/a | yes |
| <a name="input_project_id"></a> [project\_id](#input\_project\_id) | GCP project ID. | `string` | n/a | yes |
| <a name="input_region"></a> [region](#input\_region) | GCP region for all resources. | `string` | n/a | yes |
| <a name="input_state_bucket"></a> [state\_bucket](#input\_state\_bucket) | GCS bucket name used for Terraform state. The service account is granted storage.objectAdmin on this bucket. | `string` | n/a | yes |

## Outputs

| Name | Description |
|------|-------------|
| <a name="output_artifact_registry_location"></a> [artifact\_registry\_location](#output\_artifact\_registry\_location) | Set as GAR\_LOCATION in GitHub Actions variables. |
| <a name="output_artifact_registry_repository"></a> [artifact\_registry\_repository](#output\_artifact\_registry\_repository) | Set as GAR\_REPOSITORY in GitHub Actions variables. |
| <a name="output_service_account_email"></a> [service\_account\_email](#output\_service\_account\_email) | Set as GCP\_SERVICE\_ACCOUNT in GitHub Actions variables. |
| <a name="output_workload_identity_provider"></a> [workload\_identity\_provider](#output\_workload\_identity\_provider) | Set as GCP\_WORKLOAD\_IDENTITY\_PROVIDER in GitHub Actions secrets. |
<!-- END_TF_DOCS -->
