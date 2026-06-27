# GlitchOS Infrastructure Truth Audit

**Lane:** 3 — Infrastructure Truth
**Worktree:** `/mnt/c/Users/Glytc/glytchdraft-infrastructure-truth`
**Branch:** `audit/infrastructure-truth`
**Baseline SHA:** `7bcaab1cfa239fb68ead4dacf7b627e5d05505c1`
**Audit date:** 2026-06-27
**Auditor account:** `charles.hope.design@gmail.com`
**Machine:** `jaDeFireLoom1` · WSL Ubuntu 24.04.3 LTS · kernel 6.6.87.2-microsoft-standard-WSL2

---

## 1. Executive Summary

GlitchOS has **one active cloud deployment**: a Cloud Run service (`glitchos-viewer-staging`) deployed 2026-06-25 in Google Cloud project `glitchos-staging-charles`, serving the viewer application at a `.run.app` URL. No Compute Engine instances exist; the Compute Engine API is disabled. No static IPs, firewall rules, or snapshots are accessible.

**Three service accounts** are present and configured in the project. Recent authenticated use was not directly verified during this audit. One **Artifact Registry** Docker repository holds the current viewer image. One **Cloud Storage bucket** holds Cloud Build source artifacts (~21.6 MB). A **$25/month budget cap** with alert thresholds is configured, but no notification destination is set.

**No other cloud services are confirmed active.** Vercel is authenticated but has zero projects. Railway, Supabase, AWS, and Cloudflare CLIs are absent. These services are referenced in specifications and setup documents but cannot be confirmed deployed from available evidence.

**Primary storage is the Samsung T7 Shield** (Windows `E:`, WSL `/mnt/t7`), holding 5 city datasets. The T7 reports Windows health status **Warning** — an unresolved operational risk. No cloud backup of T7 data is in evidence.

**Highest risks:** single-machine dataset dependency on a Warning-state drive, no confirmed backup strategy, and infrastructure decisions about Cloudflare R2, Supabase, and Vercel that remain unverified deployments.

---

## 2. Audit Scope and Restrictions

**Scope:** Read-only inventory of infrastructure associated with GlitchOS / GlytchDraft / Labor & Code.

**Evidence threshold for inclusion:** A resource is included as GlitchOS infrastructure only when:
- The repository explicitly references it, OR
- Its name/description/metadata explicitly references the project, OR
- A handoff or infrastructure document identifies it, OR
- The founder explicitly confirms it.

**Absolute restrictions honored throughout:**
- No cloud resource created, modified, started, stopped, or deleted
- No APIs enabled
- No secrets retrieved or printed
- No billing settings changed
- No DNS or DNS configuration changed
- No Vercel/Railway/Supabase/GitHub settings changed
- No environment files edited
- No pipeline or viewer code modified
- No branches switched, merged, rebased, or force-pushed
- No other worktrees accessed

**Authentication safety check:**
No command during this audit initiated a login, changed the active account, changed the active GCP project, enabled an API, modified a configuration, or retrieved a secret value. Confirmed `No` on all counts.

---

## 3. Repository Baseline

| Item | Value |
|------|-------|
| Repository | `aetherbeing/glytchdraft` |
| Remote | `https://github.com/aetherbeing/glytchdraft.git` |
| Audit branch | `audit/infrastructure-truth` |
| Baseline SHA | `7bcaab1cfa239fb68ead4dacf7b627e5d05505c1` |
| Working-tree status | Clean |
| Default branch | `master` |
| Repository visibility | Public |

**Branches present on remote (verified via `gh api`):**

| Branch | Apparent Purpose |
|--------|-----------------|
| `master` | Default, production pipeline |
| `codex/facade-diagnostic-prototype` | Codex lane — facade geometry |
| `codex/facade-synthesis` | Codex lane — facade synthesis |
| `codex/material-evidence-adapters` | Codex lane — materials |
| `codex/materials-system` | Codex lane — materials system |
| `codex/roof-diagnostic-prototype` | Codex lane — roofs |
| `codex/roof-feasibility` | Codex lane — roof feasibility |
| `docs/canonical-truth` | Canonical documentation sprint (pushed 2026-06-27) |
| `integration/quad-lanes` | Integration of roof/material/facade lanes |
| `audit/infrastructure-truth` | This audit lane |

---

## 4. Local Machine and Storage Topology

### 4.1 Machine

| Item | Value |
|------|-------|
| Hostname | `jaDeFireLoom1` |
| OS | Ubuntu 24.04.3 LTS (Noble Numbat) |
| Platform | WSL2 on Windows |
| Kernel | 6.6.87.2-microsoft-standard-WSL2 |
| WSL user | `gytchdrafter` |

### 4.2 Mounted Volumes

| Mount | Windows Volume | Filesystem | Size | Used | Status |
|-------|---------------|------------|------|------|--------|
| `/` (WSL root, `/dev/sdd`) | WSL virtual disk | ext4 | 1007 GB | 70 GB (7%) | Healthy |
| `/mnt/c` | `C:` (WD Green SN350 2TB, internal) | NTFS | 1.9 TB | 564 GB (31%) | Healthy |
| `/mnt/e` | `E:` — Samsung PSSD T7 Shield | exFAT | 1.9 TB | 404 GB (22%) | **Warning** |
| `/mnt/t7` | Same device as `E:` | exFAT | 1.9 TB | 404 GB (22%) | **Warning** |

**Note:** `/mnt/e` and `/mnt/t7` resolve to the same physical device (Samsung PSSD T7 Shield, Disk 1). The WSL auto-mount is `/mnt/e`; `/mnt/t7` is a bind-mount alias.

### 4.3 Samsung T7 Shield — VERIFIED details

