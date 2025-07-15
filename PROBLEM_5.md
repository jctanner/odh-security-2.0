# PROBLEM 5: Gateway Service Template Errors

## Initial Problem
After running "clean-build-push-deploy", there were still no gatewayclass or gateway resources being created in the cluster, despite the Gateway service being present.

## Investigation Phase
- ✅ Checked cluster state - opendatahub-operator-controller-manager was running
- ✅ Confirmed no gatewayclass or gateway API resources were found
- ✅ Found DataScienceCluster (DSC) only had dashboard and workbenches components enabled
- ✅ Discovered Auth service existed but Gateway service was missing

## First Attempted Solution
- ❌ Tried to add "services" section to DSC configuration to enable Gateway service
- ❌ Failed because DSC CRD doesn't support "services" field
- ❌ Got error: "unknown field 'spec.services'" during deployment

## Root Cause Discovery
- ✅ Services like Gateway are created automatically by DSCI controller when networking.mode is "gateway-api"
- ✅ Manually created Gateway service resource to trigger Gateway controller
- ✅ Gateway controller was working and executing actions (createGatewayClass, createCertificateResources)

## Template Issues Found
- ✅ Template action failed with: "template: pattern matches no files: 'gateway.tmpl.yaml'"
- ✅ Root cause: GatewayTemplate constant was "gateway.tmpl.yaml" but file was embedded as "resources/gateway.tmpl.yaml"

## Template Path Fix
- ✅ Changed GatewayTemplate constant from "gateway.tmpl.yaml" to "resources/gateway.tmpl.yaml"
- ✅ After rebuild/deploy, error changed to: "map has no entry for key 'Name'"

## Template Variables Issue
- ✅ New error indicated template was found but variables weren't being provided
- ✅ Discovered TemplateInfo struct only supports FS, Path, Labels, Annotations fields - no Variables field
- ❌ Attempted to add Variables field caused compilation error

## Template Content Fix
- ✅ Since variables couldn't be passed through TemplateInfo, updated template content directly
- ✅ Changed from using variables like {{ .Name }}, {{ .Namespace }}, {{ .GatewayClassName }} to hardcoded values
- ✅ Updated template to use "odh-gateway", "opendatahub", "istio", and "{{ .spec.domain }}"

## Final Status
- ✅ Final build succeeded 
- ❌ Deployment timed out waiting for DSC to be ready
- ❌ Gateway service resource still shows "False" and "Error" status
- ❌ No GatewayClass or Gateway API resources created yet
- ❌ Error logs shifted from template issues to dashboard controller ConsoleLink validation errors

## Key Technical Details
- Gateway service controller has actions: initialize, createGatewayClass, createGatewayServiceResource, createCertificateResources, and template rendering
- Template file location: `src/opendatahub-operator/internal/controller/services/gateway/resources/gateway.tmpl.yaml`
- TemplateInfo struct in types package doesn't support variables
- Gateway service resource is cluster-scoped but Gateway API resource needs to be created in opendatahub namespace
- Template system uses the Gateway service resource as context for variable substitution

## Files Modified
1. `src/opendatahub-operator/internal/controller/services/gateway/gateway_controller_actions.go`
   - Changed GatewayTemplate constant from "gateway.tmpl.yaml" to "resources/gateway.tmpl.yaml"

2. `src/opendatahub-operator/internal/controller/services/gateway/resources/gateway.tmpl.yaml`
   - Updated template to use hardcoded values instead of variables
   - Changed from {{ .Name }} to "odh-gateway"
   - Changed from {{ .Namespace }} to "opendatahub"
   - Changed from {{ .GatewayClassName }} to "istio"
   - Kept {{ .spec.domain }} for domain substitution

## Current Issue
The most recent status shows the gateway controller is still failing on template execution with "map has no entry for key 'Name'" error, even though the template was updated to only use {{ .spec.domain }}. This suggests either:
1. The template changes weren't properly built/deployed
2. There's a caching issue
3. The template context object doesn't have the expected structure

## Next Steps
1. Verify the template changes were properly built and deployed
2. Check if there are any caching issues
3. Debug the template context object structure
4. Investigate why {{ .spec.domain }} is still failing 