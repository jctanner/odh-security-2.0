# Kube-RBAC-Proxy Image Management Design

## Overview

This document outlines the design for implementing centralized kube-rbac-proxy image management in the OpenDataHub operator, following the same pattern as oauth-proxy image overrides. The goal is to provide a consistent mechanism for overriding kube-rbac-proxy images across all components, particularly important for air-gapped environments and custom registries.

## Current State Analysis

### Current State of Image Management

**OAuth-Proxy Implementation** (established pattern to follow):
- Multiple components use oauth-proxy with `RELATED_IMAGE_OSE_OAUTH_PROXY_IMAGE`
- Each component has different parameter names in their `params.env` files
- Successfully deployed across ODH and RHOAI platforms

**Kube-RBAC-Proxy Current Usage**:
1. **Test configurations**: Reference `quay.io/brancz/kube-rbac-proxy:local`
2. **Upgrade logic**: Contains cleanup logic for model-registry kube-rbac-proxy containers
3. **No centralized image management**: Components hardcode kube-rbac-proxy images individually

**Recent Architecture Change**:
- **Dynamic Manifests**: Components now pull manifests from external repositories via `get_all_manifests.sh` script
- **Improved Modularity**: Each component's manifests are fetched from their respective repositories at build time
- **Developer Friendly**: Enables easier development with component-specific manifest overrides

**Gap to Address**:
Currently there's no unified way to override kube-rbac-proxy images across components for air-gapped deployments, unlike oauth-proxy which has established `RELATED_IMAGE_OSE_OAUTH_PROXY_IMAGE` support.

## Proposed Design

### 1. Environment Variable Standard

Following the oauth-proxy pattern, introduce a new `RELATED_IMAGE` environment variable:

```bash
RELATED_IMAGE_OSE_KUBE_RBAC_PROXY_IMAGE
```

This will be the central override point for all kube-rbac-proxy images across components.

### 2. Component Integration Pattern

Each component that uses kube-rbac-proxy will need updates in their support files to include image parameter mapping.

#### 2.1 Component Support File Updates

**Current OAuth-Proxy Component Mappings** (for reference):

```go
// dashboard_support.go (NEW!)
"oauth-proxy-image": "RELATED_IMAGE_OSE_OAUTH_PROXY_IMAGE"

// workbenches_support.go  
"oauth-proxy-image": "RELATED_IMAGE_OSE_OAUTH_PROXY_IMAGE"

// trustyai_support.go
"oauthProxyImage": "RELATED_IMAGE_OSE_OAUTH_PROXY_IMAGE"

// modelregistry_support.go
"IMAGES_OAUTH_PROXY": "RELATED_IMAGE_OSE_OAUTH_PROXY_IMAGE"

// kserve_support.go
"oauth-proxy": "RELATED_IMAGE_OSE_OAUTH_PROXY_IMAGE"

// datasciencepipelines_support.go
"IMAGES_OAUTHPROXY": "RELATED_IMAGE_OSE_OAUTH_PROXY_IMAGE"
```

**Note**: **SIX** different parameter names for the same image across components!

**Proposed kube-rbac-proxy implementation** (standardized):
```go
// All components will use consistent naming
var imageParamMap = map[string]string{
    "kube-rbac-proxy": "RELATED_IMAGE_OSE_KUBE_RBAC_PROXY_IMAGE",  // NEW
    // ... other existing images
}
```

**Additional Components** (as they adopt kube-rbac-proxy):
- ModelRegistry: `"kube-rbac-proxy": "RELATED_IMAGE_OSE_KUBE_RBAC_PROXY_IMAGE"`
- DataSciencePipelines: `"kube-rbac-proxy": "RELATED_IMAGE_OSE_KUBE_RBAC_PROXY_IMAGE"`
- KServe: `"kube-rbac-proxy": "RELATED_IMAGE_OSE_KUBE_RBAC_PROXY_IMAGE"`
- TrustyAI: `"kube-rbac-proxy": "RELATED_IMAGE_OSE_KUBE_RBAC_PROXY_IMAGE"`

### 3. params.env File Structure

#### 3.1 Standardized Key Name

