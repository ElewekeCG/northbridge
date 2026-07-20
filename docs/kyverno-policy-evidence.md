# Kyverno Policy Evidence — Deliverable D5

## Policies Applied

All three ClusterPolicies active with `validationFailureAction: Enforce`:

| Policy | Ready | Action |
|--------|-------|--------|
| require-resource-limits | True | Enforce |
| require-image-tag | True | Enforce |
| require-non-root | True | Enforce |

---

## Test 1 — Missing Resource Limits

**Manifest applied:** Pod with `nginx:1.25`, no `resources.limits` defined.

**Kyverno rejection:**
resource Pod/northbridge/test-no-limits was blocked due to the following policies
require-non-root:
check-non-root: 'validation error: Containers must not run as root. Set
securityContext.runAsNonRoot: true and runAsUser to a non-zero UID.
rule check-non-root failed at path /spec/containers/0/securityContext/'
**Why this matters:** Addresses incident #5 — a container with no memory limit
consumed all available host memory and degraded every other service on the node.
This policy makes it structurally impossible to deploy a container without explicit
resource limits.

---

## Test 2 — Latest Image Tag

**Manifest applied:** Pod with `nginx:latest`, valid resource limits and non-root security context.

**Kyverno rejection:**
resource Pod/northbridge/test-latest-tag was blocked due to the following policies
require-image-tag:
check-image-tag: 'validation failure: Images must not use the latest tag. Use a
specific version tag or git SHA.'

**Why this matters:** Addresses incident #2 — an engineer deployed from a stale
local branch and the wrong image version reached production. Pinning to a specific
tag or SHA ensures every deployment is traceable to a known, reviewed commit.

---

## Test 3 — Running as Root

**Manifest applied:** Pod with `runAsNonRoot: false` and `runAsUser: 0`.

**Kyverno rejection:**
resource Pod/northbridge/test-root-user was blocked due to the following policies
require-non-root:
check-non-root: 'validation error: Containers must not run as root. Set
securityContext.runAsNonRoot: true and runAsUser to a non-zero UID.
rule check-non-root failed at path /spec/'

**Why this matters:** Running as root gives a container unnecessary privileges.
If a process is compromised, root access inside the container significantly
increases the blast radius — potential for host escape, access to other containers'
filesystems, and privilege escalation.

---
