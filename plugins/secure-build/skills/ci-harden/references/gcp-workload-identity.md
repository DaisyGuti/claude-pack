# Workload Identity Federation for CI

Contents:
- What this replaces
- Everything here is a draft
- GitHub Actions provider
- GitLab provider
- Service account and bindings
- Prove the restrictions
- Direct federation without a service account
- Sources

## What this replaces

A downloaded service-account key is a long-lived password: it never expires, it leaks through logs
and backups, and it works from anywhere. Workload Identity Federation (WIF) lets the CI job
present its own short-lived OIDC token and receive a short-lived Google access token, so there is
no key to store. `gcp-review` flags the user-managed keys that remain in a project, and Google's
organization policy `constraints/iam.disableServiceAccountKeyCreation` stops new ones.

## Everything here is a draft

These commands change a cloud project. Show them with the placeholders named and let a project
owner run them. Reads (`list`, `describe`, `get-iam-policy`) can run without a go.

An **attribute condition is required**: without one, any repository or project that
the issuer vouches for could ask for tokens, and every GitHub and GitLab.com customer shares one
issuer.

## GitHub Actions provider

`REPO_ID` is the numeric repository ID: `gh api repos/ORG/REPO --jq .id`.

```sh
gcloud iam workload-identity-pools create github \
  --project=PROJECT_ID --location=global --display-name="GitHub Actions"

gcloud iam workload-identity-pools providers create-oidc REPO_SLUG \
  --project=PROJECT_ID --location=global --workload-identity-pool=github \
  --display-name="GitHub REPO_SLUG" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.repository_id=assertion.repository_id,attribute.ref=assertion.ref,attribute.environment=assertion.environment" \
  --attribute-condition="assertion.repository_id=='REPO_ID' && assertion.environment=='release'"
```

- Claims must be mapped before an attribute condition or IAM binding can use them. Google's
  `google-github-actions/auth` documentation states this and that the condition is a security
  requirement.
- Match on the numeric `repository_id`. GitHub's documentation says repositories created after
  July 15, 2026 use an immutable default `sub` format that includes owner and repository IDs, so a
  condition written against the older `repo:ORG/REPO:...` string can stop matching. Decode a real
  token (below) and confirm the claim values before finalizing the condition.
- The `environment` condition ties the identity to jobs that declare `environment: release`.
  Protection rules on that GitHub environment (required reviewers, a deployment branch and tag
  policy) then decide who can reach the cloud.
- Dependabot update jobs carry an `event_name` of `dynamic`; do not give that event cloud access.

## GitLab provider

`PROJECT_ID` is the numeric project ID: `glab api projects/GROUP%2FPROJECT --jq .id`. Read the
issuer from the instance (gitlab.com returned `https://gitlab.com` with no
trailing slash on the read date):

```sh
curl -s https://GITLAB_HOST/.well-known/openid-configuration | python3 -c "import json,sys; print(json.load(sys.stdin)['issuer'])"
```

```sh
gcloud iam workload-identity-pools providers create-oidc gitlab-PROJECT_SLUG \
  --project=PROJECT_ID --location=global --workload-identity-pool=POOL_ID \
  --display-name="GitLab PROJECT_SLUG" \
  --issuer-uri="ISSUER" \
  --allowed-audiences="https://GITLAB_HOST" \
  --attribute-mapping="google.subject=assertion.sub,attribute.project_id=assertion.project_id,attribute.project_path=assertion.project_path,attribute.ref=assertion.ref,attribute.ref_protected=assertion.ref_protected,attribute.environment=assertion.environment" \
  --attribute-condition="assertion.project_id=='PROJECT_ID_NUMBER' && assertion.ref_protected=='true'"
```

The `aud` in the job's `id_tokens:` entry must equal one of the allowed audiences. The condition
limits access to one project and to protected branches and tags, so a merge request from an
unprotected branch cannot reach the cloud. The `gitlab-migration` skill's
`references/gcp-wif-trust.md` walks the same provider step by step, including the Security Token
Service exchange, self-managed notes and troubleshooting; read it when the task is moving from
GitHub to GitLab.

## Service account and bindings

One service account per purpose. The publisher needs write access to one Artifact Registry
repository and nothing else.

```sh
gcloud iam service-accounts create ci-publisher --project=PROJECT_ID \
  --display-name="CI image publisher"

# Let the federated identity impersonate it (GitHub example; GitLab uses attribute.project_id).
gcloud iam service-accounts add-iam-policy-binding \
  ci-publisher@PROJECT_ID.iam.gserviceaccount.com --project=PROJECT_ID \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github/attribute.repository_id/REPO_ID"

# Let it push to one repository.
gcloud artifacts repositories add-iam-policy-binding REPOSITORY \
  --project=PROJECT_ID --location=LOCATION \
  --member="serviceAccount:ci-publisher@PROJECT_ID.iam.gserviceaccount.com" \
  --role=roles/artifactregistry.writer
```

`PROJECT_NUMBER` is the digits-only project number. The pipeline's variables are the provider
resource name (`projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/POOL/providers/PROVIDER`)
and the service account email. Neither is a secret.

## Prove the restrictions

A run from the allowed repository on the protected environment must succeed. These must fail at
the token exchange, and the user should try each once:

- the same workflow from a fork or another repository or project
- a branch or tag the environment's deployment policy does not allow
- a GitLab pipeline on an unprotected branch

To inspect claims while debugging, decode only the payload of a token in a throwaway project and
never paste a whole token anywhere:

```sh
printf '%s' "$TOKEN" | cut -d. -f2 | tr '_-' '/+' | base64 -d 2>/dev/null | python3 -m json.tool
```

## Direct federation without a service account

`google-github-actions/auth` documents a direct mode in which the federated identity holds the
IAM roles itself (granted to a `principalSet://...` member) and no service account is involved.
Tokens last at most 10 minutes, and not every Google Cloud service accepts a `principalSet`
member. This plugin's pipelines use a service account because that works everywhere. Check
Google's list of supported products for Artifact Registry before choosing the direct mode.

## Sources

Fetched 2026-10-16.

- google-github-actions/auth: https://github.com/google-github-actions/auth
- GitHub OIDC claims: https://docs.github.com/en/actions/concepts/security/openid-connect
- GitHub, OIDC in Google Cloud: https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-google-cloud-platform
- GitLab ID token claims: https://docs.gitlab.com/ci/secrets/id_token_authentication/
- GitLab and Google Cloud: https://docs.gitlab.com/ci/cloud_services/google_cloud/
- Google, `create-oidc` reference (flags confirmed by the `gitlab-migration` skill's build): https://docs.cloud.google.com/sdk/gcloud/reference/iam/workload-identity-pools/providers/create-oidc
- Artifact Registry authentication: https://docs.cloud.google.com/artifact-registry/docs/docker/authentication
