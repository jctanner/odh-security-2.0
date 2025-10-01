# Kube-Auth-Proxy Image Management Design

## Overview

This document outlines the architectural design for implementing centralized `kube-auth-proxy` (OAuth2 proxy) image management in the OpenDataHub operator gateway service. The kube-auth-proxy is used for authentication in front of the data science gateway and currently has a hardcoded image reference.

**Key Requirement**: The solution must support **automatic image updates via Mintmaker/Renovate**.

## Current State Analysis

### Current Implementation

The kube-auth-proxy image is currently **hardcoded** in `internal/controller/services/gateway/gateway_support.go`:

```go
const (
    // ... other constants
    KubeAuthProxyImage = "quay.io/jtanner/kube-auth-proxy@sha256:434580fd42d73727d62566ff6d8336219a31b322798b48096ed167daaec42f07"
    // ... other constants
)
```

This image is used in `gateway_auth_actions.go` when creating the kube-auth-proxy deployment:

```go
func createKubeAuthProxyDeployment(rr *odhtypes.ReconciliationRequest, oidcConfig *serviceApi.OIDCConfig, domain string) error {
    deployment := &appsv1.Deployment{
        // ...
        Spec: appsv1.DeploymentSpec{
            // ...
            Template: corev1.PodTemplateSpec{
                Spec: corev1.PodSpec{
                    Containers: []corev1.Container{
                        {
                            Name:  KubeAuthProxyName,
                            Image: KubeAuthProxyImage,  // <-- HARDCODED
                            // ...
                        },
                    },
                },
            },
        },
    }
    return rr.AddResources(deployment)
}
```

### Problem Statement

**Key Issues:**
1. **No Image Override Capability**: The hardcoded image cannot be overridden for air-gapped environments
2. **No Automated Updates**: Renovate/Mintmaker cannot update hardcoded string constants
3. **Inconsistent with Component Pattern**: Components use `RELATED_IMAGE_*` environment variables; services don't
4. **Development Friction**: Every image change requires code modification and rebuild
5. **Platform Inflexibility**: No way to use different images for ODH vs RHOAI platforms
6. **Security Updates**: Difficult to quickly update image for CVE remediation

### Gateway Service vs Component Differences

**Key Architectural Difference:**

Unlike components (dashboard, kserve, etc.), the gateway service:
- **Does NOT** use Kustomize with `params.env` files
- **Does NOT** fetch manifests from external repositories
- **DIRECTLY** creates Kubernetes resources programmatically in Go code
- Is part of the **services controller**, not the **components controller**

**Services Directory Structure:**
```
internal/controller/services/
├── gateway/           # Gateway service (auth proxy lives here)
├── monitoring/        # Monitoring service
├── servicemesh/       # Service mesh service
└── auth/              # Auth service
```

None of these services use the `params.env` + `ApplyParams()` pattern.

## Critical Discovery: Renovate/Mintmaker Limitations

### Analysis of Mintmaker Source Code

After examining the Mintmaker codebase at `src/mintmaker/config/manager/manager.yaml` (lines 28-34), a critical limitation was discovered:

> **Mintmaker Comment**: "We store the Renovate image reference in this annotation to leverage Kustomize's built-in 'images' transformer. Kustomize's 'images' feature works natively with image references (e.g., container images in spec.containers[].image), **but it does not support updating env variables directly**, unless we write a new transformer plugin."

### How Renovate Works

Renovate uses "managers" to detect and update dependencies. The workflow is:

1. **Platform module**: Clones the repository
2. **Manager module**: Scans files and extracts dependencies
3. **Datasource module**: Looks up available versions
4. **Versioning module**: Validates and sorts versions

**Key Managers for Our Use Case:**

#### Kubernetes Manager (`lib/modules/manager/kubernetes/`)
- Scans YAML files matching configured patterns
- Uses regex to find image references: `^\s*-?\s*image:\s*['"]?(<image-ref>)['"]?\s*`
- **Only detects** `spec.containers[].image` and `spec.initContainers[].image` fields
- **Does NOT detect** environment variable values or annotations by default

#### Kustomize Manager (`lib/modules/manager/kustomize/`)
- Looks for `kustomization.yaml` files
- Parses `images:` section with `name`, `newTag`, `newName`, `digest` fields
- **Critical Feature**: Kustomize's `images` transformer updates ALL occurrences of an image reference in the resulting manifests, including:
  - Container image fields
  - Init container image fields  
  - **Pod annotations** (!)
  - Any other field containing the exact image reference

### What Renovate/Mintmaker CAN Update Automatically

1. ✅ **Container image fields**: `spec.containers[].image`
2. ✅ **Kustomize images section**: `images[].newTag` / `images[].newName` in `kustomization.yaml`
3. ✅ **Pod annotations**: Via Kustomize's `images` transformer (when kustomization.yaml has images section)
4. ✅ **Dockerfiles**: `FROM` statements
5. ✅ **Tekton resources**: Image references in pipeline definitions

### What Renovate/Mintmaker CANNOT Update Automatically

