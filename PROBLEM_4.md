# PROBLEM_4.md

## Problem Statement

The OpenDataHub operator's Gateway controller requires cert-manager CRDs and RBAC permissions, but investigation reveals this may be inconsistent with how other ODH component operators handle cert-manager dependencies. This analysis examines cert-manager usage patterns across ODH components to identify design patterns our implementation could adopt.

## Background

During Gateway API migration, we discovered that:
1. ODH operator requires cert-manager CRDs to be pre-installed (PROBLEM_3.md)
2. ODH operator needs cert-manager RBAC permissions to watch Certificate resources (PROBLEM_1.md)
3. This suggests cert-manager is a hard dependency, but other operators may handle this differently

## Component Analysis

### **1. Kueue Operator**

**Default Deployment**: Uses `internalcert` instead of cert-manager
```yaml
# src/kueue/config/default/kustomization.yaml
resources:
- ../components/internalcert
# [CERTMANAGER] To enable cert-manager, uncomment all sections with 'CERTMANAGER'. 'WEBHOOK' components are required.
# - ../components/certmanager
```

**cert-manager Implementation**: Optional, disabled by default
- **Location**: `src/kueue/config/components/certmanager/`
- **Purpose**: Webhook TLS certificates for admission webhooks
- **Configuration**: Self-signed issuer with automatic Certificate creation
- **Resources Created**: 
  - `cert-manager.io/v1` Issuer (self-signed)
  - `cert-manager.io/v1` Certificate (for webhook service)
  - Secret: `webhook-server-cert`

**Alternative Approach**: Internal certificates
- **Location**: `src/kueue/config/components/internalcert/`
- **Implementation**: Empty Secret resource for manual certificate management
- **Default**: Used by default deployment (no cert-manager dependency)

### **2. ODH Model Controller**

**Default Deployment**: Uses webhook without cert-manager
```yaml
# src/odh-model-controller/config/default/kustomization.yaml
resources:
- ../webhook
# [CERTMANAGER] To enable cert-manager, uncomment all sections with 'CERTMANAGER'. 'WEBHOOK' components are required.
#- ../certmanager
```

**cert-manager Implementation**: Optional, disabled by default
- **Location**: `src/odh-model-controller/config/certmanager/`
- **Purpose**: Webhook TLS certificates for admission webhooks
- **Configuration**: Self-signed issuer with automatic Certificate creation
- **Resources Created**:
  - `cert-manager.io/v1` Issuer (self-signed)
  - `cert-manager.io/v1` Certificate (for webhook service)
  - Secret: `webhook-server-cert`

**Alternative Approach**: Webhook works without cert-manager
- **Default**: Webhooks enabled but cert-manager disabled
- **Certificate Management**: Handled externally or with self-signed certificates

### **3. Feast Operator**

**Analysis**: No cert-manager usage found
- **Repository**: Python-based, not Go Kubernetes operator
- **Certificate Management**: Not applicable (no admission webhooks)

## OpenDataHub Operator Implementation

### **Current Approach**: Direct cert-manager integration

**Gateway Controller**: Creates cert-manager Certificate resources directly
```go
// src/opendatahub-operator/internal/controller/services/gateway/gateway_controller_actions.go
func createCertificateResources(ctx context.Context, rr *odhtypes.ReconciliationRequest) error {
    // Only create cert-manager resources if certificate type is CertManager
    if gatewayInstance.Spec.Certificate.Type != serviceApi.CertManagerCertificate {
        return nil // Skip cert-manager
    }
    
    certificate := &certmanagerv1.Certificate{
        // Direct Certificate resource creation
    }
}
```

**Key Differences**:
1. **Resource Watching**: ODH operator watches Certificate resources (requires RBAC)
2. **Direct Creation**: Creates Certificate resources in Go code, not YAML templates
3. **Conditional Usage**: Only creates cert-manager resources when explicitly configured
4. **Hard Dependency**: Requires cert-manager CRDs even when not used

## Design Pattern Comparison

### **Component Operators Pattern**: Optional cert-manager with alternatives

**Advantages**:
- ✅ **No Hard Dependencies**: Work without cert-manager installed
- ✅ **Flexible Deployment**: Multiple certificate management options
- ✅ **Kustomize-Based**: Configuration through standard Kubernetes patterns
- ✅ **User Choice**: Users can enable cert-manager or use alternatives

**Implementation**:
```yaml
# Default: No cert-manager
resources:
- ../components/internalcert

# Optional: Enable cert-manager
# - ../components/certmanager
```

### **ODH Operator Pattern**: Direct cert-manager integration

**Advantages**:
- ✅ **Runtime Configuration**: Certificate type configured in API spec
- ✅ **Programmatic Control**: Full control over Certificate resource creation
- ✅ **Dynamic Behavior**: Can adapt certificate creation based on runtime conditions

**Disadvantages**:
- ❌ **Hard Dependency**: Requires cert-manager CRDs even when not used
- ❌ **RBAC Complexity**: Needs permissions to watch cert-manager resources
- ❌ **Startup Failures**: Controller fails if cert-manager CRDs missing

## Analysis: Why ODH Operator Needs cert-manager Watching

**Investigation**: Why does Gateway controller watch Certificate resources?

**Answer**: It doesn't need to watch them - the controller creates Certificate resources but doesn't watch them:

