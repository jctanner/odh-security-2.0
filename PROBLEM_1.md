# PROBLEM_1.md

## Problem Statement
Gateway controller lacks permissions to watch Gateway API and certificate resources, causing controller failures despite RBAC configuration in config/rbac/role.yaml.

## Severity
**HIGH** - Blocks Gateway API migration functionality

## Symptoms Observed
- Gateway controller unable to watch Gateway API resources
- Certificate resource watching failures
- RBAC permission denied errors in controller logs
- Clean rebuild/redeploy cycles don't resolve the issue
- config/rbac/role.yaml changes not taking effect

## Current State
- **Date**: 2025-01-14
- **Status**: Active Issue
- **Impact**: Gateway API migration blocked
- **Repository**: opendatahub-operator (src/opendatahub-operator)
- **Controller**: Gateway service controller

## Technical Details

### Expected Behavior
Gateway controller should have permissions to:
- Watch Gateway API resources (gateways.gateway.networking.k8s.io)
- Watch certificate resources (certificates.cert-manager.io)
- Create/update/delete Gateway API resources
- Monitor certificate status and lifecycle

### Actual Behavior
- Permission denied errors when controller attempts to watch resources
- Controller fails to initialize properly
- Gateway API resources not created/managed

### Error Messages
```
W0714 22:30:43.408889       1 reflector.go:569] go/pkg/mod/k8s.io/client-go@v0.32.4/tools/cache/reflector.go:251: failed to list *v1alpha1.Gateway: gateways.services.platform.opendatahub.io is forbidden: User "system:serviceaccount:opendatahub-operator-system:opendatahub-operator-controller-manager" cannot list resource "gateways" in API group "services.platform.opendatahub.io" at the cluster scope

E0714 22:30:43.498036       1 reflector.go:166] "Unhandled Error" err="go/pkg/mod/k8s.io/client-go@v0.32.4/tools/cache/reflector.go:251: Failed to watch *v1alpha1.Gateway: failed to list *v1alpha1.Gateway: gateways.services.platform.opendatahub.io is forbidden: User \"system:serviceaccount:opendatahub-operator-system:opendatahub-operator-controller-manager\" cannot list resource \"gateways\" in API group \"services.platform.opendatahub.io\" at the cluster scope"

W0714 22:30:43.499519       1 reflector.go:569] go/pkg/mod/k8s.io/client-go@v0.32.4/tools/cache/reflector.go:251: failed to list *v1.Gateway: gateways.gateway.networking.k8s.io is forbidden: User "system:serviceaccount:opendatahub-operator-system:opendatahub-operator-controller-manager" cannot list resource "gateways" in API group "gateway.networking.k8s.io" at the cluster scope

E0714 22:30:43.499649       1 reflector.go:166] "Unhandled Error" err="go/pkg/mod/k8s.io/client-go@v0.32.4/tools/cache/reflector.go:251: Failed to watch *v1.Gateway: failed to list *v1.Gateway: gateways.gateway.networking.k8s.io is forbidden: User \"system:serviceaccount:opendatahub-operator-system:opendatahub-operator-controller-manager\" cannot list resource \"gateways\" in API group \"gateway.networking.k8s.io\" at the cluster scope"

W0714 22:30:43.500419       1 reflector.go:569] go/pkg/mod/k8s.io/client-go@v0.32.4/tools/cache/reflector.go:251: failed to list *v1.Certificate: certificates.cert-manager.io is forbidden: User "system:serviceaccount:opendatahub-operator-system:opendatahub-operator-controller-manager" cannot list resource "certificates" in API group "cert-manager.io" at the cluster scope

E0714 22:30:43.597984       1 reflector.go:166] "Unhandled Error" err="go/pkg/mod/k8s.io/client-go@v0.32.4/tools/cache/reflector.go:251: Failed to watch *v1.Certificate: failed to list *v1.Certificate: certificates.cert-manager.io is forbidden: User \"system:serviceaccount:opendatahub-operator-system:opendatahub-operator-controller-manager\" cannot list resource \"certificates\" in API group \"cert-manager.io\" at the cluster scope"
```

## Investigation History

### Attempted Solutions
1. **RBAC Role Updates** (Multiple attempts)
   - Modified config/rbac/role.yaml to add Gateway API permissions
   - Added certificate resource permissions
   - Clean rebuilds performed after each change
   - No improvement observed