| Item | Value |
|------|-------|
| Windows drive letter | `E:` |
| Volume label | `SSB` |
| Device | Samsung PSSD T7 Shield (Disk 1) |
| Filesystem | exFAT |
| Windows health status | **Warning** — exact cause unknown, not investigated |
| Capacity | ~2 TB (nominal) |
| Used | ~404 GB |
| WSL canonical alias | `/mnt/t7` |
| Data readable? | Yes — Miami LAZ files confirmed readable via PowerShell |
| Write operations authorized? | No — read-only during this audit |
| chkdsk / repair authorized? | No |

**OPERATIONAL RISK:** `Warning` health status in Windows Disk Management is unresolved. Files are currently readable but the status indicates a filesystem-level issue. No confirmed backup of the datasets on this drive exists.

### 4.4 City Datasets on T7 (`/mnt/e` / `/mnt/t7`)

| City directory | Status | Notes |
|----------------|--------|-------|
| `detroit/` | VERIFIED present | Size unknown (scan not performed) |
| `la/` | VERIFIED present | Contains LA LiDAR tiles per pipeline docs |
| `miami/` | VERIFIED present | `data_raw/`, `data_processed/`, `exports/` confirmed |
| `new_orleans/` | VERIFIED present | Size unknown |
| `nyc/` | VERIFIED present | Size unknown |

**Miami confirmed subdirectory layout (read-only):**
- `/mnt/t7/miami/data_raw/laz/` — USGS LAZ tiles (108 files per HANDOFF.md R11)
- `/mnt/t7/miami/data_processed/` — Pipeline outputs
- `/mnt/t7/miami/exports/` — Processed exports

**Sample LAZ files confirmed present on T7/E: (via PowerShell read):**
- `USGS_LPC_FL_MiamiDade_D23_LID2024_318154_0901.laz` (125.9 MB)
- `USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901.laz` (136.9 MB)
- `USGS_LPC_FL_MiamiDade_D23_LID2024_318454_0901.laz` (99.5 MB)
- `USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901.laz` (114.6 MB)

### 4.5 Local SSD Canary Data (`/mnt/c/Users/Glytc/glitchos_local/`)

| Path | Contents |
|------|----------|
| `glitchos_local/miami/` | Canary 5-tile subset from Phase 03 R12 sprint |

Used for local SSD testing (R12 canary run); not the canonical dataset. Sizes not queried.

### 4.6 Worktrees on `C:` (repo workspaces)

| Directory | Purpose |
|-----------|---------|
| `glytchdraft/` | Primary glytchdraft worktree (Lane 1 diagnostic) |
| `glytchdraft-canonical-truth/` | Closed docs lane worktree (preserved) |
| `glytchdraft-infrastructure-truth/` | This audit lane |
| `glytchdraft-integration/` | Integration worktree |
| `glytchdraft-codex/` | Codex worktree |
| `glytchdraft-facades/` | Facades codex worktree |
| `glytchdraft-materials-next/` | Materials codex worktree |
| `glytchdraft-roofs/` | Roofs codex worktree |
| `glytchdraft-clean/` | Clean worktree |
| `glytchOS/` | GlytchOS viewer (main repo) |
| `glytchOS-gcloud/` | GlytchOS gcloud viewer |
| `glytchOS-viewer-truth/` | Lane 2 viewer QA worktree |
| `atlas_output/` | Atlas pipeline output |
| `atlas_poster_generation/` | Poster generation |

**FINDING:** At least 8 `glytchdraft-*` worktrees exist simultaneously. This level of worktree proliferation is a coordination risk.

---

## 5. Available CLI Tools

| Tool | Found | Version | Auth State |
|------|-------|---------|------------|
| `gcloud` | VERIFIED | 573.0.0 | Authenticated as `charles.hope.design@gmail.com` |
| `gsutil` | VERIFIED | 5.37 | Shares gcloud auth |
| `bq` | VERIFIED | Present | Shares gcloud auth |
| `vercel` | VERIFIED | 54.14.0 | Authenticated as `aetherbeing` |
| `railway` | MISSING | — | BLOCKED |
| `supabase` | MISSING | — | BLOCKED |
| `aws` | MISSING | — | BLOCKED |
| `wrangler` | MISSING | — | BLOCKED |
| `gh` | VERIFIED | 2.45.0 | Authenticated as `aetherbeing` |
| `docker` | MISSING (WSL integration disabled) | — | BLOCKED |

**Evidence source:** `which <tool>` and `<tool> --version` for each, confirmed 2026-06-27.

---

## 6. Google Cloud Inventory

### 6.1 Authentication and Configuration

| Item | Value | Source |
|------|-------|--------|
| Authenticated account | `charles.hope.design@gmail.com` | `gcloud auth list` |
| Active account | `charles.hope.design@gmail.com` | `gcloud auth list` |
| Active project | `glitchos-staging-charles` | `gcloud config list` |
| Active configuration | `default` | `gcloud config list` |
| Only configuration | `default` (one configuration exists) | `gcloud config configurations list` |

### 6.2 GCP Projects Visible to Account

| Project ID | Display Name | Project Number | GlitchOS Association |
|-----------|-------------|----------------|----------------------|
| `glitchos-staging-charles` | GlitchOS Staging | 842618617484 | **PRIMARY — VERIFIED** |
| `local-storm-493816-r2` | My Project 55253 | 106010172328 | VISIBLE TO ACCOUNT — UNVERIFIED |
| `project-55ba75c8-fb4e-4057-ae0` | My First Project | 871307230740 | VISIBLE TO ACCOUNT — UNVERIFIED |
| `project-750cc081-1ef1-4350-880` | My First Project | 986869787957 | VISIBLE TO ACCOUNT — UNVERIFIED |

**Evidence source:** `gcloud projects list`

