# Kube-RBAC-Proxy Subject Access Review (SAR) Issue

## Overview

This document tracks an issue where the kube-rbac-proxy in the cluster is not properly processing ClusterRoleBinding for users in the `odh-users` group, preventing them from performing GET operations on projects via the Kubernetes API.

## Problem Statement

Users in the `odh-users` group are unable to access project information through the dashboard, despite having appropriate ClusterRoleBinding configurations. The kube-rbac-proxy appears to be rejecting or not processing the Subject Access Review (SAR) requests correctly.

## Current State Analysis

### Expected Behavior
- Users in the `odh-users` group should be able to GET projects from the Kubernetes API
- kube-rbac-proxy should process SAR requests and allow access based on ClusterRoleBinding permissions
- Dashboard should successfully retrieve and display project information for authorized users

### Observed Behavior
- Users in `odh-users` group are denied access to project information
- kube-rbac-proxy is not properly evaluating ClusterRoleBinding permissions
- SAR requests are either being rejected or not processed correctly

## Investigation Areas

**Note:** All cluster commands should use `oc` (OpenShift CLI) with the correct KUBECONFIG:
```bash
export KUBECONFIG=/home/jtanner/workspace/github/jctanner.redhat/rosa_example/rosa-cluster.kubeconfig
```

### 1. ClusterRoleBinding Configuration

**Check if ClusterRoleBinding exists and is properly configured:**

```bash
# List all ClusterRoleBindings for odh-users group
KUBECONFIG=/home/jtanner/workspace/github/jctanner.redhat/rosa_example/rosa-cluster.kubeconfig oc get clusterrolebindings -o wide | grep odh-users

# Get detailed information about odh-users ClusterRoleBinding
KUBECONFIG=/home/jtanner/workspace/github/jctanner.redhat/rosa_example/rosa-cluster.kubeconfig oc describe clusterrolebinding odh-users

# Check if the binding references the correct ClusterRole
KUBECONFIG=/home/jtanner/workspace/github/jctanner.redhat/rosa_example/rosa-cluster.kubeconfig oc get clusterrolebinding odh-users -o yaml
```

**Expected ClusterRoleBinding structure:**
```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: odh-users
subjects:
- kind: Group
  name: odh-users
  apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: view  # or appropriate role
  apiGroup: rbac.authorization.k8s.io
```

### 2. kube-rbac-proxy Configuration

**Check kube-rbac-proxy deployment and configuration:**

```bash
# Find kube-rbac-proxy pods
KUBECONFIG=/home/jtanner/workspace/github/jctanner.redhat/rosa_example/rosa-cluster.kubeconfig oc get pods -A | grep kube-rbac-proxy

# Check kube-rbac-proxy logs
KUBECONFIG=/home/jtanner/workspace/github/jctanner.redhat/rosa_example/rosa-cluster.kubeconfig oc logs -n <namespace> <kube-rbac-proxy-pod> --tail=100

# Check kube-rbac-proxy configuration
KUBECONFIG=/home/jtanner/workspace/github/jctanner.redhat/rosa_example/rosa-cluster.kubeconfig oc get deployment -n <namespace> <kube-rbac-proxy-deployment> -o yaml
```

**Key configuration parameters to verify:**
- `--authorization-kubeconfig` pointing to correct kubeconfig
- `--authorization-rbac-super-user` if needed
- `--insecure-allow-listed-groups` for odh-users group
- `--insecure-allow-listed-users` if applicable

### 3. Subject Access Review (SAR) Testing

**Test SAR directly to verify permissions:**

```bash
# Test SAR for odh-users group
KUBECONFIG=/home/jtanner/workspace/github/jctanner.redhat/rosa_example/rosa-cluster.kubeconfig oc auth can-i get projects --as-group=odh-users

# Test SAR for specific user in odh-users group
KUBECONFIG=/home/jtanner/workspace/github/jctanner.redhat/rosa_example/rosa-cluster.kubeconfig oc auth can-i get projects --as=user@example.com --as-group=odh-users

# Test SAR with verbose output
KUBECONFIG=/home/jtanner/workspace/github/jctanner.redhat/rosa_example/rosa-cluster.kubeconfig oc auth can-i get projects --as-group=odh-users -v=6
```