2. **Clean Rebuild Cycles**
   - `workflow --name cleanup --exec` 
   - `workflow --name build-push-deploy --exec`
   - Issue persists across multiple clean cycles

3. **Permission Verification**
   - [TO BE DOCUMENTED: kubectl auth can-i checks]
   - [TO BE DOCUMENTED: ClusterRole inspection]

4. **RBAC Permissions Added** (2025-01-14)
   - Added missing RBAC rules to `src/opendatahub-operator/config/rbac/role.yaml`
   - Added Gateway API permissions: `gateway.networking.k8s.io` (gateways, httproutes, referencegrants)
   - Added Custom Gateway service permissions: `services.platform.opendatahub.io` (gateways)
   - Added cert-manager permissions: `cert-manager.io` (certificates, certificaterequests, issuers, clusterissuers)
   - Added kustomize task to `tasks/deploy.yml` to apply updated RBAC: `kustomize build config/default | kubectl apply -f -`
   - Running deploy workflow to test the fix

### Current RBAC Configuration
**Location**: `src/opendatahub-operator/config/rbac/role.yaml`

**Problem**: The role.yaml file contains NO permissions for the required resources:
- ❌ `gateways.services.platform.opendatahub.io` (custom Gateway service)
- ❌ `gateways.gateway.networking.k8s.io` (standard Gateway API)
- ❌ `certificates.cert-manager.io` (cert-manager certificates)

**ClusterRole Name**: `opendatahub-operator-controller-manager-role` (applied via kustomization with namePrefix)
**ServiceAccount**: `opendatahub-operator-controller-manager` 
**Namespace**: `opendatahub-operator-system`

**Current Role Structure** (first 50 lines of 1056 total):
```yaml
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: controller-manager-role
rules:
- apiGroups:
  - '*'
  resources:
  - deployments
  - replicasets
  - services
  verbs:
  - '*'
- apiGroups:
  - '*'
  resources:
  - statefulsets
  verbs:
  - create
  - delete
  - get
  - list
  - patch
  - update
  - watch
- apiGroups:
  - admissionregistration.k8s.io
  resources:
  - mutatingwebhookconfigurations
  - validatingadmissionpolicies
  - validatingadmissionpolicybindings
  - validatingwebhookconfigurations
  verbs:
  - create
  - delete
  - get
  - list
  - patch
  - update
  - watch
# ... continues for 1056 lines total
```

## Debugging Steps Needed

### 1. Verify Current RBAC State
```bash
# Check deployed ClusterRole
kubectl get clusterrole opendatahub-operator-manager-role -o yaml

# Check ClusterRoleBinding
kubectl get clusterrolebinding opendatahub-operator-manager-rolebinding -o yaml

# Test specific permissions
kubectl auth can-i watch gateways.gateway.networking.k8s.io --as=system:serviceaccount:opendatahub-operator-system:opendatahub-operator-controller-manager
kubectl auth can-i watch certificates.cert-manager.io --as=system:serviceaccount:opendatahub-operator-system:opendatahub-operator-controller-manager
```

### 2. Examine Controller Logs
```bash
# Get controller pod logs
kubectl logs -n opendatahub-operator-system deployment/opendatahub-operator-controller-manager -c manager

# Look for RBAC-related errors
kubectl logs -n opendatahub-operator-system deployment/opendatahub-operator-controller-manager -c manager | grep -i "forbidden\|rbac\|permission"
```

### 3. Validate Build Process
```bash
# Verify role.yaml is being included in build
# Check if kustomization.yaml includes rbac resources
# Confirm Docker build context includes updated files
```

### 4. Check Resource Dependencies
- Verify Gateway API CRDs are installed
- Confirm cert-manager CRDs are present
- Check controller manager deployment configuration

## Root Cause Analysis

### **PRIMARY CAUSE IDENTIFIED** ✅
**Missing RBAC Permissions**: The `config/rbac/role.yaml` file is missing the required permissions for Gateway API and cert-manager resources.

**Required Permissions Missing**:
1. `gateways.services.platform.opendatahub.io` - Custom Gateway service resources
2. `gateways.gateway.networking.k8s.io` - Standard Gateway API resources  
3. `certificates.cert-manager.io` - cert-manager certificate resources