The three non-GlitchOS projects have no GCS buckets visible and are not inspected further.

### 6.3 Cloud Run Services — `glitchos-staging-charles`

| Item | Value |
|------|-------|
| Service name | `glitchos-viewer-staging` |
| Region | `us-east1` |
| Status | **ACTIVE** |
| URL | `https://glitchos-viewer-staging-842618617484.us-east1.run.app` |
| Last deployed | 2026-06-25T20:13:03Z |
| Deployed by | `glitchos-cloudbuild-deployer@glitchos-staging-charles.iam.gserviceaccount.com` |
| Current revision | `glitchos-viewer-staging-00001-q76` |
| Container image | `us-east1-docker.pkg.dev/glitchos-staging-charles/glitchos/viewer:06e18fcb6925239320d2ac70ddfddf7e9edcf216` |
| Port | 8080 |
| Memory | 256 Mi |
| CPU | 1 |
| Min instances | 0 (scales to zero) |
| Max instances | 2 (per revision) |
| Concurrency | 80 |
| Timeout | 300s |
| Service account | `glitchos-viewer-runtime@glitchos-staging-charles.iam.gserviceaccount.com` |
| Ingress | all |
| Traffic | 100% LATEST |
| Environment variables | None configured in service spec |

**Evidence source:** `gcloud run services describe glitchos-viewer-staging --project=glitchos-staging-charles --region=us-east1`

### 6.4 Artifact Registry — `glitchos-staging-charles`

| Item | Value |
|------|-------|
| Repository name | `glitchos` |
| Format | Docker |
| Mode | Standard |
| Location | `us-east1` |
| Description | GlitchOS viewer Docker images |
| Encryption | Google-managed key |
| Created | 2026-06-25T15:52:51 |
| Size | ~30.8 MB |
| Image | `viewer:06e18fcb6925239320d2ac70ddfddf7e9edcf216` (also tagged `latest`) |
| Image created | 2026-06-25T16:11:32 |

**Evidence source:** `gcloud artifacts repositories list --project=glitchos-staging-charles` and `gcloud artifacts docker images list ...`

### 6.5 Cloud Storage Buckets — `glitchos-staging-charles`

| Bucket | Purpose | Size | Location |
|--------|---------|------|----------|
| `gs://glitchos-staging-charles_cloudbuild/` | Cloud Build source artifacts | ~21.6 MB | — |

**Evidence source:** `gsutil ls -p glitchos-staging-charles` and `gsutil du -s gs://glitchos-staging-charles_cloudbuild/`

No GLB geometry buckets, no dataset backup buckets, no tile asset buckets are present in this project.

### 6.6 Service Accounts — `glitchos-staging-charles`

| Display Name | Email | Status |
|-------------|-------|--------|
| GlitchOS Cloud Build Deployer | `glitchos-cloudbuild-deployer@glitchos-staging-charles.iam.gserviceaccount.com` | PRESENT / CONFIGURED |
| GlitchOS Cloud Run Runtime | `glitchos-viewer-runtime@glitchos-staging-charles.iam.gserviceaccount.com` | PRESENT / CONFIGURED |
| Default compute service account | `842618617484-compute@developer.gserviceaccount.com` | PRESENT / CONFIGURED |

**Evidence source:** `gcloud iam service-accounts list --project=glitchos-staging-charles`

Recent authenticated use was not directly verified for any service account during this audit. Status reflects presence in the project, not confirmed active usage. IAM role assignments were not queried (would require `gcloud projects get-iam-policy` which returns full policy; roles can be inferred from service account names and deployment context).

### 6.7 Cloud Build

| Item | Value |
|------|-------|
| Build triggers | 0 found |
| Recent builds | 0 items listed |
| Build source bucket | `gs://glitchos-staging-charles_cloudbuild/source/` (exists, ~21.6 MB) |

The Cloud Build source bucket contains artifacts from at least one prior build (the 2026-06-25 image). No active triggers are configured.

**FINDING:** The viewer was likely deployed manually via `gcloud builds submit` or `docker push` + `gcloud run deploy`, not via an automated CI/CD trigger. This is an operational risk — deployment is not reproducible without the original build command.

### 6.8 APIs — `glitchos-staging-charles`

| API | Status | Evidence |
|-----|--------|---------|
| Cloud Run | ENABLED | Service deployed and responding |
| Artifact Registry | ENABLED | Repository and image confirmed |
| Cloud Storage | ENABLED | Bucket accessible |
| Cloud Build | LIKELY ENABLED | Source bucket populated |
| Cloud Logging | ENABLED | `_Required` and `_Default` logging sinks present |
| Compute Engine | **DISABLED** | `gcloud compute instances list` returned SERVICE_DISABLED |
| Secret Manager | **DISABLED** | `gcloud secrets list` returned SERVICE_DISABLED |
| Cloud Monitoring | Not queried | — |

### 6.9 Compute Engine — `glitchos-staging-charles`

**STATUS: NOT APPLICABLE — API DISABLED**

`gcloud compute instances list` returned: Compute Engine API not enabled. This confirms no VMs are running under this project. Static IPs and firewall rules could not be queried for the same reason.

### 6.10 Billing — `glitchos-staging-charles`

| Item | Value | Source |
|------|-------|--------|
| Billing account name | `billingAccounts/0123D8-2664EA-4768BC` | `gcloud billing projects describe` |
| Billing enabled | Yes | `gcloud billing projects describe` |
| Budget name | GlitchOS Staging Monthly | `gcloud alpha billing budgets list` |
| Budget amount | $25 USD / month | `gcloud alpha billing budgets list` |
| Budget period | Calendar month | `gcloud alpha billing budgets list` |
| Alert thresholds | 50%, 90%, 100% of current spend | `gcloud alpha billing budgets list` |
| Budget alert action | `allUpdatesRule: {}` — no notification channels configured | `gcloud alpha billing budgets list` |