### 4. Dashboard Backend Authentication

**Check dashboard backend authentication flow:**

```bash
# Check dashboard backend logs
KUBECONFIG=/home/jtanner/workspace/github/jctanner.redhat/rosa_example/rosa-cluster.kubeconfig oc logs -n <namespace> <dashboard-backend-pod> --tail=100

# Look for authentication errors
KUBECONFIG=/home/jtanner/workspace/github/jctanner.redhat/rosa_example/rosa-cluster.kubeconfig oc logs -n <namespace> <dashboard-backend-pod> | grep -i "auth\|permission\|denied"
```

## Troubleshooting Steps

### Step 1: Verify ClusterRoleBinding

```bash
# Check if odh-users ClusterRoleBinding exists
KUBECONFIG=/home/jtanner/workspace/github/jctanner.redhat/rosa_example/rosa-cluster.kubeconfig oc get clusterrolebinding odh-users

# If it doesn't exist, create it
cat <<EOF | KUBECONFIG=/home/jtanner/workspace/github/jctanner.redhat/rosa_example/rosa-cluster.kubeconfig oc apply -f -
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: odh-users
subjects:
- kind: Group
  name: odh-users
  apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: view
  apiGroup: rbac.authorization.k8s.io
EOF
```

### Step 2: Test SAR Permissions

```bash
# Test if odh-users group has view permissions
KUBECONFIG=/home/jtanner/workspace/github/jctanner.redhat/rosa_example/rosa-cluster.kubeconfig oc auth can-i get projects --as-group=odh-users

# Test specific resource access
KUBECONFIG=/home/jtanner/workspace/github/jctanner.redhat/rosa_example/rosa-cluster.kubeconfig oc auth can-i get projects --as-group=odh-users --subresource=status

# Test with different verbs
KUBECONFIG=/home/jtanner/workspace/github/jctanner.redhat/rosa_example/rosa-cluster.kubeconfig oc auth can-i list projects --as-group=odh-users
KUBECONFIG=/home/jtanner/workspace/github/jctanner.redhat/rosa_example/rosa-cluster.kubeconfig oc auth can-i watch projects --as-group=odh-users
```

### Step 3: Check kube-rbac-proxy Configuration

```bash
# Get kube-rbac-proxy deployment configuration
KUBECONFIG=/home/jtanner/workspace/github/jctanner.redhat/rosa_example/rosa-cluster.kubeconfig oc get deployment -n <namespace> <kube-rbac-proxy-deployment> -o yaml

# Check if odh-users group is in allow-list
KUBECONFIG=/home/jtanner/workspace/github/jctanner.redhat/rosa_example/rosa-cluster.kubeconfig oc get deployment -n <namespace> <kube-rbac-proxy-deployment> -o jsonpath='{.spec.template.spec.containers[0].args}' | grep odh-users
```

### Step 4: Enable Debug Logging

```bash
# Update kube-rbac-proxy deployment to enable debug logging
KUBECONFIG=/home/jtanner/workspace/github/jctanner.redhat/rosa_example/rosa-cluster.kubeconfig oc patch deployment -n <namespace> <kube-rbac-proxy-deployment> -p '{"spec":{"template":{"spec":{"containers":[{"name":"kube-rbac-proxy","args":["--v=4","--logtostderr=true"]}]}}}}'

# Check logs after enabling debug
KUBECONFIG=/home/jtanner/workspace/github/jctanner.redhat/rosa_example/rosa-cluster.kubeconfig oc logs -n <namespace> <kube-rbac-proxy-pod> --tail=100 -f
```

## Common Issues and Solutions

### Issue 1: Missing ClusterRoleBinding

**Symptoms:** SAR requests fail with "no permission" errors

