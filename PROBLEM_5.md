# PROBLEM_5.md

## Problem Statement

The Gateway controller is running and watching for Gateway service resources, but no GatewayClass or Gateway (Gateway API) resources are being created. The DSCI is configured for `networking.mode: "gateway-api"` but the actual Gateway API resources required for routing are missing.

## Current State Analysis

### **DSCI Configuration**: ✅ Correct
```yaml
# kubectl get dsci -o yaml
spec:
  networking:
    mode: gateway-api  # Gateway controller should be active
status:
  phase: Ready
```

### **Gateway Controller**: ✅ Running
```log
# kubectl logs -n opendatahub-operator-system deployment/opendatahub-operator-controller-manager | grep gateway
{"level":"info","ts":"2025-07-15T18:46:42Z","logger":"setup","msg":"creating reconciler","type":"service","name":"gateway"}
{"level":"info","ts":"2025-07-15T18:46:44Z","msg":"Starting Controller","controller":"gateway","controllerGroup":"services.platform.opendatahub.io","controllerKind":"Gateway"}
{"level":"info","ts":"2025-07-15T18:46:44Z","msg":"Starting workers","controller":"gateway","controllerGroup":"services.platform.opendatahub.io","controllerKind":"Gateway","worker count":1}
```

### **CRDs**: ✅ Available
```bash
# kubectl get crd | grep gateway
gatewayclasses.gateway.networking.k8s.io                          2025-06-15T12:53:15Z
gateways.gateway.networking.k8s.io                                2025-06-15T12:53:15Z
gateways.services.platform.opendatahub.io                         2025-07-15T17:27:30Z
httproutes.gateway.networking.k8s.io                              2025-06-15T12:53:16Z
```

### **Missing Resources**: ❌ Not Created
```bash
# kubectl get gatewayclasses -A
No resources found

# kubectl get gateways -A  
No resources found

# kubectl get gateways.services.platform.opendatahub.io -A
No resources found
```

## Root Cause Analysis

### **1. No Gateway Service Resources**
The Gateway controller is waiting for Gateway service resources (`gateways.services.platform.opendatahub.io`) to be created, but none exist. This is the trigger resource that would cause the controller to create the actual Gateway API resources.

### **2. Missing GatewayClass Resource**
No GatewayClass resource exists to define the gateway implementation. For Istio, this should be:
```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: GatewayClass
metadata:
  name: istio
spec:
  controllerName: istio.io/gateway-controller
```

### **3. Gateway Template References Missing GatewayClass**
The Gateway template expects a `GatewayClassName` variable:
```yaml
# src/opendatahub-operator/internal/controller/services/gateway/resources/gateway.tmpl.yaml
spec:
  gatewayClassName: {{ .GatewayClassName }}  # No default value provided
```

### **4. Missing Action Chain**
The Gateway controller has the template but the action chain is incomplete:
```go
// src/opendatahub-operator/internal/controller/services/gateway/gateway_controller.go
WithAction(initialize).                    // ✅ Sets up template
WithAction(createCertificateResources).    // ✅ Creates cert-manager resources
WithAction(template.NewAction()).          // ✅ Processes template
WithAction(deploy.NewAction()).            // ✅ Deploys resources
// Missing: createGatewayService action (exists but not called)
```

## Expected Behavior

### **1. GatewayClass Resource**
Should automatically create an Istio GatewayClass:
```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: GatewayClass
metadata:
  name: istio
spec:
  controllerName: istio.io/gateway-controller
  description: "Istio Gateway implementation"
```

### **2. Gateway Service Resource**
Should create a Gateway service resource that triggers the controller:
```yaml
apiVersion: services.platform.opendatahub.io/v1alpha1
kind: Gateway
metadata:
  name: odh-gateway
  namespace: opendatahub
spec:
  domain: "apps.example.com"
  gatewayClassName: "istio"
  certificate:
    type: "CertManager"
```

### **3. Gateway API Resource**
Should create the actual Gateway resource from the template:
```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: odh-gateway
  namespace: opendatahub
spec:
  gatewayClassName: istio
  listeners:
  - name: https
    port: 443
    protocol: HTTPS
    hostname: "*.apps.example.com"
```

## Technical Investigation

### **Controller Action Flow**
```go
// Current actions (working):
initialize                 // Sets up gateway.tmpl.yaml
createCertificateResources // Creates cert-manager Certificate
template.NewAction()       // Processes template with variables
deploy.NewAction()         // Deploys processed resources

// Missing actions:
createGatewayClass         // Should create GatewayClass resource
createGatewayService       // Should create Gateway service resource (exists but not called)
```

