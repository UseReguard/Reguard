# Trusted Publishing Setup — UseReguard/Reguard → PyPI + GHCR

**Date:** 2026-08-30
**Status:** WORKFLOW PREPARED · OWNER CONFIGURATION PENDING

The release workflow at `.github/workflows/release.yml` is
prepared. Two owner-operated configuration steps are required
before any tag can be pushed. No long-lived PyPI credentials are
stored in this repository.

---

## 1. PyPI Trusted Publisher

### 1a. Determine current PyPI project status for `reguard`

Two cases:

**Case A — project `reguard` does not yet exist on PyPI.**

- Do NOT attempt to claim or create it during this preparation phase.
- The owner manually registers a **Pending Trusted Publisher** for
  `reguard` from the PyPI side:

  1. Visit <https://pypi.org/manage/account/publishing/> (PyPI
     account → Publishing → Add a new pending publisher).
  2. Fill in exactly:

     ```text
     PyPI project name : reguard
     Owner             : UseReguard
     Repository        : Reguard
     Workflow filename : release.yml
     Environment name  : pypi
     ```

  3. Submit. The pending publisher is consumed on the first
     successful OIDC handshake from the workflow.

**Case B — project `reguard` already exists and is controlled by the
owner.**

- Visit <https://pypi.org/project/reguard/> → "Publishing" tab →
  Add a trusted publisher.
- Fill in the same five fields as Case A.

### 1b. Configure the GitHub `pypi` environment

In the GitHub repository:

1. Visit `https://github.com/UseReguard/Reguard/settings/environments`.
2. Click **New environment** → name `pypi`.
3. (Optional but recommended) **Required reviewers**: add the
   repository owner. Reviewers are only required on non-`workflow_dispatch`
   trigger paths and the release workflow is tag-triggered; verify
   that the chosen setting does not block tag pushes.
4. Save. No secrets are required in this environment —
   OIDC handles authentication.

### 1c. What the workflow does on first tag push

The first tag push (`v0.1.0-rc.1` or later) triggers:

- `validate` — checks `pyproject.toml` `[project].version` matches
  the tag.
- `build` — runs `pytest`, builds the exact wheel + sdist, runs
  `twine check`, uploads artifacts.
- `publish-pypi` — uses `pypa/gh-action-pypi-publish@release/v1`
  with OIDC. PyPI verifies the workflow identity against the
  Trusted Publisher record and accepts the upload. No API token
  is ever present in the repository or runner environment.

---

## 2. GHCR Authentication

GHCR authentication uses the repository's built-in
`secrets.GITHUB_TOKEN`. No personal access token is required.

The `publish-runtime` job declares:

```yaml
permissions:
  contents: read
  packages: write
```

and logs in via:

```yaml
- uses: docker/login-action@v3
  with:
    registry: ghcr.io
    username: ${{ github.actor }}
    password: ${{ secrets.GITHUB_TOKEN }}
```

### 2a. Owner verification steps

1. Visit `https://github.com/UseReguard/Reguard/settings/actions`
   and confirm **Workflow permissions** is at least:
   - "Read and write permissions", OR
   - "Read repository contents and packages permissions" (this is
     sufficient for `contents: read` + `packages: write`).
2. If `UseReguard` is an organization, visit
   `https://github.com/organizations/UseReguard/settings/packages`
   and confirm that members may publish packages to the
   organization. Otherwise the first push will fail with
   `403 Forbidden` and a link to the org settings page.
3. No additional secrets are required.

### 2b. What the workflow does on first tag push

- Builds `runtime/Dockerfile` from the project root.
- Tags the resulting image as:
  - `ghcr.io/usereguard/reguard-runtime:v0.1.0-rc.1`
  - `ghcr.io/usereguard/reguard-runtime:<release-source-sha>`
- Pushes both via `docker/build-push-action@v6`.
- The published digest is recorded in `${{ steps.build.outputs.digest }}`
  and surfaces in the run summary.

---

## 3. What the owner does NOT need to do

- Create or store any PyPI API token.
- Create or store any GHCR personal access token.
- Configure a `package_write` PAT anywhere.
- Edit `release.yml` before the first tag push.

---

## 4. Stop conditions

The preparation phase stops at:

- Workflow `release.yml` written and committed.
- Source tree normalized to `UseReguard/Reguard` references.
- Manifest hashes pending until final rebuild.
- No tag pushed.
- No PyPI upload attempted.
- No GHCR push attempted.

The next owner-authorized phase is the actual tag push
(`git tag -a v0.1.0-rc.1 … && git push origin v0.1.0-rc.1`),
which then triggers the workflow end-to-end. Until that tag push
happens, no external publication occurs.

— end of trusted publishing setup —
