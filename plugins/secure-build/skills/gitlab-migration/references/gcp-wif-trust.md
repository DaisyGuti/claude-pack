# Google Cloud Workload Identity Federation: add GitLab, then retire GitHub

Every command here is a DRAFT. Show it, wait for the user's go for that step, then run it. Reads
(`list`, `describe`, `get-iam-policy`) can run without a go.

Sources (read 2026-10-16):

- GitLab: https://docs.gitlab.com/ci/cloud_services/google_cloud/ and
  https://docs.gitlab.com/ci/secrets/id_token_authentication/
- Google: https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines
  and https://docs.cloud.google.com/sdk/gcloud/reference/iam/workload-identity-pools/providers/create-oidc
- Google troubleshooting: https://docs.cloud.google.com/iam/docs/troubleshooting-workload-identity-federation

Fetch these again before drafting; flags and claim names can change.

## Contents

- [Plan](#plan)
- [Step 1: read the current GitHub setup](#step-1-read-the-current-github-setup)
- [Step 2: issuer and audience](#step-2-issuer-and-audience)
- [Step 3: create the GitLab provider](#step-3-create-the-gitlab-provider)
- [Step 4: let the pool identity use the service account](#step-4-let-the-pool-identity-use-the-service-account)
- [Step 5: change the pipeline](#step-5-change-the-pipeline)
- [Step 6: prove the restrictions](#step-6-prove-the-restrictions)
- [Step 7: retire the GitHub provider](#step-7-retire-the-github-provider)
- [Self-managed GitLab notes](#self-managed-gitlab-notes)
- [Troubleshooting](#troubleshooting)

## Plan

- Keep one pool for the GitLab installation in the Google Cloud project; add GitLab as a second
  provider next to the GitHub one (GitLab's page: one pool per GitLab installation per project;
  several repositories can use different providers in that pool).
- The GitHub provider stays until cutover is final. Both providers can trust the same service
  account during the mirror period.
- No long-lived keys. The job gets a short-lived ID token, exchanges it at Google's Security Token
  Service, then impersonates the service account.
- Google requires an attribute condition for GitLab.com because every GitLab.com organisation
  shares one issuer; claims such as the project name are not unique to your organisation. The
  condition below restricts to one project and to protected refs.

## Step 1: read the current GitHub setup

Read the workflow files first (the inventory lists the files that use `google-github-actions/auth`
or `id-token: write`); the `with:` block names the pool, provider and service account. Do not copy
values into chat beyond what the user needs to confirm.

Reads (no go needed):

```sh
gcloud iam workload-identity-pools list --location=global --project=GCP_PROJECT_ID
gcloud iam workload-identity-pools providers list --location=global \
  --workload-identity-pool=POOL_ID --project=GCP_PROJECT_ID
gcloud iam workload-identity-pools providers describe GITHUB_PROVIDER_ID --location=global \
  --workload-identity-pool=POOL_ID --project=GCP_PROJECT_ID
gcloud iam service-accounts get-iam-policy SERVICE_ACCOUNT_EMAIL --project=GCP_PROJECT_ID
```

Record: which service accounts the GitHub identity can impersonate, and what roles each service
account holds. Every service account listed gets the same review in step 4. Check the
organisation policies for a list of allowed external identity providers; if one exists, GitLab's
issuer may need an exception before step 3 works.

## Step 2: issuer and audience

Read the issuer from the instance:

```sh
curl -s https://GITLAB_HOST/.well-known/openid-configuration | python3 -c "import json,sys; print(json.load(sys.stdin)['issuer'])"
```

Use that exact string as `--issuer-uri`. On the read date gitlab.com returned `https://gitlab.com`
with no trailing slash, while GitLab's Google Cloud page asks for a trailing slash in the console
form. If the exchange later reports an issuer mismatch, compare the provider's issuer with the
token's `iss` claim (step 6 shows how to print claims safely).

Allowed audience: GitLab's page uses the instance address without a trailing slash, for example
`https://gitlab.com`. Set it explicitly with `--allowed-audiences` and give the same value as `aud`
in the job's `id_tokens`. A job may carry several tokens with different `aud` values; give each
cloud its own.

## Step 3: create the GitLab provider

Only if the pool does not exist yet:

```sh
gcloud iam workload-identity-pools create POOL_ID --location=global \
  --project=GCP_PROJECT_ID --display-name="CI pool"
```

The provider. `GITLAB_PROJECT_ID` is the numeric project ID (Project overview page, or
`glab api projects/GROUP%2FPROJECT --jq .id`). Numeric IDs are preferred over paths in the
condition because a path can be reused after a rename or deletion, the same reasoning Google gives
for GitHub's numeric fields.

```sh
gcloud iam workload-identity-pools providers create-oidc gitlab-PROJECT_SLUG \
  --project=GCP_PROJECT_ID --location=global --workload-identity-pool=POOL_ID \
  --display-name="GitLab PROJECT_SLUG" \
  --issuer-uri="ISSUER_FROM_STEP_2" \
  --allowed-audiences="AUDIENCE_FROM_STEP_2" \
  --attribute-mapping="google.subject=assertion.sub,attribute.project_id=assertion.project_id,attribute.project_path=assertion.project_path,attribute.namespace_path=assertion.namespace_path,attribute.ref=assertion.ref,attribute.ref_protected=assertion.ref_protected,attribute.environment=assertion.environment" \
  --attribute-condition="assertion.project_id=='GITLAB_PROJECT_ID' && assertion.ref_protected=='true'"
```

Flags confirmed on Google's reference page: `--issuer-uri`, `--allowed-audiences`,
`--attribute-mapping`, `--attribute-condition`, `--workload-identity-pool`, `--location`,
`--display-name` (up to 32 characters), `--description` (up to 256), `--jwk-json-path`, `--disabled`.

Notes on the mapping and condition:

- Claims come from the GitLab ID token page: `project_id`, `project_path`, `namespace_id`,
  `namespace_path`, `ref`, `ref_type`, `ref_protected` (the string `true` or `false`), and, for jobs
  with an environment, `environment` and `environment_protected`. Re-check the claim list before
  use.
- Every attribute used in a binding must be mapped. Unused mappings are harmless.
- `project_path` in a merge request pipeline is the SOURCE project, and `ref_protected` is false for
  an unprotected source branch, so the condition above refuses fork and feature-branch merge
  request pipelines.
- To also tie the identity to one environment, add `&& assertion.environment=='production'`. Only
  jobs that declare `environment:` carry that claim.
- Google limits the length of `google.subject`. GitLab's default `sub` includes the full project path
  and ref and can exceed it for long group paths. If the provider is refused or exchanges fail for
  that reason, map `google.subject=assertion.project_id` and rely on the attributes for
  authorisation. Check Google's attribute mapping page for the current limit.
- A path-based condition is easier to read: `assertion.project_path=='group/project'`. Use it only
  next to the numeric ID check.

## Step 4: let the pool identity use the service account

```sh
gcloud iam service-accounts add-iam-policy-binding SERVICE_ACCOUNT_EMAIL \
  --project=GCP_PROJECT_ID \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/GCP_PROJECT_NUMBER/locations/global/workloadIdentityPools/POOL_ID/attribute.project_id/GITLAB_PROJECT_ID"
```

`GCP_PROJECT_NUMBER` is the project number (digits) and `POOL_ID` is the pool ID, per GitLab's page.
If the GitHub binding grants a broad service account, use this move to split it: one service
account per purpose (deploy versus read-only) and bind each to the narrowest attribute set.

## Step 5: change the pipeline

Remove `google-github-actions/auth` and `id-token: write`. In the deploy job (build it on the
hardened pipeline from the `ci-harden` skill):

```yaml
deploy:
  id_tokens:
    GITLAB_OIDC_TOKEN:
      aud: AUDIENCE_FROM_STEP_2
  rules:
    - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH
  script:
    - |
      AUDIENCE_PATH="//iam.googleapis.com/projects/$GCP_PROJECT_NUMBER/locations/global/workloadIdentityPools/$WIF_POOL_ID/providers/$WIF_PROVIDER_ID"
      FEDERATED_TOKEN="$(curl --fail-with-body -sS https://sts.googleapis.com/v1/token \
        --header 'Content-Type: application/json' \
        --data "$(jq -n --arg aud "$AUDIENCE_PATH" --arg tok "$GITLAB_OIDC_TOKEN" '{
          audience: $aud,
          grantType: "urn:ietf:params:oauth:grant-type:token-exchange",
          requestedTokenType: "urn:ietf:params:oauth:token-type:access_token",
          scope: "https://www.googleapis.com/auth/cloud-platform",
          subjectTokenType: "urn:ietf:params:oauth:token-type:jwt",
          subjectToken: $tok }')" | jq -r .access_token)"
      CLOUDSDK_AUTH_ACCESS_TOKEN="$(curl --fail-with-body -sS \
        "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/$GCP_SERVICE_ACCOUNT:generateAccessToken" \
        --header 'Content-Type: application/json' \
        --header "Authorization: Bearer $FEDERATED_TOKEN" \
        --data '{"scope": ["https://www.googleapis.com/auth/cloud-platform"]}' | jq -r .accessToken)"
      export CLOUDSDK_AUTH_ACCESS_TOKEN
      gcloud --quiet run deploy ...   # the actual deploy command
```

This follows GitLab's Google Cloud page (token exchange, then `generateAccessToken`). The page says
`CLOUDSDK_AUTH_ACCESS_TOKEN` hands the access token to `gcloud`. The job image needs `curl` and
`jq`. `GCP_PROJECT_NUMBER`, `WIF_POOL_ID`, `WIF_PROVIDER_ID` and `GCP_SERVICE_ACCOUNT` are
identifiers and can be plain CI/CD variables or `variables:` entries. Never
print the token variables.

GitLab's page also links a Terraform module and CI/CD template for this setup. If the team already
uses Terraform for IAM, prefer expressing steps 3 and 4 there and reviewing them as code.

## Step 6: prove the restrictions

A deploy from the protected default branch must succeed. These must fail at the token exchange:

- the same job on an unprotected feature branch
- a merge request pipeline from a branch or fork
- a different GitLab project asking for the same provider

To see claims while debugging, print only the payload fields that are not secret, in a job on a
protected branch, and never the whole token:

```sh
printf '%s' "$GITLAB_OIDC_TOKEN" | cut -d. -f2 | tr '_-' '/+' | base64 -d 2>/dev/null \
  | jq '{iss, aud, project_id, project_path, ref, ref_protected, environment}'
```

## Step 7: retire the GitHub provider

Only after cutover is final and the rollback window has closed. Each command needs its own go and
the `describe` output shown first.

```sh
gcloud iam service-accounts remove-iam-policy-binding SERVICE_ACCOUNT_EMAIL \
  --project=GCP_PROJECT_ID --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/GCP_PROJECT_NUMBER/locations/global/workloadIdentityPools/POOL_ID/attribute.repository/OWNER/REPO"
gcloud iam workload-identity-pools providers delete GITHUB_PROVIDER_ID --location=global \
  --workload-identity-pool=POOL_ID --project=GCP_PROJECT_ID
```

Use the real member string from `get-iam-policy`; the attribute name in the example is a
placeholder for whatever the GitHub binding used. Deleting a provider takes effect for every
workflow that still uses it.

## Self-managed GitLab notes

- The issuer is the instance URL and Google must reach `/.well-known/openid-configuration` and the
  key set it points to. On a private network Google cannot, and the provider cannot verify tokens.
  `--jwk-json-path` uploads a key file instead; the keys then need re-uploading whenever the
  instance rotates them. Confirm with the instance administrator and Google's page before relying
  on it.
- The attribute-condition requirement stated for GitLab.com is stricter than necessary on an
  instance only your organisation uses; keep the project condition anyway.

## Troubleshooting

- Exchange refused: compare `iss` and `aud` in the token with the provider's issuer and allowed
  audiences, then compare the claims with the attribute condition.
- Binding seems ignored: the attribute in the `principalSet` member must be mapped in the provider.
- Use curl's `--fail-with-body` while debugging so Google's error text is visible (GitLab's page
  advises the same).
- Google's page: Troubleshoot Workload Identity Federation (link at the top).