### **Template Variable Requirements**
```yaml
# gateway.tmpl.yaml needs these variables:
{{ .Name }}              # Gateway name
{{ .Namespace }}         # Gateway namespace  
{{ .GatewayClassName }}  # GatewayClass name (should be "istio")
{{ .Domain }}            # Domain for hostname wildcards
```

## Solution Requirements

### **1. Create GatewayClass Resource**
Add action to create Istio GatewayClass automatically:
```go
func createGatewayClass(ctx context.Context, rr *odhtypes.ReconciliationRequest) error {
    gatewayClass := &gwapiv1.GatewayClass{
        ObjectMeta: metav1.ObjectMeta{
            Name: "istio",
        },
        Spec: gwapiv1.GatewayClassSpec{
            ControllerName: "istio.io/gateway-controller",
            Description:    ptr.To("Istio Gateway implementation"),
        },
    }
    return rr.AddResources(gatewayClass)
}
```

### **2. Create Gateway Service Resource**
Add action to create Gateway service resource that triggers the controller:
```go
func createGatewayServiceResource(ctx context.Context, rr *odhtypes.ReconciliationRequest) error {
    gateway := &serviceApi.Gateway{
        ObjectMeta: metav1.ObjectMeta{
            Name:      "odh-gateway",
            Namespace: rr.DSCI.Spec.ApplicationsNamespace,
        },
        Spec: serviceApi.GatewaySpec{
            Domain:           getGatewayDomain(ctx, rr.Client),
            GatewayClassName: "istio",
            Certificate: &serviceApi.GatewayCertificate{
                Type: serviceApi.CertManagerCertificate,
            },
        },
    }
    return rr.AddResources(gateway)
}
```

### **3. Update Action Chain**
Add missing actions to the controller setup:
```go
WithAction(initialize).
WithAction(createGatewayClass).          // NEW: Create GatewayClass
WithAction(createGatewayServiceResource). // NEW: Create Gateway service
WithAction(createCertificateResources).
WithAction(template.NewAction()).
WithAction(deploy.NewAction()).
```

### **4. Default Template Variables**
Ensure template variables are provided:
```go
func initialize(ctx context.Context, rr *odhtypes.ReconciliationRequest) error {
    domain, _ := getGatewayDomain(ctx, rr.Client)
    
    rr.Templates = []odhtypes.TemplateInfo{
        {
            FS:   resourcesFS,
            Path: GatewayTemplate,
            Variables: map[string]string{
                "Name":             "odh-gateway",
                "Namespace":        rr.DSCI.Spec.ApplicationsNamespace,
                "GatewayClassName": "istio",
                "Domain":           domain,
            },
        },
    }
    return nil
}
```

## Current Workaround

For immediate testing, manually create the missing resources:

### **1. Create GatewayClass**
```bash
kubectl apply -f - <<EOF
apiVersion: gateway.networking.k8s.io/v1
kind: GatewayClass
metadata:
  name: istio
spec:
  controllerName: istio.io/gateway-controller
  description: "Istio Gateway implementation"
EOF
```

### **2. Create Gateway Service Resource**
```bash
kubectl apply -f - <<EOF
apiVersion: services.platform.opendatahub.io/v1alpha1
kind: Gateway
metadata:
  name: odh-gateway
  namespace: opendatahub
spec:
  domain: "apps.example.com"
  gatewayClassName: "istio"
  certificate:
    type: "CertManager"
EOF
```

## Success Criteria

✅ **GatewayClass exists**: `kubectl get gatewayclasses` shows `istio` class  
✅ **Gateway service exists**: `kubectl get gateways.services.platform.opendatahub.io` shows `odh-gateway`  
✅ **Gateway API resource exists**: `kubectl get gateways` shows `odh-gateway`  
✅ **Gateway has istio class**: Gateway spec shows `gatewayClassName: istio`  
✅ **HTTPRoutes can reference Gateway**: Dashboard HTTPRoute can use Gateway for routing  

---

**Status**: 🔄 ACTIVE ISSUE  
**Priority**: HIGH - Blocks Gateway API migration functionality  
**Root Cause**: Missing GatewayClass and Gateway service resource creation  
**Solution**: Add missing controller actions to create required resources  
**Related**: PROBLEM_2.md (HTTPRoute domain resolution) 