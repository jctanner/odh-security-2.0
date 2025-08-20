# PROBLEM_3.md

## Problem Statement
OpenDataHub operator controllers fail to start due to missing Custom Resource Definitions (CRDs) for Gateway API services and cert-manager resources, causing controller initialization errors.

## Severity
**HIGH** - Blocks Gateway API migration functionality and controller startup

## Symptoms Observed
- Controller startup failures with CRD-related errors
- Gateway service controller unable to initialize
- cert-manager resource watching failures
- Controllers continuously failing to start event sources

## Current State
- **Date**: 2025-01-15
- **Status**: RESOLVED
- **Impact**: Gateway API migration blocked until CRDs installed
- **Repository**: opendatahub-operator (src/opendatahub-operator)
- **Controllers**: Gateway service controller, cert-manager integration

## Technical Details

### Expected Behavior
Controllers should start successfully and watch for their respective resources:
- Gateway service controller should watch `Gateway.services.platform.opendatahub.io`
- Controllers should watch `Certificate.cert-manager.io` resources
- All controllers should initialize without CRD-related errors

### Actual Behavior
- Controller startup fails with "no matches for kind" errors
- Gateway service controller cannot initialize
- cert-manager resource watching fails
- Operator logs show continuous CRD-related errors

### Error Messages
```
{"level":"error","ts":"2025-07-15T17:26:45Z","logger":"controller-runtime.source.EventHandler","msg":"if kind is a CRD, it should be installed before calling Start","kind":"Gateway.services.platform.opendatahub.io","error":"no matches for kind \"Gateway\" in version \"services.platform.opendatahub.io/v1alpha1\""}

{"level":"error","ts":"2025-07-15T17:26:45Z","logger":"controller-runtime.source.EventHandler","msg":"if kind is a CRD, it should be installed before calling Start","kind":"Certificate.cert-manager.io","error":"no matches for kind \"Certificate\" in version \"cert-manager.io/v1\""}
```

## Investigation History

### Root Cause Analysis
**Missing CRDs**: Two sets of Custom Resource Definitions were missing from the cluster:

1. **Gateway Service CRD**: `services.platform.opendatahub.io/gateways` - Required for custom Gateway service controller
2. **cert-manager CRDs**: `cert-manager.io/certificates` - Required for certificate management integration

### Discovery Process
1. **Operator Logs Analysis**: Error messages clearly indicated missing CRDs
2. **CRD Verification**: Confirmed Gateway API v1 CRDs were present but custom Gateway service CRD was missing
3. **cert-manager Check**: Confirmed cert-manager CRDs were completely missing from cluster
4. **File System Check**: Located Gateway service CRD in operator's `config/crd/bases/` directory

### CRD Status Investigation
```bash
# Standard Gateway API CRDs (present)
kubectl get crd | grep -i gateway
gatewayclasses.gateway.networking.k8s.io
gateways.gateway.networking.k8s.io
httproutes.gateway.networking.k8s.io
referencegrants.gateway.networking.k8s.io

# Custom Gateway service CRD (missing)
kubectl get crd | grep services.platform.opendatahub.io
# No results - CRD not installed

# cert-manager CRDs (missing)
kubectl get crd | grep cert-manager.io
# No results - CRDs not installed
```

## Resolution Applied

### 1. **Install Gateway Service CRD**
```bash
kubectl apply -f src/opendatahub-operator/config/crd/bases/services.platform.opendatahub.io_gateways.yaml
```
**Result**: `customresourcedefinition.apiextensions.k8s.io/gateways.services.platform.opendatahub.io created`

### 2. **Install cert-manager CRDs**
```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.14.4/cert-manager.crds.yaml
```
**Result**: All cert-manager CRDs installed successfully:
- `certificaterequests.cert-manager.io`
- `certificates.cert-manager.io`
- `challenges.acme.cert-manager.io`
- `clusterissuers.cert-manager.io`
- `issuers.cert-manager.io`
- `orders.acme.cert-manager.io`

