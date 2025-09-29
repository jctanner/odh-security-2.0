#!/bin/bash
# Script to deploy echo-server with auto-discovered gateway configuration

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ECHO_YAML="$SCRIPT_DIR/echo.yaml"
TEMP_YAML="/tmp/echo-configured.yaml"

echo "=== Echo Server Deployment Creator ==="
echo ""

# Check if echo.yaml exists
if [ ! -f "$ECHO_YAML" ]; then
    echo "❌ Error: $ECHO_YAML not found"
    exit 1
fi

# Auto-discover the gateway
echo "🔍 Discovering Gateway..."
GATEWAY_INFO=$(kubectl get gateway --all-namespaces -o json | jq -r '.items[] | select(.metadata.name | contains("gateway")) | "\(.metadata.namespace)/\(.metadata.name)"' | head -1)

if [ -z "$GATEWAY_INFO" ]; then
    echo "❌ Error: No Gateway found in cluster"
    exit 1
fi

GATEWAY_NAMESPACE=$(echo "$GATEWAY_INFO" | cut -d'/' -f1)
GATEWAY_NAME=$(echo "$GATEWAY_INFO" | cut -d'/' -f2)
echo "✓ Found Gateway: $GATEWAY_NAMESPACE/$GATEWAY_NAME"

# Get gateway listener hostname for display
GATEWAY_HOSTNAME=$(kubectl get gateway "$GATEWAY_NAME" -n "$GATEWAY_NAMESPACE" -o jsonpath='{.spec.listeners[?(@.name=="https")].hostname}' 2>/dev/null || echo "")
if [ -n "$GATEWAY_HOSTNAME" ]; then
    echo "✓ Gateway hostname: $GATEWAY_HOSTNAME"
    # Extract base domain
    BASE_DOMAIN=$(echo "$GATEWAY_HOSTNAME" | sed 's/^[^.]*\.//')
fi

# Find the LoadBalancer service created for the gateway
GATEWAY_LB_SERVICE=$(kubectl get svc -n "$GATEWAY_NAMESPACE" -l "gateway.networking.k8s.io/gateway-name=$GATEWAY_NAME" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
if [ -n "$GATEWAY_LB_SERVICE" ]; then
    echo "✓ Gateway LoadBalancer service: $GATEWAY_NAMESPACE/$GATEWAY_LB_SERVICE"
fi

echo ""
echo "📝 Configuring echo-server deployment..."

# Read the original echo.yaml and replace gateway references
# Replace "odh-gateway" with discovered gateway name in HTTPRoute parentRefs
sed "s/name: odh-gateway/name: $GATEWAY_NAME/g" "$ECHO_YAML" | \
sed "s/namespace: openshift-ingress/namespace: $GATEWAY_NAMESPACE/g" > "$TEMP_YAML"

echo "✓ Updated gateway references:"
echo "  - Gateway name: $GATEWAY_NAME"
echo "  - Gateway namespace: $GATEWAY_NAMESPACE"

echo ""
echo "🚀 Deploying echo-server..."

# Apply the configured YAML
kubectl apply -f "$TEMP_YAML"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Successfully deployed echo-server"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📋 Deployment Summary"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Namespace:     opendatahub"
    echo "Deployment:    echo-server"
    echo "Service:       echo-server (http:8080, https:8443)"
    echo "Gateway:       $GATEWAY_NAMESPACE/$GATEWAY_NAME"
    echo ""
    echo "HTTPRoutes created:"
    echo "  1. echo-server-route (TLS, path: /echo)"
    echo "     Backend: echo-server:8443 (with kube-rbac-proxy)"
    echo ""
    echo "  2. echo-server-route-plaintext (plaintext, path: /echo-plaintext)"
    echo "     Backend: echo-server:8080 (direct to echo-server)"
    echo ""
    
    if [ -n "$GATEWAY_HOSTNAME" ] && [ -n "$BASE_DOMAIN" ]; then
        echo "🌐 Access URLs (once DNS is configured):"
        echo "   https://echo-server.opendatahub.$BASE_DOMAIN/echo"
        echo "   https://echo-server.opendatahub.$BASE_DOMAIN/echo-plaintext"
        echo ""
    fi
    
    echo "📊 Check deployment status:"
    echo "   kubectl get deploy,svc,httproute -n opendatahub -l app=echo-server"
    echo ""
    echo "🔍 View logs:"
    echo "   kubectl logs -n opendatahub -l app=echo-server -c echo-server --tail=50 -f"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # Clean up temp file
    rm -f "$TEMP_YAML"
else
    echo "❌ Error: Failed to deploy echo-server"
    rm -f "$TEMP_YAML"
    exit 1
fi
