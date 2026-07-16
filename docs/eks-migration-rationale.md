# Incident-to-Solution Mapping — Northbridge Commerce

**Document:** `/docs/eks-migration-rationale.md`  
**Context:** Six incidents from the Compose deployment period that collectively
justify the migration to EKS. Each incident is mapped to the specific component
of the Kubernetes architecture that makes it structurally impossible to recur.

---

## Incident 1 — AWS maintenance reboot took the entire platform down for six minutes

**What happened:** AWS scheduled a host reboot. Every container on the single
EC2 instance went down simultaneously. There was no second host. The platform
was unreachable until the instance finished rebooting and Docker Compose
restarted the containers.

**What addresses it:** The two-node EKS cluster. Kubernetes schedules pods
across multiple nodes — when AWS reboots one node for maintenance, the
scheduler detects the node is unavailable and reschedules affected pods onto
the surviving node within seconds. The platform stays up. A single-node
failure is a routine operational event, not an outage. EKS also supports
node groups with `minSize: 2`, meaning the cluster will not permit itself to
operate with fewer than two nodes.

---

## Incident 2 — A deploy from a stale local branch shipped the wrong image version

**What happened:** An engineer SSH'd into the EC2 host and ran
`docker compose up --build` from a two-day-old local branch. The wrong code
reached production. Reconciling what git's `main` branch contained versus what
was actually running took over an hour.

**What addresses it:** The CI/CD pipeline (`.github/workflows/deploy.yml`).
All production deployments now flow exclusively through GitHub Actions on push
to `main`. No human SSHes in and runs a build command. Every image is tagged
with the git SHA at build time and pushed to ECR before any deployment happens.
The running image tag is always traceable to a specific commit. "What is
actually running" is answerable by checking the ECR image tag, which is
deterministically tied to a git commit hash.

---

## Incident 3 — Catalog service OOM-killed four times in twenty minutes during a flash sale

**What happened:** Traffic spiked during a flash sale. The catalog container
hit its memory limit, was killed, Compose restarted it, it hit the limit again.
This repeated four times in twenty minutes. There was no mechanism to add
capacity — only to restart the same undersized container on the same undersized
host.

**What addresses it:** Kubernetes Horizontal Pod Autoscaler (HPA) and the
two-node cluster. HPA watches CPU and memory metrics and automatically increases
the replica count when thresholds are crossed — adding more catalog pods rather
than repeatedly restarting one. Spreading replicas across two nodes means
additional capacity is immediately available without provisioning new
infrastructure. The pod `resources.requests` and `resources.limits` fields
in the Kubernetes manifests enforce per-pod limits without giving a single pod
the ability to consume the entire node.

---

## Incident 4 — Two engineers deployed simultaneously and overwrote each other's changes

**What happened:** Two engineers independently SSH'd into the same host and
ran conflicting deploys within minutes of each other. The second deploy silently
reverted part of the first engineer's fix. Neither noticed immediately.

**What addresses it:** The CI/CD pipeline with GitHub Actions as the single
deployment path. Because all deploys are triggered by merges to `main`, two
engineers cannot deploy simultaneously without first resolving their changes
through a pull request. GitHub enforces serial merges to `main` — the second
engineer's PR cannot merge until the first is in, and the pipeline deploys
them in sequence, not in parallel. There is no SSH access to production as a
deployment mechanism.

---

## Incident 5 — A container with no memory limit starved every other container on the host

**What happened:** A new engineer added a service without copying the memory
limit convention from the rest of the Compose file. Under load, that container
consumed available host memory and degraded every other container on the same
instance — a single misconfiguration with platform-wide blast radius.

**What addresses it:** Kubernetes `LimitRange` and `resources` fields in pod
specs. A `LimitRange` object in the namespace sets a default memory limit that
applies to any container that does not explicitly specify one — a missing limit
is not a silent footgun, it is filled in automatically. Additionally, because
pods are scheduled across two nodes, a runaway pod on one node does not have
access to the memory of the other node's pods. The blast radius of a
misconfiguration is bounded to one node rather than the entire platform.

---

## Incident 6 — A three-week-old hotfix was never merged back to main

**What happened:** An engineer applied a fix directly via SSH to the running
production environment. Three weeks later, someone discovered the fix had never
been committed to git. Production and source control had silently drifted apart.
No automated process existed to detect or prevent this.

**What addresses it:** The CI/CD pipeline makes SSH-based hotfixes structurally
impossible as a deployment mechanism. The only way to change what runs in
production is to merge to `main` and let the pipeline deploy. A change that
exists only on the host and not in git will be overwritten on the next deploy
when `git pull origin main` runs and `docker compose pull` fetches the ECR
images built from `main`. Production cannot drift from source control because
every deploy starts from git.

---

## Summary Table

| Incident | Root Cause | Solution Component |
|----------|-----------|-------------------|
| 1. Maintenance reboot outage | Single host, no redundancy | Two-node EKS cluster |
| 2. Stale branch deploy | Manual SSH deploys | CI/CD pipeline, SHA-tagged images |
| 3. OOM-kill loop during spike | No horizontal scaling | HPA + multi-node scheduling |
| 4. Concurrent conflicting deploys | No deploy coordination | Single pipeline path via GitHub Actions |
| 5. No memory limit, platform-wide degradation | Missing limit, shared host | LimitRange + node isolation |
| 6. Hotfix never merged to git | SSH access as deploy path | Pipeline-only deploys, git pull on deploy |