**Solution:** Create or update ClusterRoleBinding for odh-users group

### Issue 2: kube-rbac-proxy Not Allow-listing Group

**Symptoms:** kube-rbac-proxy logs show "user not in allow-list" errors

**Solution:** Add odh-users group to `--insecure-allow-listed-groups` parameter

### Issue 3: Incorrect ClusterRole Permissions

**Symptoms:** SAR succeeds but actual API calls fail

**Solution:** Verify ClusterRole has appropriate permissions for projects resource

### Issue 4: Authentication Token Issues

**Symptoms:** SAR fails with authentication errors

**Solution:** Check if user tokens are properly passed through kube-rbac-proxy

## Testing and Validation

### Test Case 1: Direct API Access

```bash
# Test direct API access with user token
curl -H "Authorization: Bearer <user-token>" \
  https://<cluster-api>/api/v1/projects
```

### Test Case 2: Through kube-rbac-proxy

```bash
# Test through kube-rbac-proxy endpoint
curl -H "Authorization: Bearer <user-token>" \
  https://<kube-rbac-proxy-endpoint>/api/v1/projects
```

### Test Case 3: Dashboard Integration

```bash
# Check dashboard backend logs during project access
KUBECONFIG=/home/jtanner/workspace/github/jctanner.redhat/rosa_example/rosa-cluster.kubeconfig oc logs -n <namespace> <dashboard-backend-pod> -f

# Access dashboard and attempt to view projects
# Monitor logs for authentication/authorization errors
```

## Monitoring and Logging

### Key Log Messages to Monitor

**kube-rbac-proxy logs:**
- `"user not in allow-list"`
- `"authorization failed"`
- `"subject access review failed"`
- `"permission denied"`

**Dashboard backend logs:**
- `"Error retrieving user"`
- `"Unauthorized"`
- `"Failed to retrieve username"`
- `"Error getting Oauth Info for user"`

### Log Collection Commands

```bash
# Collect kube-rbac-proxy logs
KUBECONFIG=/home/jtanner/workspace/github/jctanner.redhat/rosa_example/rosa-cluster.kubeconfig oc logs -n <namespace> <kube-rbac-proxy-pod> --since=1h > kube-rbac-proxy.log

# Collect dashboard backend logs
KUBECONFIG=/home/jtanner/workspace/github/jctanner.redhat/rosa_example/rosa-cluster.kubeconfig oc logs -n <namespace> <dashboard-backend-pod> --since=1h > dashboard-backend.log

# Collect all relevant logs
KUBECONFIG=/home/jtanner/workspace/github/jctanner.redhat/rosa_example/rosa-cluster.kubeconfig oc logs -n <namespace> -l app=dashboard --since=1h > all-dashboard.log
```

## Investigation Results

### Key Findings from Investigation

## 1. **ClusterRoleBinding Configuration** ✅ **CORRECT**
- **Found**: `odh-projects-read` ClusterRoleBinding exists and is properly configured
- **Groups**: Correctly bound to `odh-users` group
- **Permissions**: ClusterRole `odh-projects-read` has correct permissions:
  - `apiGroups: ["project.openshift.io"]`
  - `resources: ["projects"]`
  - `verbs: ["get", "list"]`

## 2. **kube-rbac-proxy Configuration** ⚠️ **POTENTIAL ISSUE**
- **Found**: kube-rbac-proxy is running with debug logging (`--v=10`)
- **Configuration**: Uses custom config file `/etc/kube-rbac-proxy/config-file.yaml`
- **Config Content**: 
  ```yaml
  authorization:
    resourceAttributes:
      namespace: ""
      apiGroup: ""
      apiVersion: v1
      resource: "projects"
      verb: "list"
  ```
- **Issue**: The config is checking for `apiVersion: v1` but projects are in `project.openshift.io/v1`