**FINDING:** The budget has no notification channels (`allUpdatesRule: {}`). Budget alerts will not be sent to any email or Pub/Sub topic unless channels are configured. The budget cap exists but will not generate alerts without a destination.

### 6.11 Logging and Monitoring — `glitchos-staging-charles`

| Item | Value |
|------|-------|
| Logging sinks | `_Required` and `_Default` (GCP standard sinks) |
| Custom logging sinks | None |
| Monitoring dashboards | 0 found |

### 6.12 Secret Manager — `glitchos-staging-charles`

**STATUS: API DISABLED**

`gcloud secrets list` returned: Secret Manager API not enabled. No secrets are stored in Secret Manager for this project. The Cloud Run service has no environment variables in its spec, meaning credentials (if any) are either baked into the Docker image or the service is configured without secrets.

**SECURITY FINDING:** If the viewer requires API keys or credentials, their storage location is unknown. Secret Manager is not in use. No environment variables are set on the Cloud Run service. Credentials may be baked into the container image — this requires founder confirmation.

### 6.13 Domain Mappings — `glitchos-staging-charles`

**STATUS: None found.**

`gcloud beta run domain-mappings list --region=us-east1` returned zero items. The service is accessible only via the `.run.app` URL. No custom domain is mapped to the Cloud Run service.

---

## 7. Vercel Inventory

| Item | Value | Status |
|------|-------|--------|
| CLI version | 54.14.0 | VERIFIED |
| Authenticated account | `aetherbeing` | VERIFIED |
| Team/scope queried | `aetherbeings-projects` | VERIFIED |
| Projects visible to this account | 0 | VERIFIED |
| Deployments visible to this account | 0 | VERIFIED |
| Repository configuration | `vercel.json` present — `cleanUrls: true, trailingSlash: false` | VERIFIED |
| Current deployment status under this account | **NO DEPLOYMENT FOUND** | VERIFIED |
| Deployment through another account or team | UNKNOWN | NOT QUERIED |

**Evidence source:** `vercel whoami`, `vercel ls`, `vercel projects list`

**FINDING:** The CLI is authenticated as `aetherbeing` and `vercel.json` exists in the repository, but no Vercel projects or deployments are visible under the `aetherbeings-projects` scope. Whether a deployment exists under a different team or account cannot be determined from this session. The spec (`docs/GLYTCHOS_SPEC.md`) designates Vercel as the viewer-shell hosting target. Current confirmed deployment is Cloud Run, not Vercel.

**STATUS:** CONFIGURED IN REPOSITORY — NO DEPLOYMENT FOUND UNDER INSPECTED ACCOUNT

---

## 8. Railway Inventory

**STATUS: BLOCKED — CLI not installed.**

`railway` binary not found via `which railway`. No Railway configuration files (`.railway/`, `railway.toml`, `railway.json`) were found in the repository.

**Repository evidence:** No Railway references found in `.yml`, `.json`, `.py`, `.sh`, or `.env*` files.

**STATUS:** MISSING / NOT REFERENCED IN CODEBASE

---

## 9. Supabase Inventory

**STATUS: CLI not installed (BLOCKED for live queries). Repository evidence available.**

### Repository Evidence

| File | Contents |
|------|---------|
| `SUPABASE_SETUP.md` | Full setup guide for Trace Economy persistence layer |
| `frontend/.env.example` | `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` (template values, tracked) |
| `frontend/package.json` | Supabase JS client dependency |
| `tests/test_supabase_scaffold.py` | Scaffold test referencing Supabase |

**Supabase database tables documented in `SUPABASE_SETUP.md`:**
- `users`, `structures`, `trace_balances`, `trace_transactions`
- `claimed_structures`, `claim_history`, `geosocial_posts`, `structure_claim_status`

**Supabase Edge Functions documented:**
- `create-claim`, `get-user-balance`, `list-claimed-structures`
- `get-structure-social-state`, `create-geosocial-post`
- `update-charity-allocation`, `create-transaction-record`

**Required environment variable names (from `SUPABASE_SETUP.md`):**
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `TRACE_ADMIN_API_KEY`

**No Supabase project ID found in the repository.** No `supabase/config.toml` found. No migration files found in `backend/supabase/migrations/` (path referenced in setup doc but directory not confirmed present).

**STATUS:** CONFIGURED IN DOCUMENTATION — ACTIVE DEPLOYMENT UNVERIFIED

**CONTRADICTION:** `SUPABASE_SETUP.md` describes a complete Trace Economy persistence layer. `CLAUDE.md` and `AGENTS.md` explicitly state Phase 1 has no economy, social, UGC, claims, or monetization. The Supabase setup documents a claims/economy system that is out of scope per project constitution documents. Whether a Supabase project was ever created and whether it is currently active requires **FOUNDER-CONFIRMATION-REQUIRED**.

---

## 10. AWS Inventory

**STATUS: CLI not installed (BLOCKED for live queries).**

`aws` binary not found.

**Repository evidence:** `scripts/la/resolve_tile_urls.py` references `https://prd-tnm.s3.amazonaws.com` — this is a **public USGS data source** (National Map), not GlitchOS infrastructure. No project-owned S3 buckets, Lightsail instances, or other AWS resources are referenced.

**STATUS:** NOT PROJECT INFRASTRUCTURE — public USGS data source referenced only

---

## 11. Cloudflare Inventory

**STATUS: CLI not installed (BLOCKED for live queries). Repository evidence available.**

`wrangler` binary not found. No `wrangler.toml`, `.wrangler/`, or `cloudflare.json` configuration files found in repository.

