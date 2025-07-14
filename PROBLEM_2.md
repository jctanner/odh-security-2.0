# PROBLEM_2.md

## Problem Statement
HTTPRoute resource creation fails due to invalid hostname format containing unresolved variable `$(dashboard-domain)`, causing dashboard Gateway API routing to fail.

## Severity
**MEDIUM** - Blocks Gateway API dashboard routing but doesn't prevent controller operation

## Symptoms Observed
- HTTPRoute resource creation fails with validation error
- Dashboard component unable to create Gateway API routing
- Hostname contains literal `$(dashboard-domain)` instead of resolved domain value
- Controller logs show HTTPRoute validation errors

## Current State
- **Date**: 2025-01-14
- **Status**: Active Issue
- **Impact**: Dashboard Gateway API routing blocked
- **Repository**: opendatahub-operator (src/opendatahub-operator)
- **Controller**: Dashboard component controller
- **Predecessor**: PROBLEM_1.md (RBAC permissions) - RESOLVED

## Technical Details

### Expected Behavior
HTTPRoute should be created with a valid DNS hostname format like:
```yaml
spec:
  hostnames:
  - "odh-dashboard.apps.example.com"
```

### Actual Behavior
HTTPRoute is created with unresolved variable substitution:
```yaml
spec:
  hostnames:
  - "odh-dashboard.$(dashboard-domain)"
```

### Error Messages
```
{"level":"error","ts":"2025-07-14T22:57:22Z","msg":"Reconciler error","controller":"dashboard","controllerGroup":"components.platform.opendatahub.io","controllerKind":"Dashboard","Dashboard":{"name":"default-dashboard"},"namespace":"","name":"default-dashboard","reconcileID":"cfabb4cb-2b1c-4a93-a91f-3c05d31c2f6f","error":"provisioning failed: failure deploying resource ... HTTPRoute.gateway.networking.k8s.io \"odh-dashboard\" is invalid: spec.hostnames[0]: Invalid value: \"odh-dashboard.$(dashboard-domain)\": spec.hostnames[0] in body should match '^(\\*\\.)?[a-z0-9]([-a-z0-9]*[a-z0-9])?(\\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$'"}
```

## Investigation History

### Root Cause Analysis
**Variable Substitution Failure**: The `$(dashboard-domain)` variable is not being resolved to an actual domain name during HTTPRoute resource generation.

### Potential Causes
1. **Missing Domain Configuration**: No domain value configured for variable substitution
2. **Template Processing Issue**: Variable substitution not happening in the right place/time
3. **Configuration Location**: Domain configuration not in the expected location for processing
4. **Gateway API Migration**: Domain resolution logic not implemented for Gateway API mode

## Investigation Steps Needed

### 1. Find Variable Substitution Logic
```bash
# Search for dashboard-domain variable usage
grep -r "dashboard-domain" src/opendatahub-operator/
grep -r "\$(dashboard-domain)" src/opendatahub-operator/

# Look for domain configuration
grep -r "domain" src/opendatahub-operator/internal/controller/components/dashboard/
```

### 2. Check Gateway API Template
```bash
# Find HTTPRoute template files
find src/opendatahub-operator/ -name "*.yaml" -o -name "*.tmpl" | xargs grep -l "HTTPRoute"
find src/opendatahub-operator/ -name "*.yaml" -o -name "*.tmpl" | xargs grep -l "dashboard-domain"
```

### 3. Compare with OpenShift Route Implementation
```bash
# Look at how Routes handle domain resolution
grep -r "route" src/opendatahub-operator/internal/controller/components/dashboard/
```

### 4. Check Platform Detection Logic
```bash
# Look for platform-specific domain resolution
grep -r "domain" src/opendatahub-operator/internal/controller/components/dashboard/
grep -r "OpenShift" src/opendatahub-operator/internal/controller/components/dashboard/
```

## Root Cause Hypotheses

### 1. Missing Domain Configuration
- No domain value configured in DSCI or DSC configuration
- Gateway API mode requires different domain configuration than Route mode
- Domain resolution logic not implemented for Gateway API

### 2. Template Processing Issue
- HTTPRoute template processed before domain variable substitution
- Variable substitution logic only works for Route resources, not HTTPRoute
- Template engine not handling Gateway API resources correctly

### 3. Platform Detection Problem
- Domain resolution logic only implemented for OpenShift Route mode
- Gateway API mode doesn't have equivalent domain detection
- Platform-specific domain resolution missing for Gateway API

### 4. Configuration Location Issue
- Domain configuration expected in different location for Gateway API
- DSCI/DSC configuration not providing domain value for Gateway API mode
- Variable substitution looking in wrong configuration path

## Next Steps

### Immediate Actions
1. **Find Domain Configuration**: Search for where dashboard-domain should be configured
2. **Locate HTTPRoute Template**: Find the template/code generating the HTTPRoute with the variable
3. **Check Variable Substitution**: Understand how/when variables should be resolved
4. **Compare with Routes**: See how the equivalent Route resource handles domain resolution

### Investigation Priority
1. **HIGH**: Find HTTPRoute template and variable substitution logic
2. **HIGH**: Locate domain configuration mechanism
3. **MEDIUM**: Compare with OpenShift Route implementation
4. **MEDIUM**: Check platform-specific domain resolution

## Expected Solution Areas

### 1. Domain Configuration
- Add domain configuration to DSCI/DSC for Gateway API mode
- Configure platform-specific domain resolution for Gateway API
- Ensure domain value is available for variable substitution

### 2. Template Processing
- Fix variable substitution timing in HTTPRoute template processing
- Implement domain resolution for Gateway API resources
- Update template engine to handle Gateway API variables

### 3. Platform Integration
- Implement platform-aware domain detection for Gateway API
- Add OpenShift-specific domain resolution for Gateway API mode
- Update platform detection to handle Gateway API routing

## Related Issues
- PROBLEM_1.md: RBAC Permissions Issue (RESOLVED) - Prerequisite that blocked this issue
- CONTEXT.md Item #40: Gateway API Migration Implementation and RBAC Fix
- CONTEXT.md Item #39: Gateway API Migration Implementation and RBAC Fix

## Success Criteria
- HTTPRoute created with valid DNS hostname format
- Dashboard accessible via Gateway API routing
- No HTTPRoute validation errors in controller logs
- Variable substitution working correctly for Gateway API resources
- Domain resolution working for both OpenShift and other platforms

---
**Created**: 2025-01-14  
**Last Updated**: 2025-01-14  
**Status**: Active Investigation  
**Next Action**: Find HTTPRoute template and domain configuration mechanism  
**Next Review**: After domain configuration analysis completed 