## 3. **SAR Permissions Testing** ⚠️ **LIMITED TESTING**
- **Admin SAR Test**: `oc auth can-i get projects --as-group=odh-users --as=system:serviceaccount:opendatahub:odh-dashboard` returns `yes`
- **Note**: This test was run with admin credentials, not as the affected `odh-user1` user
- **Missing**: Need to test with actual `odh-user1` user token/credentials

## 4. **Dashboard Backend Logs** ⚠️ **ISSUES FOUND**
- **404 Errors**: Multiple `404 page not found` errors for `/apis/user.openshift.io/v1/groups`
- **No Project API Calls**: No evidence of dashboard trying to call the projects API
- **Current User**: Logs show user is `kubeadmin` with groups `["cluster-admins","system:authenticated"]`

## 5. **kube-rbac-proxy Logs** 🔍 **ADMIN USER CONTEXT**
- **Authentication**: Working correctly - user is authenticated as `kubeadmin`
- **Groups**: User has groups `["cluster-admins","system:authenticated"]` 
- **SAR Results**: Shows `"allowed":true" with reason `"RBAC: allowed by ClusterRoleBinding \"rosa-admins\" of ClusterRole \"cluster-admin\" to Group \"cluster-admins\""`
- **Important**: These logs show admin user access, NOT the affected `odh-user1` user

### Root Cause Analysis

#### **Primary Issue**: Testing with Wrong User Context
The investigation was conducted using admin credentials (`kubeadmin` with `cluster-admins` group), not the affected `odh-user1` user who should be in the `odh-users` group. The admin user has cluster-admin privileges, so SAR requests succeed regardless of the `odh-users` group permissions.

#### **Secondary Issue**: kube-rbac-proxy Configuration
The kube-rbac-proxy config file has a potential API version mismatch:
- Config specifies: `apiVersion: v1`
- Projects API is: `project.openshift.io/v1`

#### **Tertiary Issue**: Need to Test with Actual Affected User
To properly diagnose the issue, we need to:
1. Test with `odh-user1` user credentials
2. Verify the user is actually in the `odh-users` group
3. Test SAR permissions as that specific user

### Next Steps for Proper Investigation

1. **Test with odh-user1 User**: Need to test with the actual affected user's credentials
2. **Verify User Group Membership**: Confirm `odh-user1` is in the `odh-users` group
3. **Test SAR as odh-user1**: Run SAR tests using `odh-user1` token/credentials
4. **Fix kube-rbac-proxy Config**: Update the config to use correct API version if needed
5. **Monitor kube-rbac-proxy Logs**: Watch logs while `odh-user1` attempts to access projects

## Resolution Status

- [ ] **Investigation Phase**
  - [ ] Verify ClusterRoleBinding exists and is correct
  - [ ] Check kube-rbac-proxy configuration
  - [ ] Test SAR permissions directly
  - [ ] Review dashboard backend authentication flow

- [ ] **Configuration Phase**
  - [ ] Fix ClusterRoleBinding if needed
  - [ ] Update kube-rbac-proxy configuration
  - [ ] Enable debug logging for troubleshooting

- [ ] **Testing Phase**
  - [ ] Test direct API access
  - [ ] Test through kube-rbac-proxy
  - [ ] Test dashboard integration
  - [ ] Verify user experience

- [ ] **Documentation Phase**
  - [ ] Document root cause
  - [ ] Document solution steps
  - [ ] Update troubleshooting guide
  - [ ] Add monitoring recommendations

## Related Documentation

- [Kube-RBAC-Proxy Image Design](./kube-rbac-proxy-image-design.md)
- [Dashboard BYOIDC Design](./dashboard-byoidc-design.md)
- [Authentication Documentation](./AUTHN.md)

## References

- [Kubernetes RBAC Documentation](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)
- [kube-rbac-proxy GitHub Repository](https://github.com/brancz/kube-rbac-proxy)
- [OpenShift RBAC Best Practices](https://docs.openshift.com/container-platform/latest/authentication/using-rbac.html)

---

**Last Updated:** $(date)
**Status:** Under Investigation
**Assigned:** TBD