**Repository evidence:**
- `docs/GLYTCHOS_SPEC.md` specifies Cloudflare R2 as the preferred geometry hosting target for GLB tiles
- Spec cites: `"hosting_tier": "r2"` in artifact budget configuration
- No bucket names, account IDs, or R2 endpoints are referenced anywhere in code or config

**STATUS:** SPECIFIED IN ARCHITECTURE DOCUMENT — NO DEPLOYMENT EVIDENCE

The spec designates R2 as the GLB hosting solution; actual deployment has not occurred (GLBs are currently served from the Cloud Run container or local development). **FOUNDER-CONFIRMATION-REQUIRED:** Is Cloudflare R2 still the intended geometry hosting target, or has Cloud Run become the de facto production approach?

---

## 12. GitHub and CI/CD Inventory

### 12.1 Repositories

| Repository | Visibility | Default Branch | Last Updated | Role |
|-----------|-----------|----------------|--------------|------|
| `aetherbeing/glytchdraft` | Public | `master` | 2026-06-27 | Phase 1 pipeline |
| `aetherbeing/glytchOS` | Private | `main` | 2026-06-25 | Phase 2 viewer |
| `aetherbeing/GLYTCHDRAFT_MIAMI_SLICE` | Public | — | 2026-05-04 | HISTORICAL — Miami slice export |
| `aetherbeing/laborandcode` | Private | — | 2026-05-08 | UNKNOWN — possibly company repo |
| `aetherbeing/kaolin_docker` | Private | — | 2025-02-04 | HISTORICAL — Docker/ML tooling |
| `aetherbeing/haunt-place` | Public | — | 2026-03-06 | UNKNOWN — separate project |

**Other repositories** (`color-grid-composer`, `signum`, `marradi-residency`, `RIZZDRIP.AI-TM`, `rizz-drip-salon`, `signal-drift-ai`, `mira-sales-concierge`, `goose-guide-ai`, `my-audit-repo`, `glyph-draft-studio`, `prop-rizz-ai`) — VISIBLE TO ACCOUNT — PROJECT ASSOCIATION UNVERIFIED for GlitchOS.

**Evidence source:** `gh repo list aetherbeing --limit 20`

### 12.2 GitHub Actions

| Repository | Workflows | Status |
|-----------|-----------|--------|
| `aetherbeing/glytchdraft` | 0 workflows | No CI/CD |
| `aetherbeing/glytchOS` | 0 workflows | No CI/CD |

**STATUS:** No GitHub Actions CI/CD exists for either primary GlitchOS repository.

**FINDING:** Deployment has no automated trigger. The Cloud Run service was deployed manually. Any future deployment requires a human to run build and deploy commands.

### 12.3 GitHub CLI Authentication

| Item | Value |
|------|-------|
| Account | `aetherbeing` |
| Protocol | HTTPS |
| Token scopes | `gist`, `read:org`, `repo`, `workflow` |
| Active | Yes |

### 12.4 Branch Protections

Branch protection status was not queried (requires `gh api /repos/aetherbeing/glytchdraft/branches/master/protection`). **STATUS: UNKNOWN**

---

## 13. Domains and DNS Evidence

| Domain | Source | Status |
|--------|--------|--------|
| `glitchos.io` | Referenced in `docs/DATA_PROVENANCE.md` (`https://glitchos.io/data-provenance`) | UNKNOWN — not confirmed active |
| `glitchos-viewer-staging-842618617484.us-east1.run.app` | Cloud Run service URL | ACTIVE — confirmed deployed |

**No DNS configuration files, zone files, or registrar records are present in the repository.**

**IONOS, Squarespace, Zoho:** Referenced in the audit mission brief. No evidence of these services found in any repository file.

**FOUNDER-CONFIRMATION-REQUIRED:**
- Is `glitchos.io` registered and active?
- Who is the domain registrar?
- Is DNS pointing anywhere currently?
- Is it the same as `glytchos.io` (alternate spelling)?

---

## 14. Secrets-Management Model

### 14.1 Current State

| Item | Finding | Status |
|------|---------|--------|
| Secret Manager (GCP) | API disabled — not in use | VERIFIED |
| Cloud Run env vars | None configured on the service | VERIFIED |
| Repository `.env` files | None committed (gitignored per `.gitignore`) | VERIFIED |
| `frontend/.env.example` | Contains variable names only (template values) — tracked | VERIFIED |
| `paths.local.json` | Machine-local paths only — gitignored, not tracked | VERIFIED |

### 14.2 Environment Variable Names Referenced