### 3. **Restart Operator**
```bash
kubectl rollout restart -n opendatahub-operator-system deployment/opendatahub-operator-controller-manager
```
**Result**: Operator restarted successfully and picked up new CRDs

## Verification

### Controller Startup Success
Post-fix operator logs show clean controller initialization:
```
{"level":"info","ts":"2025-07-15T17:28:21Z","msg":"Starting Controller","controller":"gateway","controllerGroup":"services.platform.opendatahub.io","controllerKind":"Gateway"}
{"level":"info","ts":"2025-07-15T17:28:21Z","msg":"Starting workers","controller":"gateway","controllerGroup":"services.platform.opendatahub.io","controllerKind":"Gateway","worker count":1}
```

### Error Resolution
- ✅ Gateway service controller initializes successfully
- ✅ cert-manager resource watching functional
- ✅ No CRD-related errors in operator logs
- ✅ All controllers start workers successfully

## Deployment Integration

### Added to deploy.yml
Updated `tasks/deploy.yml` to include CRD installation as part of standard deployment:

```yaml
- name: "Install Gateway service CRD"
  live_shell:
    cmd: "kubectl apply -f config/crd/bases/services.platform.opendatahub.io_gateways.yaml"
    chdir: "{{ local_checkouts_dir }}/opendatahub-operator"
  register: install_gateway_crd_result

- name: "Install cert-manager CRDs"
  live_shell:
    cmd: "kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.14.4/cert-manager.crds.yaml"
  register: install_certmanager_crds_result
```

### Deployment Sequence
1. **Install standard CRDs** (`make install`)
2. **Install Gateway service CRD** (custom Gateway service)
3. **Install cert-manager CRDs** (certificate management)
4. **Deploy operator** (`make deploy`)
5. **Wait for operator ready**

## Root Cause Analysis

### Why CRDs Were Missing

1. **Gateway Service CRD**: Not included in standard `make install` target
   - CRD exists in `config/crd/bases/` but not applied by default
   - Custom service CRD separate from component CRDs

2. **cert-manager CRDs**: External dependency not automatically installed
   - Required for certificate management integration
   - Must be installed separately from cert-manager project

### Build Process Gap
The `make install` target only installs component CRDs, not service CRDs or external dependencies.

## Prevention Measures

### 1. **Automated CRD Installation**
All required CRDs now included in deployment workflow

### 2. **Deployment Verification**
Deploy workflow includes CRD installation verification

### 3. **Documentation Update**
CRD requirements documented in deployment process

## Success Criteria ✅ ACHIEVED

- ✅ Gateway service controller starts successfully
- ✅ cert-manager resource watching functional
- ✅ No CRD-related errors in operator logs
- ✅ All controllers initialize workers successfully
- ✅ CRD installation automated in deployment workflow
- ✅ Clean operator startup without errors

## Related Issues
- PROBLEM_1.md: RBAC Permissions Issue (RESOLVED) - Prerequisite for this issue
- PROBLEM_2.md: HTTPRoute Domain Resolution Issue (PENDING) - Next issue to address
- CONTEXT.md Item #42: Gateway Controller RBAC Permissions Resolution (RESOLVED)

## Next Steps
With CRDs and RBAC resolved, the operator is ready to test:
1. **Dashboard HTTPRoute creation** (PROBLEM_2.md)
2. **Gateway API resource management**
3. **Certificate integration functionality**

---
**Created**: 2025-01-15  
**Last Updated**: 2025-01-15  
**Status**: ✅ RESOLVED - Missing CRDs Installed  
**Resolution**: Installed Gateway service CRD and cert-manager CRDs, updated deployment workflow to include CRD installation  
**Result**: All controllers starting successfully, no CRD-related errors in operator logs  
**Deployment**: Automated CRD installation added to tasks/deploy.yml 