1. ❌ **Environment variable values**: `env[].value` containing image references (Kubernetes manager doesn't detect these)
2. ❌ **Literal strings in code**: Go constants or hardcoded strings
3. ❌ **Strings in patches**: Unless using custom regex managers (complex and fragile)

### The Kustomize Images Transformer Magic

This is the **key insight** that makes our design work:

When you define images in `kustomization.yaml`:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

images:
- name: quay.io/oauth2-proxy/oauth2-proxy
  newTag: v7.7.0
```

Kustomize's `images` transformer will:
1. Find ALL occurrences of that image reference in your manifests
2. Replace them with the new tag/name
3. This includes pod annotations, not just container image fields!

**Note**: While Kustomize's images transformer can update pod annotations, our RHOAI Build Config pattern uses a simpler approach with environment variables directly from the CSV, avoiding the need for annotations and fieldRef.

### Why This Matters

If we store the default image in an environment variable's `value` field, Renovate cannot update it. This means:
- ❌ No automatic security updates
- ❌ No automatic version bumps
- ❌ Manual intervention required for every image update
- ❌ Requires custom regex managers (complex, fragile, not standard)

## Production RHOAI Pattern (Recommended Approach)

### DevOps Team Guidance

The RHOAI DevOps team has provided critical context about the **production build process**:

> "In `./src/RHOAI-Build-Config/bundle/additional-images-patch.yaml` is a gitops config that images are eventually patched as env variables in the CSV and also added to the relatedImages list to support disconnected installations. We've also configured renovate which keeps the sha-digest updated as per the configured tag."

This is the **existing, proven pattern** used by RHOAI for shared images like `ose-oauth-proxy`, `ose-etcd`, and `ose-cli`.

### How RHOAI Build Config Works

**File: `RHOAI-Build-Config/bundle/additional-images-patch.yaml`**

```yaml
# Each additional image must follow the format:
#
# name:  Must be in the format RELATED_IMAGE_[COMPONENT_NAME]_<IMAGE_NAME>_IMAGE
#        - COMPONENT_NAME (optional): Name of the component which uses the image. Omit if the image is shared by multiple components.
#        - IMAGE_NAME: A descriptive, uppercase identifier for the image (omit version details to keep it generic)
#
# value: Must follow the format registry.redhat.io/<ORG>/<REPO>:<TAG>@<SHA256_DIGEST>
#        - Use the full image reference including both tag and SHA digest
#        - This ensures updates are tied to a specific tag, avoiding unintended major or minor version bumps

additionalImages:
  - name: RELATED_IMAGE_OSE_OAUTH_PROXY_IMAGE
    value: "registry.redhat.io/openshift4/ose-oauth-proxy-rhel9:v4.18@sha256:c174c11374a52ddb7ecfa400bbd9fe0c0f46129bd27458991bec69237229ac7d"
  - name: RELATED_IMAGE_OSE_ETCD_IMAGE
    value: "registry.redhat.io/openshift4/ose-etcd-rhel9:v4.18@sha256:c9fe48e77f9923a508542509000e2d4e46e05048daaeef8e53230f4eb59ffd91"
  - name: RELATED_IMAGE_OSE_CLI_IMAGE
    value: "registry.redhat.io/openshift4/ose-cli-rhel9:v4.18@sha256:f4e17cd54c0e5dd64f428679f28e16a6018caecb72d0a43ba977b03b89778ce8"
```

**Build Process:**

1. **Image Declaration**: Images are declared in `additional-images-patch.yaml`
2. **Build Pipeline**: Referenced in `bundle/bundle-patch.yaml`:
   ```yaml
   additional-related-images:
     file: additional-images-patch.yaml
   ```
3. **CSV Patching**: The build process automatically:
   - Adds images to the CSV's `relatedImages` list (for air-gapped support)
   - Creates `RELATED_IMAGE_*` environment variables in the operator deployment
4. **Renovate Updates**: Renovate monitors this file and updates SHA digests automatically when new tags are released

**Production Validation** (from `konflux-central` repository):

The `konflux-central` repository is the **centralized Renovate configuration manager** for all RHOAI repositories. It confirms:

- **RHOAI-Build-Config** uses a **custom regex manager** specifically for `additional-images-patch.yaml`
- **Regex Pattern**: `(?<depName>[\w\.\\/\-]+):(?<currentValue>[\w]+)@(?<currentDigest>sha256:[a-f0-9]+)`
- **Purpose**: Automatically detects and updates image references in the YAML format
- **Scope**: All RHOAI shared images (ose-oauth-proxy, ose-etcd, ose-cli, etc.) use this pattern

This is **not a proposal** - it's the **existing production infrastructure**. Our kube-auth-proxy image should follow the same pattern.

### Tag Strategy: ODH vs RHOAI

**Critical Distinction:**

| Platform | Tag Strategy | Example | Update Frequency |
|----------|--------------|---------|------------------|
| **ODH** | `latest` + SHA digest | `quay.io/jtanner/kube-auth-proxy:latest@sha256:...` | Continuous, every new build |
| **RHOAI** | Version + SHA digest | `registry.redhat.io/.../kube-auth-proxy-rhel9:v1.0@sha256:...` | Controlled, per RHOAI release |

**Why This Matters:**
- **ODH**: Uses `latest` to track upstream development closely (bleeding edge)
- **RHOAI**: Uses version tags for stability and enterprise support (controlled releases)
- **Both**: Use SHA digests to ensure immutability and prevent unexpected changes

### Implementation for Kube-Auth-Proxy

**Step 1: Add to RHOAI Build Config**

File: `RHOAI-Build-Config/bundle/additional-images-patch.yaml`

```yaml
additionalImages:
  # ... existing entries ...
  
  # Add new entry for kube-auth-proxy
  # Note: RHOAI uses VERSION TAGS (e.g., v1.0, v1.1) not "latest"
  - name: RELATED_IMAGE_KUBE_AUTH_PROXY_IMAGE
    value: "registry.redhat.io/rhoai/kube-auth-proxy-rhel9:v1.0@sha256:434580fd42d73727d62566ff6d8336219a31b322798b48096ed167daaec42f07"
```

**Step 2: Update Operator Code**

File: `opendatahub-operator/internal/controller/services/gateway/gateway_support.go`

```go
// Remove hardcoded constant:
// const KubeAuthProxyImage = "quay.io/jtanner/kube-auth-proxy@sha256:..."

// Add function to read from environment variable
func getKubeAuthProxyImage() string {
    if image := os.Getenv("RELATED_IMAGE_KUBE_AUTH_PROXY_IMAGE"); image != "" {
        return image
    }
    // Fallback for local development only
    // In production RHOAI, the env var will always be set via CSV
    return "quay.io/jtanner/kube-auth-proxy:latest"
}
```

File: `opendatahub-operator/internal/controller/services/gateway/gateway_auth_actions.go`

```go
func createKubeAuthProxyDeployment(rr *odhtypes.ReconciliationRequest, oidcConfig *serviceApi.OIDCConfig, domain string) error {
    deployment := &appsv1.Deployment{
        // ...
        Spec: appsv1.DeploymentSpec{
            Template: corev1.PodTemplateSpec{
                Spec: corev1.PodSpec{
                    Containers: []corev1.Container{
                        {
                            Name:  KubeAuthProxyName,
                            Image: getKubeAuthProxyImage(),  // <-- Use function instead of constant
                            // ...
                        },
                    },
                },
            },
        },
    }
    return rr.AddResources(deployment)
}
```

**Step 3: ODH (Non-RHOAI) Default**

For OpenDataHub deployments (not RHOAI), add default to `config/manager/manager.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: controller-manager
  namespace: system
spec:
  template:
    spec:
      containers:
      - name: manager
        env:
        # ... existing env vars ...
        # Note: ODH uses "latest" tag to track upstream development
        # Renovate will update the SHA digest when new builds are pushed
        - name: RELATED_IMAGE_KUBE_AUTH_PROXY_IMAGE
          value: "quay.io/jtanner/kube-auth-proxy:latest@sha256:434580fd42d73727d62566ff6d8336219a31b322798b48096ed167daaec42f07"
```

**Important**: ODH intentionally uses the `latest` tag to stay current with upstream development. RHOAI uses versioned tags for enterprise stability.

### Benefits of RHOAI Pattern

| Benefit | Description |
|---------|-------------|
| **✅ Automated Updates** | Renovate automatically updates SHA digests in `additional-images-patch.yaml` |
| **✅ Air-Gapped Support** | Images automatically added to CSV's `relatedImages` list |
| **✅ Platform Flexibility** | RHOAI uses `registry.redhat.io`, ODH can use `quay.io` |
| **✅ Consistent Pattern** | Same pattern as other shared images (`ose-oauth-proxy`, `ose-etcd`, `ose-cli`) |
| **✅ DevOps Approved** | Explicitly recommended by RHOAI build team |
| **✅ Simple Code** | Just read an environment variable - no annotations, no fieldRef |
| **✅ Proven in Production** | Already used for multiple images in RHOAI |
| **✅ No Kustomize Changes** | Build process handles everything automatically |

### Comparison: Components vs Gateway Service

While components use `params.env` + `odhdeploy.ApplyParams()`, the gateway service doesn't use Kustomize manifests. The RHOAI Build Config pattern bridges this gap:

| Approach | How It Works |
|----------|--------------|
| **Components** | `params.env` → Kustomize → Component Manifests → Kubernetes |
| **Gateway Service** | `additional-images-patch.yaml` → CSV env vars → Go code reads env → Creates K8s resources |

Both ultimately read from `RELATED_IMAGE_*` environment variables, but through different paths.


## Implementation Plan

### RHOAI Build Config Pattern

#### Phase 1: RHOAI Build Config (Week 1)

1. **Add to RHOAI Build Config**
   - File: `RHOAI-Build-Config/bundle/additional-images-patch.yaml`
   - Add `RELATED_IMAGE_KUBE_AUTH_PROXY_IMAGE` entry
   - Follow existing naming convention and format
   - Submit PR to RHOAI-Build-Config repository

2. **Update Operator Code**
   - File: `opendatahub-operator/internal/controller/services/gateway/gateway_support.go`
   - Remove hardcoded `KubeAuthProxyImage` constant
   - Add `getKubeAuthProxyImage()` function reading `RELATED_IMAGE_KUBE_AUTH_PROXY_IMAGE` env var
   - Add fallback for local development

3. **Update Gateway Auth Actions**
   - File: `opendatahub-operator/internal/controller/services/gateway/gateway_auth_actions.go`
   - Replace `KubeAuthProxyImage` constant usage with `getKubeAuthProxyImage()` call
   - Add logging for image source (env var vs fallback)

#### Phase 2: ODH Default Configuration (Week 1)

4. **Add ODH Default**
   - File: `opendatahub-operator/config/manager/manager.yaml`
   - Add `RELATED_IMAGE_KUBE_AUTH_PROXY_IMAGE` environment variable
   - Set to ODH default (quay.io image)
   - Add comment explaining RHOAI override

5. **Verify Build Pipeline Integration**
   - Ensure RHOAI CSV gets env var from build config
   - Verify relatedImages list includes kube-auth-proxy
   - Test that Renovate can update the SHA digest

#### Phase 3: Testing & Validation (Week 1-2)

6. **Unit Tests**
   - Test `getKubeAuthProxyImage()` with env var set
   - Test `getKubeAuthProxyImage()` with fallback
   - Test gateway deployment creation with dynamic image

7. **Integration Tests**
   - Deploy operator with RHOAI CSV (image from build config)
   - Deploy operator with ODH config (image from manager.yaml)
   - Verify gateway auth proxy uses correct image
   - Test image override via environment variable

8. **Renovate Validation**
   - Verify Renovate detects image in `additional-images-patch.yaml`
   - Create test PR to update SHA digest
   - Confirm automated updates work as expected

9. **Documentation**
   - Update operator documentation with new pattern
   - Document environment variable override
   - Add air-gapped deployment notes
   - Reference RHOAI Build Config for RHOAI deployments

## Usage Examples

### Example 1: RHOAI - Automatic Renovate Updates

Renovate will automatically create PRs updating `additional-images-patch.yaml`:

```yaml
# Before (in RHOAI-Build-Config/bundle/additional-images-patch.yaml):
additionalImages:
  - name: RELATED_IMAGE_KUBE_AUTH_PROXY_IMAGE
    value: "registry.redhat.io/rhoai/kube-auth-proxy-rhel9:v1.0@sha256:434580fd42d73727d62566ff6d8336219a31b322798b48096ed167daaec42f07"

# After Renovate PR (SHA digest update for v1.0):
additionalImages:
  - name: RELATED_IMAGE_KUBE_AUTH_PROXY_IMAGE
    value: "registry.redhat.io/rhoai/kube-auth-proxy-rhel9:v1.0@sha256:abc123...newdigest"
```

**Note**: RHOAI uses **version tags** (v1.0, v1.1, etc.). Renovate updates the SHA digest when that version gets security patches. The RHOAI build pipeline automatically patches this into the CSV.

### Example 2: ODH - Default Configuration & Renovate Updates

For OpenDataHub deployments, the image is set in `config/manager/manager.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: controller-manager
  namespace: system
spec:
  template:
    spec:
      containers:
      - name: manager
        env:
        - name: RELATED_IMAGE_KUBE_AUTH_PROXY_IMAGE
          value: "quay.io/jtanner/kube-auth-proxy:latest@sha256:434580fd..."
```

**Renovate Behavior for ODH:**

When a new build is pushed to `quay.io/jtanner/kube-auth-proxy:latest`, Renovate will create a PR:

```diff
- name: RELATED_IMAGE_KUBE_AUTH_PROXY_IMAGE
- value: "quay.io/jtanner/kube-auth-proxy:latest@sha256:434580fd..."
+ value: "quay.io/jtanner/kube-auth-proxy:latest@sha256:abc123..."
```

**Note**: ODH uses the `latest` tag intentionally to track upstream continuously. Every new build triggers a Renovate PR. RHOAI uses versioned tags for controlled releases.

### Example 3: Air-Gapped Environment Override

For air-gapped deployments, override via environment variable in the operator CSV or deployment:

```yaml
# In CSV spec.install.spec.deployments[0].spec.template.spec.containers[0].env:
- name: RELATED_IMAGE_KUBE_AUTH_PROXY_IMAGE
  value: "internal-registry.company.com/kube-auth-proxy:v1.0.0@sha256:..."
```

Or via Kustomize patch:

```yaml
# custom-env-patch.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: controller-manager
spec:
  template:
    spec:
      containers:
      - name: manager
        env:
        - name: RELATED_IMAGE_KUBE_AUTH_PROXY_IMAGE
          value: "internal-registry.company.com/kube-auth-proxy:v1.0.0"
```

### Example 4: Verification

```bash
# Check environment variable in operator pod
kubectl get pod -n opendatahub-system -l control-plane=controller-manager \
  -o jsonpath='{.items[0].spec.containers[0].env[?(@.name=="RELATED_IMAGE_KUBE_AUTH_PROXY_IMAGE")].value}'

# Check gateway deployment uses correct image
kubectl get deployment -n istio-system kube-auth-proxy \
  -o jsonpath='{.spec.template.spec.containers[0].image}'

# For RHOAI, verify CSV contains the image
kubectl get csv -n redhat-ods-operator rhods-operator.v2.25.0 \
  -o jsonpath='{.spec.relatedImages[?(@.name=="RELATED_IMAGE_KUBE_AUTH_PROXY_IMAGE")].image}'
```

### Example 5: Local Development Testing

For local development without the build pipeline:

```bash
# Export environment variable before running operator
export RELATED_IMAGE_KUBE_AUTH_PROXY_IMAGE="quay.io/jtanner/kube-auth-proxy:dev"

# Or set in your IDE run configuration
```

## Benefits of RHOAI Build Config Pattern

1. ✅ **Automatic Updates**: Renovate updates SHA digests in `additional-images-patch.yaml`
2. ✅ **Air-Gapped Support**: Automatic inclusion in CSV's relatedImages list
3. ✅ **Platform Flexibility**: RHOAI uses registry.redhat.io, ODH uses quay.io
4. ✅ **Security**: Automated CVE remediation via Renovate
5. ✅ **Consistency**: Same pattern as ose-oauth-proxy, ose-etcd, ose-cli
6. ✅ **Simplicity**: Just read an environment variable - no annotations or fieldRef
7. ✅ **Production Proven**: Already used by multiple RHOAI shared images
8. ✅ **DevOps Approved**: Explicitly recommended by RHOAI build team
9. ✅ **No Build Changes**: RHOAI build pipeline handles everything automatically
10. ✅ **Backward Compatible**: Fallback in code for local development

## Renovate Configuration

### RHOAI Build Config Repository

The Renovate configuration for `RHOAI-Build-Config` repository is managed centrally via the **konflux-central** repository. 

**Source**: `konflux-central/config.yaml` (line 30):
```yaml
- renovate-config: "renovate/custom-renovate-distribution.json"
  sync-repositories:
    - name: "red-hat-data-services/RHOAI-Build-Config"
```

**Configuration**: `konflux-central/renovate/custom-renovate.json` (lines 41-51):
```json
{
  "customManagers": [
    {
      "fileMatch": ["(^|/)additional-images-patch.yaml"],
      "customType": "regex",
      "datasourceTemplate": "docker",
      "matchStrings": [
        "(?<depName>[\\w\\.\\/\\-]+):(?<currentValue>[\\w]+)@(?<currentDigest>sha256:[a-f0-9]+)"
      ],
      "versioningTemplate": "docker"
    }
  ]
}
```

**How It Works:**

1. **Custom Regex Manager**: Renovate uses a custom regex to parse `additional-images-patch.yaml`
2. **Pattern Match**: Matches format `registry/org/repo:tag@sha256:digest`
3. **Automatic Updates**: When new digest for the tag is available, Renovate creates PR
4. **Central Management**: All RHOAI repos get Renovate config synced from konflux-central

**Example PR from Renovate (RHOAI uses version tags):**
```diff
# bundle/additional-images-patch.yaml
additionalImages:
  - name: RELATED_IMAGE_KUBE_AUTH_PROXY_IMAGE
-   value: "registry.redhat.io/rhoai/kube-auth-proxy-rhel9:v1.0@sha256:old...digest"
+   value: "registry.redhat.io/rhoai/kube-auth-proxy-rhel9:v1.0@sha256:new...digest"
```

**RHOAI Tag Behavior**: Renovate monitors the `v1.0` tag. When a security patch is published to v1.0, Renovate updates the SHA digest. Major/minor version changes (v1.0 → v1.1) require manual configuration updates.

### ODH Repository Configuration

**Production Pattern** (from `konflux-central` repository):

Most ODH component repositories use the `default-renovate.json` configuration from konflux-central, which enables:
- **Dockerfile manager**: Updates base images in Dockerfiles with digest pinning
- **Tekton manager**: Updates Konflux pipeline references
- **RPM manager**: Updates RPM package versions

**For opendatahub-operator**: Since the image reference is in an environment variable in `config/manager/manager.yaml`, we need a custom regex manager similar to RHOAI's approach.

Add to `.github/renovate.json`:

```json
{
  "extends": ["config:recommended"],
  "kubernetes": {
    "fileMatch": ["^config/.*\\.yaml$"]
  },
  "packageRules": [
    {
      "matchDatasources": ["docker"],
      "matchPackageNames": ["quay.io/jtanner/kube-auth-proxy"],
      "groupName": "kube-auth-proxy",
      "schedule": ["before 4am on Monday"]
    }
  ],
  "regexManagers": [
    {
      "fileMatch": ["^config/manager/manager\\.yaml$"],
      "matchStrings": [
        "name: RELATED_IMAGE_KUBE_AUTH_PROXY_IMAGE\\s+value:\\s*[\"']?(?<depName>.*?):(?<currentValue>.*?)@(?<currentDigest>sha256:[a-f0-9]+)[\"']?"
      ],
      "datasourceTemplate": "docker",
      "versioningTemplate": "docker"
    }
  ]
}
```

**Configuration Explanation:**
- **kubernetes manager**: Scans YAML files in `config/` for standard image references
- **regexManagers**: Custom regex to detect image in `RELATED_IMAGE_*` environment variables
- **packageRules**: Groups updates and schedules them for Monday mornings

**ODH Tag Behavior**: ODH intentionally uses the `latest` tag. Renovate will create a PR **every time** a new build is pushed to `quay.io/jtanner/kube-auth-proxy:latest`. This keeps ODH at the bleeding edge of upstream development.

**Key Difference:**
- **RHOAI** (`v1.0` tag): Renovate only updates when v1.0 gets security patches → Stable, controlled
- **ODH** (`latest` tag): Renovate updates on every new build → Fast-moving, continuous

### Testing Renovate Locally

For RHOAI Build Config repository:

```bash
# Install Renovate CLI
npm install -g renovate

# Test RHOAI-Build-Config repository
LOG_LEVEL=debug renovate \
  --dry-run=full \
  --token=$GITHUB_TOKEN \
  rhoai/RHOAI-Build-Config

# Look for:
# - Detection of additional-images-patch.yaml
# - Image extraction from value: field
# - Proposed SHA digest updates
```

For ODH repository:

```bash
# Test opendatahub-operator repository
LOG_LEVEL=debug renovate \
  --dry-run=full \
  --token=$GITHUB_TOKEN \
  opendatahub-io/opendatahub-operator

# Look for:
# - Detection of config/manager/manager.yaml
# - Regex match for RELATED_IMAGE_KUBE_AUTH_PROXY_IMAGE
# - Proposed version/digest updates
```

**Verification Checklist:**
- [ ] RHOAI: Renovate detects `bundle/additional-images-patch.yaml`
- [ ] RHOAI: Renovate proposes SHA digest updates
- [ ] RHOAI: Build pipeline patches image into CSV
- [ ] ODH: Renovate detects `config/manager/manager.yaml`
- [ ] ODH: Renovate updates env var value
- [ ] Both: Operator pod gets correct image in `RELATED_IMAGE_KUBE_AUTH_PROXY_IMAGE` env var

## Comparison: Different Approaches

| Aspect | Components | Gateway (RHOAI Pattern) | Mintmaker (Reference) |
|--------|-----------|------------------------|----------------------|
| **Image Storage** | params.env | RHOAI Build Config YAML | Pod annotation |
| **Renovate Updates** | ❌ No | ✅ Yes (custom regex) | ✅ Yes (Kustomize transformer) |
| **Read Mechanism** | ApplyParams() | CSV env var → Go code | fieldRef → env → Go code |
| **Architecture** | Kustomize + external manifests | Programmatic resources | Controller pattern |
| **Override Method** | RELATED_IMAGE_* env | RELATED_IMAGE_* env | RELATED_IMAGE_* env |
| **Air-Gapped** | ✅ Via params.env | ✅ Via CSV relatedImages | ⚠️ Manual CSV update |
| **Complexity** | Medium (Kustomize required) | Low (just env var) | Medium (annotations + fieldRef) |
| **Production Use** | All ODH components | **RHOAI shared images** | Mintmaker/Konflux only |

**Decision**: RHOAI Build Config pattern — it's the existing production infrastructure for shared images

## Migration Strategy

### Backward Compatibility

- ✅ Code has fallback for missing environment variable
- ✅ No breaking changes to existing deployments
- ✅ Gradual rollout possible

### Rollout Plan

1. **Week 1**: Implement annotation + fieldRef pattern, merge PR
2. **Week 2**: Create platform overlays, update build system
3. **Week 3**: Configure Renovate, test automatic updates
4. **Week 4**: Monitor production deployments, document lessons learned

## Security Considerations

1. **Image Verification**: Pod annotations support digest-based references (`@sha256:...`)
2. **Registry Authentication**: Works with standard imagePullSecrets
3. **CVE Management**: Automated via Renovate vulnerability alerts
4. **Audit Trail**: Git history shows all image changes

## Alternative Approaches (Considered and Rejected)

### Alternative 1: Environment Variable with Value (REJECTED)

```yaml
env:
- name: RELATED_IMAGE_KUBE_AUTH_PROXY_IMAGE
  value: "quay.io/oauth2-proxy/oauth2-proxy:v7.6.0"
```

**Why Rejected**: Renovate cannot update environment variable values automatically. Requires custom regex managers (complex and fragile).

### Alternative 2: Hardcoded in Code (REJECTED)

```go
const DefaultImage = "quay.io/oauth2-proxy/oauth2-proxy:v7.6.0"
```

**Why Rejected**: No automated updates possible. Requires code changes for every image update.

### Alternative 3: ConfigMap (REJECTED)

**Why Rejected**: More complex than annotation, still requires custom Renovate configuration.

## Industry Examples and Patterns

Different projects use different patterns for managing operator images with Renovate:

### Mintmaker (Konflux/Red Hat)
- **Location**: `src/mintmaker/config/manager/manager.yaml`
- **Pattern**: Pod annotation + fieldRef (stores image in annotation, reads via fieldRef)
- **Why**: Explicitly documented: "Kustomize's 'images' feature... does not support updating env variables directly"

### RHOAI Build Config (Red Hat)
- **Location**: `src/RHOAI-Build-Config/bundle/additional-images-patch.yaml`
- **Pattern**: Custom regex manager for YAML image declarations → CSV env vars
- **Why**: Centralized image management for all RHOAI components, automatic CSV generation
- **Our Approach**: This is the pattern we're following for kube-auth-proxy

### Tekton/Argo CD/Flux CD (CNCF)
- **Pattern**: Kustomize images transformer for component images
- **Benefit**: Centralized image management, automatic Renovate updates

**Our Decision**: We use the RHOAI Build Config pattern because it's the **existing production infrastructure** for RHOAI shared images (ose-oauth-proxy, ose-etcd, ose-cli). No need to invent a new pattern when one already exists and works.

## Technical Validation from Renovate Source Code

### Kubernetes Manager Implementation

From `lib/modules/manager/kubernetes/extract.ts` (lines 44-46):

```typescript
const k8sImageRegex = regEx(
  `^\\s*-?\\s*image:\\s*['"]?(${dockerImageRegexPattern})['"]?\\s*`,
);
```

**Analysis**: 
- Regex specifically looks for `image:` field followed by an image reference
- Does NOT match `value:` fields (environment variables)
- Does NOT match arbitrary YAML fields containing images

### Kustomize Manager Implementation

From `lib/modules/manager/kustomize/extract.ts`:

```typescript
function extractImage(base) {
  // Extracts from images: section in kustomization.yaml
  // Returns: { name, newTag, newName, digest }
}
```

**Key Insight**: 
- Kustomize manager only processes the `images:` section of kustomization.yaml
- When Renovate updates `newTag`, Kustomize's transformer applies it everywhere
- This is why annotations get updated - Kustomize does it, not Renovate directly

### Docker Versioning Support

From `docs/usage/docker.md`:

```yaml
# Supported patterns
postgres:11                    # Simple tag
postgres:11-alpine            # Tag with suffix (compatibility)
postgres@sha256:abc...        # Digest pinning
postgres:11@sha256:abc...     # Tag + digest (recommended)
```

**Our Implementation Should Use**: `tag@digest` format for maximum security and immutability.

## References

### Production Infrastructure
- **Konflux Central Repository**: `src/konflux-central/` - Central Renovate configuration management
  - `renovate/custom-renovate.json` (lines 41-51) - Custom regex manager for `additional-images-patch.yaml`
  - `config.yaml` (line 30) - RHOAI-Build-Config Renovate configuration
  - **Key Finding**: RHOAI uses custom regex manager to update `additional-images-patch.yaml` automatically
- **RHOAI Build Config**: `src/RHOAI-Build-Config/bundle/additional-images-patch.yaml` - Production image declarations

### Documentation
- **Mintmaker Pattern**: `src/mintmaker/config/manager/manager.yaml` (lines 28-34, 76-80)
- **Renovate Docker Manager**: `src/renovate/docs/usage/docker.md`
- **Renovate Kubernetes Manager**: `src/renovate/lib/modules/manager/kubernetes/`
- **Renovate Kustomize Manager**: `src/renovate/lib/modules/manager/kustomize/`
- **Renovate String Patterns**: `src/renovate/docs/usage/string-pattern-matching.md`
- **Renovate How It Works**: `src/renovate/docs/usage/key-concepts/how-renovate-works.md`

### External Resources
- **OAuth2 Proxy**: https://github.com/oauth2-proxy/oauth2-proxy
- **Renovate Docs**: https://docs.renovatebot.com
- **Kustomize Images Transformer**: https://kubectl.docs.kubernetes.io/references/kustomize/kustomization/images/
- **Kubernetes FieldRef**: https://kubernetes.io/docs/tasks/inject-data-application/environment-variable-expose-pod-information/

### Related Designs
- **Related**: `docs/kube-rbac-proxy-image-design.md` (different proxy for RBAC, similar challenges)
- **Analysis**: `docs/renovate-findings.md` (detailed Renovate source code analysis)

## Implementation Checklist

### RHOAI Build Config Approach (Recommended)

#### Code Changes
- [ ] Add `getKubeAuthProxyImage()` function to `gateway_support.go`
- [ ] Remove hardcoded `KubeAuthProxyImage` constant
- [ ] Update `createKubeAuthProxyDeployment()` in `gateway_auth_actions.go`
- [ ] Add unit tests for `getKubeAuthProxyImage()`
- [ ] Add integration tests for gateway deployment

#### RHOAI Configuration
- [ ] Add entry to `RHOAI-Build-Config/bundle/additional-images-patch.yaml`
- [ ] Follow naming convention: `RELATED_IMAGE_KUBE_AUTH_PROXY_IMAGE`
- [ ] Use format: `<registry>/<org>/<repo>:<tag>@<sha256>`
- [ ] Submit PR to RHOAI-Build-Config repository
- [ ] Verify build pipeline patches to CSV

#### ODH Configuration
- [ ] Add `RELATED_IMAGE_KUBE_AUTH_PROXY_IMAGE` to `config/manager/manager.yaml`
- [ ] Set ODH default value (quay.io image)
- [ ] Add comment explaining RHOAI override

#### Testing & Validation
- [ ] Test with RHOAI CSV (image from build config)
- [ ] Test with ODH config (image from manager.yaml)
- [ ] Test environment variable override
- [ ] Verify Renovate detects and updates RHOAI config
- [ ] Verify Renovate detects and updates ODH config
- [ ] Test air-gapped override scenario
- [ ] Verify CSV relatedImages list includes kube-auth-proxy

#### Documentation
- [ ] Update operator README with new pattern
- [ ] Document environment variable override
- [ ] Create air-gapped deployment guide
- [ ] Document Renovate integration
- [ ] Add troubleshooting guide

---

## Conclusion

This design is based on **devops team guidance** and extensive analysis of production RHOAI patterns, Konflux Central, and Renovate source code.

### RHOAI Build Config Pattern

Use the RHOAI Build Config pattern (`additional-images-patch.yaml`) for production deployments — this is the **existing production standard** for all RHOAI shared images.

**Key Benefits:**
1. ✅ **Production Proven**: Already used by `ose-oauth-proxy`, `ose-etcd`, `ose-cli`
2. ✅ **DevOps Approved**: Explicitly recommended by RHOAI build team
3. ✅ **Automatic Updates**: Renovate updates SHA digests automatically
4. ✅ **Air-Gapped Built-in**: Automatic CSV relatedImages list
5. ✅ **Simplest Implementation**: Just read an environment variable
6. ✅ **No Build Changes**: RHOAI pipeline handles everything

### How It Works

```
RHOAI Path (Version Tags):
additional-images-patch.yaml → Build Pipeline → CSV (env + relatedImages) → Operator Pod → Go Code
     ↑ Renovate updates v1.0                                                    ↓ Reads env var
       SHA digest only                                                   createKubeAuthProxy()
       (stable, controlled)

ODH Path (Latest Tag):
config/manager/manager.yaml → Operator Deployment → Operator Pod → Go Code
     ↑ Renovate updates latest                          ↓ Reads env var
       SHA digest continuously                   createKubeAuthProxy()
       (bleeding edge)
```

**Critical Distinction:**
- **RHOAI**: Uses versioned tags (`v1.0`, `v1.1`) → Only SHA updates within that version → Stable for production
- **ODH**: Uses `latest` tag → SHA updates on every new build → Continuous upstream tracking

### Key Technical Findings

1. **RHOAI Pattern**: Production standard for shared images in RHOAI ecosystem
2. **Renovate Capability**: Can update images in YAML files (including `additional-images-patch.yaml`)
3. **CSV Integration**: RHOAI build automatically creates relatedImages list for air-gap
4. **Platform Flexibility**: RHOAI uses registry.redhat.io, ODH uses quay.io
5. **Consistency**: Same `RELATED_IMAGE_*` pattern as components, just different source

### Implementation Priority

1. **Phase 1**: RHOAI Build Config + operator code changes (Week 1)
2. **Phase 2**: ODH default configuration (Week 1)
3. **Phase 3**: Testing and validation (Week 1-2)

### Final Recommendation

**Implement the RHOAI Build Config pattern** for production. This is the simplest, most proven approach:

- **For RHOAI Production**: 
  - Add to `RHOAI-Build-Config/bundle/additional-images-patch.yaml`
  - Use **versioned tag** (e.g., `v1.0@sha256:...`)
  - Renovate updates SHA digest when v1.0 gets patches
  - Build pipeline handles CSV patching automatically
  
- **For ODH Upstream**: 
  - Add to `opendatahub-operator/config/manager/manager.yaml`
  - Use **`latest` tag** (e.g., `latest@sha256:...`)
  - Renovate updates SHA digest on every new build
  - Tracks upstream continuously (bleeding edge)
  
- **For Both**: 
  - Operator code reads `RELATED_IMAGE_KUBE_AUTH_PROXY_IMAGE` env var
  - Same code path, different image sources
  - Platform flexibility without code changes

**Key Insights**: 
1. Use the existing production infrastructure (RHOAI Build Config) rather than inventing new patterns
2. ODH uses `latest` tag to stay current, RHOAI uses versioned tags for stability
3. Both get SHA digest pinning via Renovate for immutability
4. The devops team already solved this problem for shared images - follow the same pattern