All components will use the same consistent parameter name in their `params.env` files (unlike oauth-proxy's mixed naming):

**Current OAuth-Proxy Implementation** (inconsistent naming across components):
| Component | OAuth-Proxy params.env Key | Component Support File |
|-----------|----------------------------|------------------------|
| Dashboard | `oauth-proxy-image` | `dashboard_support.go` |
| Workbenches | `oauth-proxy-image` | `workbenches.go` |
| TrustyAI | `oauthProxyImage` | `trustyai_support.go` |
| ModelRegistry | `IMAGES_OAUTH_PROXY` | `modelregistry_support.go` |
| KServe | `oauth-proxy` | `kserve_support.go` |
| DataSciencePipelines | `IMAGES_OAUTHPROXY` | `datasciencepipelines_support.go` |

**Proposed Kube-RBAC-Proxy Implementation** (consistent):
| Component | params.env Key | Default Value |
|-----------|----------------|---------------|
| Dashboard | `kube-rbac-proxy` | `registry.redhat.io/openshift4/ose-kube-rbac-proxy:latest` |
| Workbenches | `kube-rbac-proxy` | `registry.redhat.io/openshift4/ose-kube-rbac-proxy:latest` |
| ModelRegistry | `kube-rbac-proxy` | `registry.redhat.io/openshift4/ose-kube-rbac-proxy:latest` |
| DataSciencePipelines | `kube-rbac-proxy` | `registry.redhat.io/openshift4/ose-kube-rbac-proxy-rhel9:latest` |
| KServe | `kube-rbac-proxy` | `registry.redhat.io/openshift4/ose-kube-rbac-proxy:latest` |
| TrustyAI | `kube-rbac-proxy` | Platform-dependent |

**Benefits of Standardized Naming** (vs oauth-proxy's 6 different names):
- **Consistency**: Same parameter name across all components eliminates confusion
- **Simplicity**: Operators only need to remember one parameter name (not 6!)
- **Maintainability**: Easier to document, troubleshoot, and manage
- **Predictability**: Following the same pattern makes the system more intuitive
- **Learning from OAuth-Proxy**: Addresses the naming inconsistency that makes oauth-proxy harder to manage

#### 3.2 Platform-Specific Defaults

Similar to oauth-proxy, defaults should vary by platform:

- **OpenDataHub (ODH)**: `quay.io/brancz/kube-rbac-proxy:latest`
- **Red Hat OpenShift AI (RHOAI)**: `registry.redhat.io/openshift4/ose-kube-rbac-proxy@sha256:...`

### 4. Implementation Plan

#### Phase 1: Core Infrastructure
1. **Update Operator Deployment Configuration**
   ```yaml
   # config/default/custom-images-patch.yaml
   env:
   - name: RELATED_IMAGE_OSE_KUBE_RBAC_PROXY_IMAGE
     value: "registry.tannerjc.net/odh-security-2.0/kube-rbac-proxy:latest"
   ```

2. **Create/Update params.env Files** (in external component repositories)
   
   **Note**: Since manifests are now dynamically fetched from component repositories, `params.env` files will need to be updated in each component's respective repository.
   
   **Example: KServe Component Repository**:
   ```bash
   # config/overlays/odh/params.env
   # Existing oauth-proxy parameter
   oauth-proxy=registry.redhat.io/openshift4/ose-oauth-proxy@sha256:bd49cfc...
   
   # NEW: Add kube-rbac-proxy parameter (when component adopts it)
   kube-rbac-proxy=quay.io/brancz/kube-rbac-proxy:latest
   
   # Other existing parameters
   kserve-controller=quay.io/opendatahub/kserve-controller:v0.15-latest
   kserve-agent=quay.io/opendatahub/kserve-agent:v0.15-latest
   ```

   **Example: DataSciencePipelines Component Repository**:
   ```bash
   # config/base/params.env
   # Existing oauth-proxy parameter  
   IMAGES_OAUTHPROXY=registry.redhat.io/openshift4/ose-oauth-proxy-rhel9:latest
   
   # NEW: Add kube-rbac-proxy parameter (when component adopts it)
   kube-rbac-proxy=registry.redhat.io/openshift4/ose-kube-rbac-proxy-rhel9:latest
   
   # Other existing parameters
   IMAGES_DSPO=quay.io/opendatahub/data-science-pipelines-operator:latest
   IMAGES_APISERVER=quay.io/opendatahub/ds-pipelines-api-server:latest
   ```

#### Phase 2: Component Updates
3. **Update Component Support Files**
   - Add kube-rbac-proxy mappings to each component's `*_support.go` file
   - Update component `Init()` methods to call `ApplyParams` with new mappings

4. **Update Component Manifests**
   - Modify component Kustomization files to use parameterized image references
   - Update deployment templates to reference params.env values

#### Phase 3: Testing & Validation
5. **Integration Testing**
   - Verify image override works across all components
   - Test platform-specific behavior (ODH vs RHOAI)
   - Validate air-gapped environment functionality

6. **Documentation Updates**
   - Update operator documentation with kube-rbac-proxy override examples
   - Add troubleshooting guides for image override issues

### 5. Usage Examples

#### 5.1 Air-Gapped Environment Override
```yaml
# Custom images patch for air-gapped cluster
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      containers:
      - name: manager
        env:
        - name: RELATED_IMAGE_OSE_KUBE_RBAC_PROXY_IMAGE
          value: "internal-registry.company.com/kube-rbac-proxy:v0.15.0"
```

#### 5.2 Component-Specific Verification
```bash
# Check if kube-rbac-proxy image was applied correctly (after manifests are fetched)
cat opt/manifests/kserve/overlays/odh/params.env | grep kube-rbac-proxy
# Expected: kube-rbac-proxy=internal-registry.company.com/kube-rbac-proxy:v0.15.0

# Verify across multiple components (after running get_all_manifests.sh)
find opt/manifests -name "params.env" -exec grep -l "kube-rbac-proxy" {} \;

# Note: Manifests are populated dynamically, so run get_all_manifests.sh first
./get_all_manifests.sh
```

### 6. Migration Strategy

#### 6.1 Backward Compatibility
- Existing hardcoded kube-rbac-proxy images will continue to work
- New params.env approach will override only when `RELATED_IMAGE_OSE_KUBE_RBAC_PROXY_IMAGE` is set
- No breaking changes to existing deployments

#### 6.2 Rollout Plan
1. **Week 1**: Implement core infrastructure and ModelRegistry component
2. **Week 2**: Add support for DataSciencePipelines and KServe
3. **Week 3**: Add support for remaining components (TrustyAI, others as they adopt kube-rbac-proxy)
4. **Week 4**: Testing and documentation

### 7. Benefits

1. **Centralized Management**: Single environment variable controls all kube-rbac-proxy images
2. **Air-Gapped Support**: Easy override for disconnected environments  
3. **Superior Consistency**: Uses standardized `kube-rbac-proxy` parameter across all components (improvement over oauth-proxy's 6 different naming patterns)
4. **Platform Awareness**: Different defaults for ODH vs RHOAI
5. **Simplified Operations**: Uniform parameter naming eliminates component-specific knowledge requirements
6. **Addresses OAuth-Proxy Pain Points**: Operators currently need to know 6 different parameter names for oauth-proxy; kube-rbac-proxy will use just 1

### 8. Implementation Checklist

- [ ] Add `RELATED_IMAGE_OSE_KUBE_RBAC_PROXY_IMAGE` to operator deployment
- [ ] Create/update params.env files for all components
- [ ] Update component support files with image mappings
- [ ] Modify component Init() methods to call ApplyParams
- [ ] Update component manifests to use parameterized images
- [ ] Add integration tests
- [ ] Update documentation
- [ ] Verify air-gapped environment functionality

### 9. Security Considerations

- **Image Verification**: Ensure digest pinning is supported for production environments
- **Registry Authentication**: Document how to configure authentication for private registries
- **CVE Management**: Provide guidance on updating kube-rbac-proxy images for security patches

## Appendix: OAuth-Proxy Naming Pattern Reference

For comparison, here are all the different ways oauth-proxy parameters are currently named across components:

### OAuth-Proxy Parameter Name Variations
1. `oauth-proxy` (kebab-case)
2. `oauth-proxy-image` (kebab-case with suffix) - *used by 2 components*
3. `IMAGES_OAUTH_PROXY` (UPPER_SNAKE_CASE with prefix)
4. `IMAGES_OAUTHPROXY` (UPPER_SNAKE_CASE, no separators)  
5. `oauthProxyImage` (camelCase with suffix)

**Total: 6 components using 5 different naming patterns**

### Kube-RBAC-Proxy Standardization
**All components will use**: `kube-rbac-proxy` (single, consistent naming)

This demonstrates how the kube-rbac-proxy implementation will be **more consistent and maintainable** than the current oauth-proxy approach.

---

This design provides a comprehensive approach for managing kube-rbac-proxy images across the OpenDataHub operator, ensuring consistency with existing patterns while providing the flexibility needed for various deployment scenarios.