**From `frontend/.env.example`:**
- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`
- `VITE_OPENAI_API_KEY`
- `VITE_APP_NAME`
- `VITE_APP_VERSION`

**From `SUPABASE_SETUP.md`:**
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `TRACE_ADMIN_API_KEY`

### 14.3 Security Findings

**SECURITY FINDING 1 — Application credential requirements unknown:**
No application environment variables or Secret Manager integration were found on the inspected Cloud Run service. Whether the application requires external credentials is UNKNOWN. If credentials are required, their storage location is undocumented and not visible from the service configuration. This requires founder confirmation.

**SECURITY FINDING 2 — Budget alerts have no destination:**
The $25/month budget is configured but `allUpdatesRule: {}` means no email or Pub/Sub notification is set up. Alerts will not fire.

**SECURITY FINDING 3 — No reviewed secret rotation procedure:**
No documented secret rotation or key management procedure exists in any repository file.

**SECURITY FINDING 4 — `TRACE_ADMIN_KEY` referenced for economy gating:**
If a Supabase deployment exists, `TRACE_ADMIN_API_KEY` gates the Trace minting route. Its storage location is unverified.

---

## 15. Dataset and Asset Locations

### 15.1 Raw LiDAR Data (LAZ)

| City | Location | Count | Status |
|------|----------|-------|--------|
| Miami | `/mnt/t7/miami/data_raw/laz/` | 108 tiles (per HANDOFF.md R11) | VERIFIED readable |
| New Orleans | `/mnt/t7/new_orleans/` | ~500 tiles (per CLAUDE.md) | VERIFIED directory present |
| LA (Greater) | `/mnt/t7/la/` | Partial (tiles 1836a–d staged per DATA_PROVENANCE) | VERIFIED directory present |
| NYC | `/mnt/t7/nyc/` | Unknown | VERIFIED directory present |
| Detroit | `/mnt/t7/detroit/` | Unknown | VERIFIED directory present |

**Single-machine dependency:** All canonical raw LiDAR data resides on one external drive on one machine. No cloud backup confirmed.

### 15.2 Processed Pipeline Outputs

| Path | City | Status |
|------|------|--------|
| `/mnt/t7/miami/data_processed/` | Miami | VERIFIED present |
| `/mnt/c/Users/Glytc/glitchos_local/miami/` | Miami (5-tile canary) | VERIFIED present |
| `/mnt/t7/new_orleans/data_processed/` | NOLA | INFERRED present (not directly listed) |
| `/mnt/c/Users/Glytc/atlas_output/` | Various | VERIFIED directory exists |

### 15.3 GLB Viewer Assets

| City | Count | Location |
|------|-------|----------|
| Miami (South Beach) | 4 tiles (318455, 318454, 318155, 318154) | `glytchOS` or `glytchOS-gcloud` viewer repo |
| New Orleans | 178 tiles (per CLAUDE.md) | INFERRED — in viewer repo |

**NOTE:** GLB asset locations are primarily in the `glytchOS-gcloud` repository (viewer), not in `glytchdraft`. The current Cloud Run deployment serves these assets directly from the container.

### 15.4 Canonical Schemas

| Schema | Location | Status |
|--------|----------|--------|
| `city_config.schema.json` | `schemas/city_config.schema.json` | VERIFIED present |
| `paths_local.schema.json` | `schemas/paths_local.schema.json` | VERIFIED present |
| `viewer_manifest.schema.json` | `schemas/viewer_manifest.schema.json` | VERIFIED present |
| `building_metadata.schema.json` | `schemas/building_metadata.schema.json` | VERIFIED present |
| `city_status.schema.json` | `schemas/city_status.schema.json` | VERIFIED present |
| `audit_report.schema.json` | `schemas/audit_report.schema.json` | VERIFIED present |
| `artifact_manifest.schema.json` | `schemas/artifact_manifest.schema.json` | VERIFIED present |

### 15.5 City Configuration Files

| City | Config | `production_allowed` | Notes |
|------|--------|---------------------|-------|
| New Orleans | `configs/cities/new_orleans.json` | INFERRED true | 135,655 buildings; `production_ready: true` per CLAUDE.md |
| Miami | `configs/cities/miami.json` | `false` (configs/miami.status.json) | `license_status: needs_review` |
| Boston | `configs/cities/boston.json` | UNKNOWN | Spec-only |
| Detroit | `configs/cities/detroit.json` | UNKNOWN | Spec-only |
| Portland | `configs/cities/portland.json` | UNKNOWN | Spec-only |
| Tempe | `configs/cities/tempe.json` | UNKNOWN | Spec-only |
| Toledo | `configs/cities/toledo.json` | UNKNOWN | Spec-only |

---

## 16. Deployment Map

```
glytchdraft (pipeline repo)
    → build process:   Python scripts (scripts/phases/)
    → deployment:      LOCAL ONLY — no cloud pipeline runner
    → runtime:         Local WSL machine (jaDeFireLoom1) + pdal_env conda
    → storage:         Samsung T7 Shield (E:), local SSD
    → endpoint:        None — produces assets for consumption
    → status:          ACTIVE (local execution); Miami phases 00–03 verified

glytchOS / glytchOS-gcloud (viewer repo)
    → build process:   Docker image build (Vite/React app)
    → deployment:      gcloud run deploy (manual, no CI trigger)
    → runtime:         Cloud Run (glitchos-viewer-staging, us-east1)
    → storage:         Artifact Registry (viewer Docker image)
                       Cloud Build source bucket (~21.6 MB)
                       GLBs served from inside container (no external CDN confirmed)
    → endpoint:        https://glitchos-viewer-staging-842618617484.us-east1.run.app
    → status:          ACTIVE — deployed 2026-06-25

Vercel
    → build process:   Not configured
    → deployment:      Not deployed (0 projects in account)
    → status:          CONFIGURED (vercel.json present) — NOT DEPLOYED

Supabase
    → build process:   SQL migrations + Edge Functions
    → deployment:      UNVERIFIED — no project ID in repo, CLI absent
    → status:          DOCUMENTED — DEPLOYMENT UNCONFIRMED

Cloudflare R2
    → build process:   wrangler upload (specified in architecture)
    → deployment:      NOT DEPLOYED — wrangler absent, no config files
    → status:          SPECIFIED IN ARCHITECTURE — NOT ACTIVE
