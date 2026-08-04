# maildrain Terraform

Manages the GCP infrastructure for maildrain: Artifact Registry, Cloud Run Job, Cloud Scheduler, Secret Manager secrets, service account, and Workload Identity Federation.

## Initial setup (new GCP project)

Terraform runs as the `maildrain` service account via Workload Identity Federation (WIF), and that same service account manages its own IAM bindings, the state bucket's IAM, etc. That's a chicken-and-egg problem on a brand new project: the SA can't grant itself permissions it doesn't have yet. Bootstrap once with your own elevated (Owner/IAM Admin) credentials, in this order:

1. **Create the GCS state bucket manually** (Terraform does not manage it, to avoid a state-of-state problem):
   ```
   gcloud storage buckets create gs://<bucket> --location=<region> --project=<project>
   ```
2. **Copy `terraform.tfvars.example` to `terraform.tfvars`** and fill in `project_id`, `region`, `github_repo` (`owner/repo`), `state_bucket`.
3. **Run `terraform init` and `terraform apply` locally**, authenticated as yourself (`gcloud auth application-default login`) — this creates the `maildrain` service account, WIF pool, and all other resources for the first time.
4. **Grant the manual bootstrap IAM bindings** listed inline in `iam.tf` (search for `BOOTSTRAP NOTE`) — each covers a getIamPolicy/setIamPolicy permission Terraform needs on a resource it doesn't have access to yet on a first run. As of writing these are: state bucket `storage.admin`, project-level `secretmanager.admin`, the SA's own `iam.serviceAccountAdmin`, project-level `iam.workloadIdentityPoolAdmin`, and project-level `cloudscheduler.admin`.
5. **Set the required GitHub configuration** (see below), then let CI take over — subsequent `terraform plan`/`apply` runs via GitHub Actions should work without further manual grants.

### Required GitHub configuration

| Kind | Name | Value |
| ---- | ---- | ----- |
| Secret | `GCP_WORKLOAD_IDENTITY_PROVIDER` | `workload_identity_provider` output |
| Variable | `GCP_SERVICE_ACCOUNT` | `service_account_email` output |
| Variable | `GCP_PROJECT_ID` | GCP project ID |
| Variable | `CLOUD_RUN_REGION` | e.g. `europe-west2` |
| Variable | `TF_STATE_BUCKET` | the bucket created in step 1 |
| Variable | `GAR_LOCATION` | `artifact_registry_location` output |
| Variable | `GAR_REPOSITORY` | `artifact_registry_repository` output |

Note: the Terraform `github_repo` input is **not** a GitHub Actions variable — it's populated from the built-in `${{ github.repository }}` context in `.github/workflows/terraform.yml`. Don't reintroduce a `GITHUB_REPO` repo variable for this: GitHub reserves the `GITHUB_` prefix and silently rejects any variable name starting with it, which is exactly what caused `terraform.tfvars`'s `github_repo` to apply as an empty string in production once (locking CI out of GCP entirely, since the WIF trust condition matched no repository). Use `github.repository`, not a custom variable, for anything scoping WIF to this repo.

<!-- BEGIN_TF_DOCS -->
## Requirements

| Name | Version |
| ---- | ------- |
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | >= 1.5 |
| <a name="requirement_google"></a> [google](#requirement\_google) | ~> 6.0 |

## Providers

| Name | Version |
| ---- | ------- |
| <a name="provider_google"></a> [google](#provider\_google) | 6.50.0 |

## Modules

No modules.

## Resources

| Name | Type |
| ---- | ---- |
| [google_artifact_registry_repository.maildrain](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/artifact_registry_repository) | resource |
| [google_artifact_registry_repository_iam_member.maildrain_ar_writer](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/artifact_registry_repository_iam_member) | resource |
| [google_cloud_run_v2_job.maildrain](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/cloud_run_v2_job) | resource |
| [google_cloud_scheduler_job.maildrain_hourly](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/cloud_scheduler_job) | resource |
| [google_iam_workload_identity_pool.github](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/iam_workload_identity_pool) | resource |
| [google_iam_workload_identity_pool_provider.github](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/iam_workload_identity_pool_provider) | resource |
| [google_project_iam_member.maildrain_cloudscheduler_admin](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/project_iam_member) | resource |
| [google_project_iam_member.maildrain_project_iam_admin](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/project_iam_member) | resource |
| [google_project_iam_member.maildrain_run_developer](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/project_iam_member) | resource |
| [google_project_iam_member.maildrain_secretmanager_admin](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/project_iam_member) | resource |
| [google_project_iam_member.maildrain_workload_identity_pool_admin](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/project_iam_member) | resource |
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
| [google_service_account_iam_member.maildrain_sa_admin_self](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/service_account_iam_member) | resource |
| [google_storage_bucket_iam_member.maildrain_state_bucket](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/storage_bucket_iam_member) | resource |

## Inputs

| Name | Description | Type | Default | Required |
| ---- | ----------- | ---- | ------- | :------: |
| <a name="input_github_repo"></a> [github\_repo](#input\_github\_repo) | GitHub repository in 'owner/repo' format. Used to scope Workload Identity Federation. | `string` | n/a | yes |
| <a name="input_project_id"></a> [project\_id](#input\_project\_id) | GCP project ID. | `string` | n/a | yes |
| <a name="input_region"></a> [region](#input\_region) | GCP region for all resources. | `string` | n/a | yes |
| <a name="input_state_bucket"></a> [state\_bucket](#input\_state\_bucket) | GCS bucket name used for Terraform state. The service account is granted storage.objectAdmin on this bucket. | `string` | n/a | yes |

## Outputs

| Name | Description |
| ---- | ----------- |
| <a name="output_artifact_registry_location"></a> [artifact\_registry\_location](#output\_artifact\_registry\_location) | Set as GAR\_LOCATION in GitHub Actions variables. |
| <a name="output_artifact_registry_repository"></a> [artifact\_registry\_repository](#output\_artifact\_registry\_repository) | Set as GAR\_REPOSITORY in GitHub Actions variables. |
| <a name="output_service_account_email"></a> [service\_account\_email](#output\_service\_account\_email) | Set as GCP\_SERVICE\_ACCOUNT in GitHub Actions variables. |
| <a name="output_workload_identity_provider"></a> [workload\_identity\_provider](#output\_workload\_identity\_provider) | Set as GCP\_WORKLOAD\_IDENTITY\_PROVIDER in GitHub Actions secrets. |
<!-- END_TF_DOCS -->
