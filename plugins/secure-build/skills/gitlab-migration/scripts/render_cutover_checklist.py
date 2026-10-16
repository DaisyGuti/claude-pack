#!/usr/bin/env python3
"""Turn an inventory (from inventory_github_repo.py --format json) into a cutover checklist.

Read-only. Prints markdown with one checkbox per task, tailored to what the inventory found:
one task per workflow file, one per secret name, a Google Cloud trust section only when the
workflows use OIDC, a CODEOWNERS move only when the file sits in `.github/`, and so on.

Usage:
    inventory_github_repo.py REPO --format json | render_cutover_checklist.py -
    render_cutover_checklist.py inventory.json [--gitlab-host HOST] [--gitlab-path GROUP/PROJECT]
                                [--github-repo OWNER/NAME] [--tier free|premium|ultimate|unknown]

The checklist names secrets and carries no values. Tier tags come from GitLab's own pages as fetched
when this skill was written; the skill tells Claude to re-check them at run time.

Exit codes: 0 checklist printed, 2 bad input (file missing, invalid JSON, wrong shape).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

EXPECTED_SCHEMA_PREFIX = "gitlab-migration-inventory/"

TIER_RANK = {"free": 0, "premium": 1, "ultimate": 2}

IMPORTER_DOC = "https://docs.gitlab.com/user/project/import/github/"

# Dependabot ecosystem name -> Renovate manager name. Renovate detects most of these on its own;
# the names are listed so a person can confirm each ecosystem is covered.
RENOVATE_MANAGER = {
    "npm": "npm",
    "pip": "pip_requirements, pep621, poetry",
    "gomod": "gomod",
    "maven": "maven",
    "gradle": "gradle",
    "docker": "dockerfile",
    "github-actions": "none needed after the move (GitHub Actions files are gone)",
    "terraform": "terraform",
    "cargo": "cargo",
    "bundler": "bundler",
    "composer": "composer",
    "nuget": "nuget",
    "gitsubmodule": "git-submodules",
}


def _tier_tag(required: str, tier: str, alternative: str) -> str:
    """Return a short note when a feature needs a higher tier than the project has."""
    needed = TIER_RANK[required]
    if tier == "unknown":
        return (
            f" [needs {required.capitalize()} or higher; confirm the tier. "
            f"Without it: {alternative}]"
        )
    if TIER_RANK[tier] >= needed:
        return ""
    return f" [needs {required.capitalize()}; tier is {tier}. Instead: {alternative}]"


class InputError(Exception):
    """Bad input; the message names the input and the fix."""


def _load_inventory(source: str) -> dict[str, Any]:
    try:
        raw = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
    except OSError as err:
        raise InputError(
            f"cannot read {source!r}: {err}. Pass the JSON written by "
            "inventory_github_repo.py (--format json), or '-' for stdin."
        ) from err
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as err:
        raise InputError(
            f"{source!r} is not valid JSON ({err}). "
            "Create it with: inventory_github_repo.py REPO --format json"
        ) from err
    schema = data.get("schema", "") if isinstance(data, dict) else ""
    if not str(schema).startswith(EXPECTED_SCHEMA_PREFIX):
        raise InputError(
            f"{source!r} is not an inventory (schema {schema!r}, expected "
            f"{EXPECTED_SCHEMA_PREFIX}*). Regenerate it with inventory_github_repo.py."
        )
    return data


def render(
    inv: dict[str, Any],
    *,
    gitlab_host: str,
    gitlab_path: str,
    github_repo: str,
    tier: str,
) -> str:
    lines: list[str] = []
    add = lines.append
    self_managed = gitlab_host != "gitlab.com"

    add("# Cutover checklist: GitHub to GitLab")
    add("")
    add(f"- Source: `{github_repo}` on GitHub")
    add(
        f"- Target: `{gitlab_path}` on `{gitlab_host}` "
        f"({'self-managed' if self_managed else 'SaaS'})"
    )
    add(f"- GitLab tier: {tier}")
    add("- Secret values never appear in this list. They come from the team's password manager.")
    add("")

    add("## 0. Decisions before anything runs")
    add("")
    add(f"- [ ] Confirm host `{gitlab_host}`, target path `{gitlab_path}` and the GitLab tier.")
    add(
        "- [ ] Confirm the person running the import has the Maintainer or Owner role on the "
        "target group."
    )
    add("- [ ] Name one cutover owner and one backup. Pick the freeze window.")
    add("- [ ] Decide the mirror length and direction (section 9). Write the end date down.")
    if self_managed:
        add(
            "- [ ] Self-managed: read the documentation shipped with your instance at "
            f"`https://{gitlab_host}/help`. The public pages describe the newest release, which "
            "may be "
            "ahead of the instance."
        )
        add(
            "- [ ] Self-managed: ask the administrator to enable the GitHub import source and "
            "confirm the instance can reach GitHub."
        )
    add("")

    add("## 1. Before the import")
    add("")
    add(f"- [ ] Re-read the importer page for changes: {IMPORTER_DOC}")
    add(
        "- [ ] Scan the full Git history for committed secrets before it reaches a new host "
        "(gitleaks)."
    )
    add("- [ ] List open pull requests. Merge, close or plan to re-create each one.")
    add(
        "- [ ] The person running the import creates a classic GitHub personal access token with "
        "the `repo` scope (add `read:org` for collaborators or LFS). The token is entered only in "
        "their own terminal or the GitLab form, never in chat."
    )
    add(
        "- [ ] Check user mapping: contributors need to exist in GitLab before the import finishes."
    )
    add("- [ ] Record the current GitHub settings the checkout cannot show (section 7 lists them).")
    if inv["lfs"]["used"]:
        add(
            "- [ ] Git LFS is in use: the token needs `read:org`, and `.lfsconfig` must not point "
            "at another host."
        )
    add("")

    add("## 2. Import")
    add("")
    add("- [ ] Draft the import command or UI steps (see references/importer.md). Show them.")
    add("- [ ] Get the go for the import. Run it. Record the project ID and start time.")
    add(
        "- [ ] Wait for the status to reach Complete or Partially completed. Open Details for any "
        "failed entity."
    )
    add("")

    add("## 3. Verify the import")
    add("")
    add("- [ ] Compare branch and tag lists between the two hosts.")
    add("- [ ] Compare issue, pull request (merge request), label, milestone and release totals.")
    add("- [ ] Open a few older merge requests and check comments, reviews and attachments.")
    add("- [ ] Check members and roles. Collaborators may have been added with high roles.")
    add("- [ ] Check the wiki, if the project had one.")
    if inv["lfs"]["used"]:
        add(
            "- [ ] Clone the new project and run `git lfs pull` to confirm the LFS objects arrived."
        )
    add("")

    add("## 4. Pipelines")
    add("")
    add(
        "- [ ] Start from the hardened reference pipeline in the `ci-harden` skill, then add "
        "project-specific jobs."
    )
    workflows = inv["workflows"]
    if not workflows:
        add(
            "- [ ] No workflow files were found. Confirm there is no other CI (external service) "
            "to move."
        )
    for workflow in workflows:
        events = [t["event"] for t in workflow.get("triggers", [])]
        jobs = [j["id"] for j in workflow.get("jobs", [])]
        detail = f"triggers: {', '.join(events) or 'unknown'}; jobs: {', '.join(jobs) or 'unknown'}"
        add(f"- [ ] Translate `{workflow['file']}` ({detail}).")
        if not workflow["parsed"]:
            add(f"  - [ ] Could not be parsed ({workflow['parse_error']}). Read the file by hand.")
        for flag in workflow.get("flags", []):
            if flag["severity"] in ("manual", "review") and flag["id"] != "parse-failed":
                add(f"  - [ ] `{flag['id']}`: {flag['message']}")
    labels = sorted(
        {
            label
            for workflow in workflows
            for job in workflow.get("jobs", [])
            if job.get("self_hosted")
            for label in job["runs_on"]
        }
    )
    if labels:
        add(
            "- [ ] Register GitLab runners (or pick shared runners) and give them tags matching: "
            + ", ".join(f"`{label}`" for label in labels)
            + "."
        )
    add("- [ ] Create pipeline schedules in the GitLab project for every `schedule` trigger.")
    add("- [ ] Run a pipeline on a branch and on a merge request. Both must pass before cutover.")
    add("")

    add("## 5. Secrets and variables")
    add("")
    add(
        "- [ ] Create each secret below as a CI/CD variable. Values come from the password manager "
        "through stdin or a prompt, never from chat or a file. For each one decide: masked, "
        "protected (when only protected branches and tags need it), environment scope, "
        "and File type for multi-line values."
    )
    for name in inv["secret_names"]:
        add(f"  - [ ] `{name}`")
    if not inv["secret_names"]:
        add(
            "  - [ ] No `secrets.*` names found in workflows. Check organization-level secrets in "
            "GitHub."
        )
    if inv["variable_names"]:
        add("- [ ] Recreate each repository variable (`vars.*`) as a CI/CD variable:")
        for name in inv["variable_names"]:
            add(f"  - [ ] `{name}`")
    if inv["uses_github_token"]:
        add(
            "- [ ] `GITHUB_TOKEN` is used. Replace with `CI_JOB_TOKEN`, or a project access token "
            "if a job "
            "needs more than the job token allows."
        )
    if inv["environments"]:
        add(
            "- [ ] Recreate environments: " + ", ".join(f"`{e}`" for e in inv["environments"]) + "."
        )
    add(
        "- [ ] Check masking limits for each value (length, characters). Use a File type variable "
        "for multi-line values."
    )
    add("")

    if inv["gcp_workload_identity"]:
        add("## 6. Google Cloud trust (Workload Identity Federation)")
        add("")
        add(
            "- [ ] Find the current pool, provider and service account in the workflow files "
            "(read them, do not guess)."
        )
        add(
            "- [ ] Fetch the current Google and GitLab pages (references/gcp-wif-trust.md) and "
            "compare the flags."
        )
        add(
            f"- [ ] Read the issuer from `https://{gitlab_host}/.well-known/openid-configuration` "
            "and use it exactly."
        )
        add(
            "- [ ] Draft the new OIDC provider with an attribute condition tied to the project "
            "path and protected refs."
        )
        add("- [ ] Draft the service account binding using the project path attribute.")
        add(
            "- [ ] Add `id_tokens:` with an `aud` to the deploy jobs. Run one deploy from a "
            "protected branch."
        )
        add("- [ ] Confirm an unprotected branch and a fork merge request are refused.")
        add("- [ ] Keep the GitHub provider until cutover is final, then remove it.")
        add("")

    add("## 7. Repository rules and settings")
    add("")
    add(
        "These live in GitHub settings and are not visible in the checkout. Read them with `gh` "
        "(reads only) "
        "and compare against what the importer created:"
    )
    add("")
    add(
        "- [ ] Branch protection rules or rulesets (the importer maps most of them; required "
        "status checks are not imported)."
    )
    add("- [ ] Protected branches in GitLab: default branch, release branches, tags.")
    add("- [ ] Required status checks -> 'Pipelines must succeed' in merge request settings.")
    add(
        "- [ ] Approval rules and number of approvals"
        + _tier_tag(
            "premium",
            tier,
            "approvals are optional on Free and do not block merging; rely on review habits and CI",
        )
    )
    add(
        "- [ ] Push rules (signed commits, branch name, file size)"
        + _tier_tag("premium", tier, "enforce with CI checks")
    )
    add("- [ ] Merge method, squash and delete-source-branch defaults.")
    add(
        "- [ ] Deploy keys, webhooks, GitHub Apps and Pages: list each from GitHub settings and "
        "decide its GitLab equivalent."
    )
    co = inv["codeowners"]
    if co["found"]:
        add(
            "- [ ] CODEOWNERS"
            + _tier_tag("premium", tier, "document owners in the README; there is no enforcement")
        )
        if not co["gitlab_ready"]:
            add(
                "  - [ ] Move the file from `.github/CODEOWNERS` to the repository root, `docs/` "
                "or `.gitlab/`."
            )
        for owner in co["team_owners"]:
            add(f"  - [ ] Replace team owner `{owner}` with GitLab users or a group.")
        if co.get("inline_comments"):
            add(
                "  - [ ] Move inline comments onto their own lines (GitLab does not support "
                "inline comments and still parses owners named in them)."
            )
        add("  - [ ] Turn on Code Owner approval on the protected branches.")
    dep = inv["dependabot"]
    if dep:
        add("- [ ] Dependency updates: Dependabot has no GitLab version.")
        add(
            "  - [ ] Choose Renovate (templates/renovate.json) or scanners in CI (osv-scanner, "
            "trivy)."
        )
        if dep["parsed"]:
            for update in dep["updates"]:
                manager = RENOVATE_MANAGER.get(
                    update["ecosystem"], "check the Renovate manager list"
                )
                add(
                    f"  - [ ] `{update['ecosystem']}` ({update['interval'] or 'no interval'}): "
                    f"Renovate manager {manager}"
                )
        else:
            add(f"  - [ ] `{dep['file']}` could not be parsed; list its ecosystems by hand.")
        if dep.get("registries_configured"):
            add(
                "  - [ ] Private registries are configured; add Renovate host rules (credentials "
                "from a CI/CD variable)."
            )
    for extra in inv["github_extras"]:
        add(f"- [ ] `{extra['path']}`: {extra['gitlab_destination']}")
    add("")

    add("## 8. Integrations and notifications")
    add("")
    add(
        "- [ ] Webhooks: list GitHub's, recreate in GitLab (project webhooks), test each with the "
        "test button."
    )
    add(
        "- [ ] Slack: install the GitLab for Slack app and subscribe channels. For wider Slack "
        "work use the "
        "`team-comms` plugin."
    )
    add("- [ ] Chat, ticket and status tools that read GitHub: repoint each.")
    add(
        "- [ ] Add the GitLab remote URL to anything that clones the repository (build servers, "
        "deploy hosts)."
    )
    add("")

    add("## 9. Mirror period")
    add("")
    add(
        "- [ ] Choose the direction. GitLab as the new home with GitHub as a copy: push mirror "
        "from GitLab "
        "(available in every tier)."
    )
    add(
        "- [ ] GitLab pulling from GitHub keeps GitHub as the source of truth"
        + _tier_tag("premium", tier, "use a push mirror or a scheduled CI job")
        + ". Do not push to the mirror side."
    )
    add(
        "- [ ] Mirrors do not carry pull requests, issues or merge requests. State this to the "
        "team."
    )
    add("- [ ] Write the freeze rule: after cutover, nobody pushes to GitHub.")
    add("- [ ] Set the end date for the mirror and add it to the calendar.")
    add("")

    add("## 10. Links and URLs")
    add("")
    refs = inv["references"]
    add("- [ ] Update hard-coded GitHub references (list below comes from the inventory):")
    if refs["counts"]:
        for kind, count in refs["counts"].items():
            add(f"  - [ ] `{kind}`: {count} found")
        shown = [i for i in refs["items"] if i["own_repo"] is not False][:40]
        for item in shown:
            add(f"    - `{item['file']}:{item['line']}` {item['text']}")
    else:
        add("  - [ ] None found in the checkout.")
    if inv["submodules"]:
        for module in inv["submodules"]:
            note = "relative URL, follows the superproject" if module["relative"] else module["url"]
            add(f"- [ ] Submodule `{module['path']}`: {note}")
    if refs.get("go_module"):
        add(
            f"- [ ] Go module path `{refs['go_module']}`: decide whether to keep the old path or "
            "change imports."
        )
    add(
        "- [ ] Package registries, container images and docs sites: publish to the new location, "
        "then repoint consumers."
    )
    add("- [ ] README badges and docs links.")
    add(
        "- [ ] Each developer: `git remote set-url origin <new URL>` (drafted in "
        "references/cutover-and-rollback.md)."
    )
    add("")

    add("## 11. Cutover day")
    add("")
    add("- [ ] Announce the freeze. Merge or park open work.")
    add("- [ ] Run a final import or mirror sync. Compare the default branch SHA on both hosts.")
    add(
        "- [ ] Protect branches and turn on 'Pipelines must succeed' (only after one passing "
        "pipeline exists)."
    )
    add("- [ ] Switch deploy credentials and triggers to GitLab.")
    add("- [ ] Developers update remotes. Confirm a push from a fresh clone works.")
    add("- [ ] Watch the first pipelines on the default branch.")
    add("")

    add("## 12. Rollback")
    add("")
    add(
        "- [ ] Keep the GitHub repository unarchived and its Actions enabled until the rollback "
        "window closes."
    )
    add("- [ ] Keep the GitHub Workload Identity provider until then.")
    add(
        "- [ ] Rollback trigger: write down what failure sends the team back (for example, a "
        "failed production deploy)."
    )
    add(
        "- [ ] Rollback steps: push the latest GitLab default branch to GitHub, re-enable "
        "Actions, repoint remotes."
    )
    add("")

    add("## 13. After cutover")
    add("")
    add("- [ ] Archive the GitHub repository. This needs a second explicit confirmation.")
    add("- [ ] Remove the GitHub provider from the Google Cloud pool.")
    add(
        "- [ ] Revoke the GitHub token used for the import and rotate any secret that passed "
        "through the move."
    )
    add(
        "- [ ] Remove stale secrets and variables in GitHub settings (the user does this directly)."
    )
    add("- [ ] End the mirror on the agreed date.")
    add("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render a tailored GitHub-to-GitLab cutover checklist from an inventory."
    )
    parser.add_argument("inventory", help="inventory JSON file, or '-' to read it from stdin")
    parser.add_argument(
        "--gitlab-host", default="gitlab.com", help="GitLab host (default: gitlab.com)"
    )
    parser.add_argument("--gitlab-path", default="GROUP/PROJECT", help="target group/project path")
    parser.add_argument(
        "--github-repo", default="", help="source OWNER/NAME (default: from the inventory)"
    )
    parser.add_argument(
        "--tier",
        choices=("free", "premium", "ultimate", "unknown"),
        default="unknown",
        help="GitLab tier of the target project (default: unknown)",
    )
    args = parser.parse_args(argv)

    try:
        inventory = _load_inventory(args.inventory)
    except InputError as err:
        print(f"render_cutover_checklist.py: {err}", file=sys.stderr)
        return 2
    github_repo = args.github_repo or inventory.get("origin", {}).get("owner_repo") or "OWNER/NAME"
    print(
        render(
            inventory,
            gitlab_host=args.gitlab_host,
            gitlab_path=args.gitlab_path,
            github_repo=github_repo,
            tier=args.tier,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