```go
// Gateway controller imports cert-manager APIs but only creates resources
import certmanagerv1 "github.com/cert-manager/cert-manager/pkg/apis/certmanager/v1"

// Creates Certificate resources but doesn't watch them
certificate := &certmanagerv1.Certificate{...}
rr.AddResources(certificate)
```

**Root Cause**: Controller-runtime automatically sets up watchers for any API types used in the codebase, even if not explicitly watched.

## Recommendations

### **1. Adopt Component Operator Pattern**

**Approach**: Make cert-manager optional through configuration overlays
- **Default**: Use self-signed certificates or manual certificate management
- **Optional**: Enable cert-manager through kustomize configuration
- **Benefits**: Eliminates hard cert-manager dependency

### **2. Conditional API Import**

**Approach**: Only import cert-manager APIs when needed
- **Build Tags**: Use Go build tags to conditionally include cert-manager support
- **Runtime Detection**: Check for cert-manager CRDs at runtime before creating resources
- **Benefits**: Reduces startup dependencies

### **3. External Certificate Management**

**Approach**: Support external certificate provisioning
- **Manual Certificates**: Allow users to provide TLS certificates via Secrets
- **External Issuers**: Support certificates from external CA or manual processes
- **Benefits**: Reduces cert-manager dependency

### **4. Resource Creation vs Watching**

**Approach**: Create resources without watching them
- **Fire-and-Forget**: Create Certificate resources and let cert-manager handle lifecycle
- **Status Polling**: Check certificate status through API calls rather than watching
- **Benefits**: Eliminates need for cert-manager RBAC permissions

## Implementation Strategy

### **Phase 1: Optional cert-manager (Recommended)**
```yaml
# config/gateway/base/kustomization.yaml
resources:
- gateway-service.yaml
- gateway-internal-cert.yaml  # Default: internal cert management

# config/gateway/certmanager/kustomization.yaml  
resources:
- ../base
- certificate.yaml  # Optional: cert-manager Certificate resource
```

### **Phase 2: Conditional API Usage**
```go
// +build certmanager

package gateway

import certmanagerv1 "github.com/cert-manager/cert-manager/pkg/apis/certmanager/v1"

// Only included when built with certmanager tag
func createCertManagerCertificate(...) error {
    // cert-manager Certificate creation
}
```

### **Phase 3: Runtime Detection**
```go
func createCertificateResources(ctx context.Context, rr *odhtypes.ReconciliationRequest) error {
    // Check if cert-manager CRDs are available
    if !isCertManagerAvailable(rr.Client) {
        return createInternalCertificate(ctx, rr)
    }
    
    return createCertManagerCertificate(ctx, rr)
}
```

## Gateway Certificate Management Options

**Key Insight**: The Gateway API only needs a Secret with TLS certificate data - it doesn't care how that Secret was created.

```yaml
# Gateway template only needs a Secret reference
listeners:
- name: https
  port: 443
  protocol: HTTPS
  tls:
    mode: Terminate
    certificateRefs:
    - name: odh-gateway-tls-secret  # Just needs a Secret!
      kind: Secret
```

### **Certificate Management Approaches**

**1. Default: Self-Signed Certificates (Recommended)**
- Generate self-signed certificates in Go code
- Create Secret with certificate data directly
- No external dependencies required
- Works immediately out-of-the-box

**2. Manual Certificate Management**
- Users provide their own certificates via Secrets
- Supports external certificate authorities
- Enterprise-friendly for existing PKI infrastructure

**3. Optional: cert-manager Integration**
- Runtime detection of cert-manager availability
- Fallback to self-signed if cert-manager not available
- Configuration-driven certificate type selection

### **Implementation Strategy**
```go
func createCertificateResources(ctx context.Context, rr *odhtypes.ReconciliationRequest) error {
    // Default: Self-signed certificates
    if !shouldUseCertManager(rr) || !isCertManagerAvailable(rr.Client) {
        return createSelfSignedCertificate(ctx, rr)
    }
    
    // Optional: cert-manager Certificate resource
    return createCertManagerCertificate(ctx, rr)
}
```

## Conclusion

**Key Finding**: Component operators (kueue, odh-model-controller) treat cert-manager as optional with alternatives, while our ODH operator creates a hard dependency.

**Discovery**: Gateway API only needs a Secret with TLS certificate data - cert-manager is just one way to create that Secret.

**Recommendation**: Adopt the component operator pattern of optional cert-manager with fallback to self-signed certificate management.

**Benefits**:
- ✅ Eliminates cert-manager CRD requirement (resolves PROBLEM_3.md)
- ✅ Reduces RBAC permission complexity (improves PROBLEM_1.md)
- ✅ Follows established ODH component patterns
- ✅ Maintains flexibility for users with/without cert-manager
- ✅ Works out-of-the-box with self-signed certificates
- ✅ Supports enterprise certificate management workflows

**Implementation Options**:
1. **Self-signed certificates** (default, no dependencies)
2. **Manual certificate management** (user-provided Secrets)
3. **cert-manager integration** (optional, runtime detection)

---

**Status**: 📋 ANALYSIS COMPLETE - NOT IMPLEMENTING  
**Decision**: Keeping cert-manager as hard dependency for now  
**Future Work**: Implement optional cert-manager pattern based on component operator designs  
**Related**: PROBLEM_1.md (RBAC), PROBLEM_3.md (Missing CRDs) 