### **Secondary Issues**
1. **Build Process Working**: The role.yaml is being applied correctly via kustomization
2. **Deployment Configuration Working**: ClusterRole and ClusterRoleBinding are being created correctly
3. **Resource Timing**: Not a factor - permissions are the blocker
4. **API Version Compatibility**: Gateway API v1.0.0 and cert-manager appear compatible

### **Evidence**
- ServiceAccount: `system:serviceaccount:opendatahub-operator-system:opendatahub-operator-controller-manager`
- ClusterRole: `opendatahub-operator-controller-manager-role` (exists with namePrefix applied)
- ClusterRoleBinding: `opendatahub-operator-controller-manager-rolebinding` (exists and properly bound)
- **Problem**: The ClusterRole simply doesn't contain the required API group permissions

## Next Steps

### **SOLUTION REQUIRED** ⚠️
**Add missing RBAC permissions to `src/opendatahub-operator/config/rbac/role.yaml`**

### Required RBAC Rules to Add
```yaml
# Gateway API permissions
- apiGroups:
  - gateway.networking.k8s.io
  resources:
  - gateways
  - httproutes
  - referencegrants
  verbs:
  - create
  - delete
  - get
  - list
  - patch
  - update
  - watch

# Custom Gateway service permissions
- apiGroups:
  - services.platform.opendatahub.io
  resources:
  - gateways
  verbs:
  - create
  - delete
  - get
  - list
  - patch
  - update
  - watch

# cert-manager permissions
- apiGroups:
  - cert-manager.io
  resources:
  - certificates
  - certificaterequests
  - issuers
  - clusterissuers
  verbs:
  - create
  - delete
  - get
  - list
  - patch
  - update
  - watch
```

### Implementation Steps
1. **Add RBAC Rules**: ✅ DONE - Added missing permissions to `src/opendatahub-operator/config/rbac/role.yaml`
2. **Apply via Kustomize**: ✅ DONE - Added kustomize task to `tasks/deploy.yml` for faster application
3. **Run Deploy Workflow**: ✅ DONE - Applied RBAC changes via `kustomize build config/default | kubectl apply -f -`
4. **Verify Permissions**: ✅ DONE - All permissions working: `kubectl auth can-i list gateways.gateway.networking.k8s.io` and `kubectl auth can-i list certificates.cert-manager.io` both return success
5. **Test Controller**: ✅ DONE - Controller logs show no more RBAC forbidden errors, Gateway controller functioning normally

### Investigation Priority
1. **HIGH**: ✅ Root cause identified - missing RBAC permissions
2. **HIGH**: ✅ Error messages documented 
3. **MEDIUM**: Add required RBAC rules to role.yaml
4. **MEDIUM**: Test the fix with rebuild/redeploy cycle

## Related Issues
- CONTEXT.md Item #41: DSCI Null Phase Issue Resolution (resolved)
- CONTEXT.md Item #39: Gateway API Migration Implementation and RBAC Fix (partial)

## Success Criteria ✅ ACHIEVED
- ✅ Gateway controller successfully watches Gateway API resources
- ✅ Certificate resource monitoring functional  
- ✅ No RBAC permission denied errors in controller logs
- 🔄 Gateway API resources created and managed properly (separate HTTPRoute hostname issue discovered)
- ✅ Clean rebuild/redeploy cycles work as expected

## Resolution Summary
**Problem**: Gateway controller missing RBAC permissions for Gateway API and cert-manager resources
**Solution**: Added missing permissions to `src/opendatahub-operator/config/rbac/role.yaml`
**Result**: Controller logs show clean operation with no RBAC errors

**Permissions Added**:
- `gateway.networking.k8s.io` - gateways, httproutes, referencegrants
- `services.platform.opendatahub.io` - gateways  
- `cert-manager.io` - certificates, certificaterequests, issuers, clusterissuers

**Verification**: `kubectl auth can-i` commands confirm all permissions working correctly

**Next Issue**: HTTPRoute hostname validation error with `$(dashboard-domain)` variable substitution - separate from RBAC issue

---
**Created**: 2025-01-14  
**Last Updated**: 2025-01-14  
**Status**: ✅ RESOLVED - RBAC Permissions Issue Fixed  
**Resolution**: Added missing Gateway API and cert-manager permissions to role.yaml, applied via kustomize  
**Result**: Controller logs show no more RBAC forbidden errors, Gateway controller functioning normally 