```

---

## 17. Cost and Billing Findings

### 17.1 Verified Billing Configuration

| Item | Value | Source |
|------|-------|--------|
| Billing account | Active, linked to `glitchos-staging-charles` | `gcloud billing projects describe` |
| Monthly budget cap | $25 USD | `gcloud alpha billing budgets list` |
| Budget alerts | 50%, 90%, 100% thresholds set | `gcloud alpha billing budgets list` |
| Alert delivery | **None configured** (`allUpdatesRule: {}`) | `gcloud alpha billing budgets list` |

### 17.2 Active Resources — Cost Not Queried

| Resource | Classification | Cost Notes |
|----------|---------------|------------|
| Cloud Run `glitchos-viewer-staging` | ACTIVE RESOURCE — COST UNKNOWN | The service is configured to scale to zero, avoiding idle instance charges. Related storage, logging, networking, build, registry, and request-driven charges may still occur. |
| Artifact Registry `glitchos` (~30.8 MB) | ACTIVE RESOURCE — COST UNKNOWN | Storage cost; likely minimal at this size |
| Cloud Storage `_cloudbuild` (~21.6 MB) | ACTIVE RESOURCE — COST UNKNOWN | Storage cost; likely minimal |
| Cloud Logging (`_Required`, `_Default`) | ACTIVE RESOURCE — COST UNKNOWN | Standard GCP logging included in many tiers |

### 17.3 Founder-Reported Subscriptions Requiring Confirmation

| Service | Status |
|---------|--------|
| Supabase subscription | FOUNDER-CONFIRMATION-REQUIRED — is a Supabase project active and billing? |
| Cloudflare subscription | FOUNDER-CONFIRMATION-REQUIRED — is a Cloudflare account with R2 active? |
| Vercel subscription | FOUNDER-CONFIRMATION-REQUIRED — is aetherbeing on Hobby or Pro? |
| Domain registrar (glitchos.io / glytchos.io) | FOUNDER-CONFIRMATION-REQUIRED — registered and billing? |
| IONOS hosting | FOUNDER-CONFIRMATION-REQUIRED — any IONOS services active? |
| Squarespace | FOUNDER-CONFIRMATION-REQUIRED — any Squarespace sites active? |
| Zoho | FOUNDER-CONFIRMATION-REQUIRED — any Zoho services active (email, CRM)? |

---

## 18. Security and Operational Risks

### RISK-1 — T7 Drive Warning Status (HIGH)
The Samsung T7 Shield reports `Warning` health status in Windows Disk Management. All canonical raw city datasets (Miami, NOLA, LA, NYC, Detroit) are stored exclusively on this drive. If the drive fails, all unprocessed LiDAR data is permanently lost unless backed up elsewhere. No cloud backup is in evidence.

**Action required:** Determine root cause of Warning status; establish backup strategy before the drive is used for further writes.

### RISK-2 — Single-Machine Dependency (HIGH)
All pipeline execution, all raw data, and all local processed outputs depend on a single physical machine (`jaDeFireLoom1`). No CI/CD, no cloud-based pipeline runner, no disaster recovery procedure documented.

### RISK-3 — Budget Alert Has No Delivery Destination (MEDIUM)
The $25/month GCP budget exists but `allUpdatesRule: {}` means no email or Pub/Sub channel is configured. Budget overruns will not trigger notifications.

### RISK-4 — Application Credential Requirements Unknown (MEDIUM)
No application environment variables or Secret Manager integration were found on the inspected service. Whether the application requires external credentials is UNKNOWN. If credentials are required, their storage location is undocumented and not visible from the service configuration alone.

### RISK-5 — No CI/CD — Manual-Only Deployments (MEDIUM)
No GitHub Actions or Cloud Build triggers exist. Deployment requires manual `docker build` + `gcloud run deploy`. The exact deploy commands are not documented in the repository. A new machine or new team member cannot reproduce the deployment without tribal knowledge.

### RISK-6 — Proliferating Worktrees (LOW-MEDIUM)
Eight or more `glytchdraft-*` worktrees exist simultaneously on `C:`. Without active coordination they can diverge, conflict on shared Git objects, or accumulate uncommitted work.

### RISK-7 — Scope Contradiction: Supabase Economy Docs vs. Phase 1 Boundary (MEDIUM)
`SUPABASE_SETUP.md` documents a complete Trace Economy persistence system (claims, balances, social posts). `CLAUDE.md` and `AGENTS.md` explicitly exclude economy, claims, and social features from Phase 1. Whether a Supabase deployment was created and is currently running or incurring costs is unknown.

### RISK-8 — No Documented Recovery Procedure (MEDIUM)
No runbook, disaster recovery document, or deployment procedure is present. If the T7 fails, if the GCP project is deleted, or if access to `charles.hope.design@gmail.com` is lost, recovery path is undocumented.

### RISK-9 — Stale DNS / Unconfirmed Domain (LOW-MEDIUM)
`glitchos.io` is referenced in a documentation file but its registration status, DNS configuration, and whether it resolves to anything is unknown. No other domain is confirmed active.

---

## 19. Active versus Historical Resources

### Currently Active (VERIFIED)

| Resource | Evidence |
|----------|---------|
| Cloud Run `glitchos-viewer-staging` | Deployed 2026-06-25; serving from `.run.app` URL |
| Artifact Registry `glitchos` | Image present; referenced by Cloud Run |
| GCS `glitchos-staging-charles_cloudbuild` | Bucket exists with ~21.6 MB content |
| Service accounts (3) | Listed and present/configured — recent authenticated use not directly verified |
| GCP billing | Active with $25 budget |
| `glytchdraft` repository | Active development (master + multiple codex branches) |
| `glytchOS` repository | Active development (main + multiple codex branches) |
| Samsung T7 Shield | Physically connected; Miami data readable |

### Configured but Deployment Unknown

| Resource | Evidence |
|----------|---------|
| Vercel | `vercel.json` in repo; CLI authenticated; 0 projects deployed |
| Supabase | Documented in `SUPABASE_SETUP.md`; no project ID in repo; CLI absent |
| Cloudflare R2 | Specified in architecture; no config files; wrangler absent |

### Historical / Inactive

| Resource | Evidence |
|----------|---------|
| `aetherbeing/GLYTCHDRAFT_MIAMI_SLICE` | Public GitHub repo; last updated 2026-05-04; appears to be an export artifact |
| `archive/glytchos_legacy/` | Quarantined legacy pipeline module in `glytchdraft` |
| `glytchdraft-canonical-truth` worktree | Completed documentation sprint; closed lane |
| `kaolin_docker` repository | 2025-02-04; historical ML tooling |

---

## 20. Contradictions

| ID | Contradiction | Sources |
|----|---------------|---------|
| C1 | `SUPABASE_SETUP.md` documents a Trace Economy claims system; `CLAUDE.md`/`AGENTS.md` explicitly exclude economy/claims/social from Phase 1 | `SUPABASE_SETUP.md` vs. `CLAUDE.md` §Phase Boundary |
| C2 | Spec specifies Vercel for viewer shell + Cloudflare R2 for geometry; actual deployment is Cloud Run serving geometry from the container | `docs/GLYTCHOS_SPEC.md` §7.1 vs. Cloud Run service config |
| C3 | `docs/GLYTCHOS_SPEC.md` and `docs/GLITCHOS_AGNOSTIC_PIPELINE_VIEWER_SPEC.md` are byte-identical 794-line files with different names; which is canonical is not documented | Both files in `docs/` |
| C4 | `/mnt/e` and `/mnt/t7` both exist as WSL mount paths for the same physical device; documentation uses both interchangeably | `HANDOFF.md` R10 paths vs. WSL mount table |
| C5 | Budget alerts configured but no delivery channels exist — the budget will not alert | GCP billing budget config |

---

## 21. Missing Evidence

| Item | Required For | Status |
|------|-------------|--------|
| `glitchos.io` registration and DNS records | Domain truth | MISSING — not in repo or infra |
| Supabase project ID and deployment state | Cost and service truth | MISSING — not in repo |
| Cloudflare account and R2 bucket names | Storage architecture | MISSING — not in repo |
| Cloud Run container secrets / credential storage | Security | MISSING — not documented |
| Viewer deployment commands / runbook | Reproducibility | MISSING — not in repo |
| IAM role bindings for service accounts | Security posture | NOT QUERIED (would require `get-iam-policy`) |
| IONOS / Squarespace / Zoho subscriptions | Cost truth | MISSING — no repo evidence |
| NOLA processed output path and GLB count | Pipeline truth | NOT DIRECTLY CONFIRMED |
| GlytchOS-gcloud repository contents and Dockerfile | Deployment truth | Not inspected (different repo) |
| Backup strategy for T7 data | Operational risk | MISSING |

---

## 22. Founder-Confirmation Decisions

| ID | Decision Required |
|----|------------------|
| FC-1 | Is `glitchos.io` registered and active? Who is the registrar? What does it currently resolve to? |
| FC-2 | Is a Supabase project active and incurring cost? What is the project ID? Is the Trace Economy schema deployed? |
| FC-3 | Is Cloudflare R2 still the intended GLB hosting target, or has Cloud Run become the de facto production approach? |
| FC-4 | Does the deployed Cloud Run viewer require any API keys or credentials? If so, where are they stored? |
| FC-5 | Are IONOS, Squarespace, or Zoho services currently active and billing? |
| FC-6 | Is there a billing alert destination that should be configured on the $25 GCP budget? |
| FC-7 | What is the backup strategy for the T7 datasets? Is any cloud backup in place? |
| FC-8 | Is the Vercel account on a paid tier? If Vercel is not being used, should the `vercel.json` be removed? |
| FC-9 | Should `aetherbeing/laborandcode` and `aetherbeing/haunt-place` be treated as GlitchOS infrastructure or separate projects? |
| FC-10 | What are the exact `docker build` and `gcloud run deploy` commands used to produce the current Cloud Run deployment? |

---

## 23. Ranked Cleanup Candidates

| Priority | Item | Risk Reduction |
|----------|------|---------------|
| 1 | Establish T7 backup strategy (cloud sync of LAZ archives) | Eliminates single-point data loss risk |
| 2 | Configure budget alert delivery destination (add email to `allUpdatesRule`) | Ensures billing alerts actually fire |
| 3 | Document the Cloud Run deployment procedure (Dockerfile source, build command, deploy command) | Eliminates undocumented deployment risk |
| 4 | Confirm and document Supabase status (active or inactive) | Resolves C1 contradiction and FC-2 |
| 5 | Confirm domain registrar and DNS status for `glitchos.io` | Resolves domain unknown |
| 6 | Confirm Cloudflare/Vercel status and remove inactive `vercel.json` if not needed | Reduces configuration confusion |
| 7 | Investigate and resolve T7 Warning health status | Reduces drive failure risk |
| 8 | Consolidate or cull stale `glytchdraft-*` worktrees | Reduces coordination overhead |
| 9 | Enable Secret Manager and migrate any credentials out of the container image | Improves security posture |
| 10 | Add IAM role audit for service accounts | Verifies least-privilege |

---

## 24. Safest Single Next Action

**Configure a verified notification destination for the existing $25 GCP budget.**

The budget cap and alert thresholds already exist and are correctly scoped to `glitchos-staging-charles`. Adding an email or Pub/Sub notification channel to `allUpdatesRule` requires one console action, no infrastructure changes, no code modifications, no deployments, no data movement, and no secret rotation. It eliminates the silent billing overrun risk immediately.

This audit does not perform that action. It is recorded here as the recommended first step for the founder.

The second-safest next action is a **read-only investigation** of the T7 Warning health status in Windows Disk Management to determine the root cause before the drive is used for further writes or relied upon as the sole copy of canonical dataset files.

---

*Audit complete. No infrastructure was modified. No secrets were exposed. No APIs were enabled. No configurations were changed.*
