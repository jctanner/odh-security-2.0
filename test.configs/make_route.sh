#!/bin/bash
# Script to create an OpenShift Route for the Gateway's LoadBalancer service
# This works around the lack of real LoadBalancer in CRC environments

set -e

echo "=== Gateway LoadBalancer Route Creator ==="
echo ""

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

# Get gateway UID for owner reference
GATEWAY_UID=$(kubectl get gateway "$GATEWAY_NAME" -n "$GATEWAY_NAMESPACE" -o jsonpath='{.metadata.uid}')

# Get gateway listener hostname
GATEWAY_HOSTNAME=$(kubectl get gateway "$GATEWAY_NAME" -n "$GATEWAY_NAMESPACE" -o jsonpath='{.spec.listeners[?(@.name=="https")].hostname}')
if [ -z "$GATEWAY_HOSTNAME" ]; then
    echo "⚠️  Warning: Could not find HTTPS listener hostname on gateway"
fi
echo "✓ Gateway hostname: $GATEWAY_HOSTNAME"

# Find the LoadBalancer service created for the gateway
GATEWAY_LB_SERVICE=$(kubectl get svc -n "$GATEWAY_NAMESPACE" -l "gateway.networking.k8s.io/gateway-name=$GATEWAY_NAME" -o jsonpath='{.items[0].metadata.name}')
if [ -z "$GATEWAY_LB_SERVICE" ]; then
    echo "❌ Error: Could not find LoadBalancer service for gateway $GATEWAY_NAME"
    exit 1
fi
echo "✓ Gateway LoadBalancer service: $GATEWAY_NAMESPACE/$GATEWAY_LB_SERVICE"

# Get service UID for owner reference
SERVICE_UID=$(kubectl get svc "$GATEWAY_LB_SERVICE" -n "$GATEWAY_NAMESPACE" -o jsonpath='{.metadata.uid}')

# Check current LoadBalancer status
EXTERNAL_ADDRESS=$(kubectl get svc "$GATEWAY_LB_SERVICE" -n "$GATEWAY_NAMESPACE" -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
if [ -z "$EXTERNAL_ADDRESS" ]; then
    EXTERNAL_ADDRESS=$(kubectl get svc "$GATEWAY_LB_SERVICE" -n "$GATEWAY_NAMESPACE" -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
fi

if [ -z "$EXTERNAL_ADDRESS" ]; then
    echo "⚠️  LoadBalancer external address is pending (expected in CRC)"
else
    echo "✓ Current external address: $EXTERNAL_ADDRESS"
fi

echo ""

# Check if Route already exists
ROUTE_NAME="gateway-lb-$GATEWAY_NAME"
if kubectl get route "$ROUTE_NAME" -n "$GATEWAY_NAMESPACE" &>/dev/null; then
    echo "⚠️  Route $ROUTE_NAME already exists"
    echo "Updating existing Route..."
    ACTION="updated"
else
    echo "📝 Creating new Route: $ROUTE_NAME"
    ACTION="created"
fi

# Use the gateway's hostname or generate one
if [ -n "$GATEWAY_HOSTNAME" ]; then
    ROUTE_HOSTNAME="$GATEWAY_HOSTNAME"
else
    ROUTE_HOSTNAME="$GATEWAY_NAME.$GATEWAY_NAMESPACE.apps-crc.testing"
fi

echo "Creating OpenShift Route to expose Gateway LoadBalancer..."

# Create the Route
kubectl apply -f - <<EOF
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: $ROUTE_NAME
  namespace: $GATEWAY_NAMESPACE
  labels:
    gateway-lb-route: "true"
    gateway.networking.k8s.io/gateway-name: $GATEWAY_NAME
  ownerReferences:
  - apiVersion: v1
    kind: Service
    name: $GATEWAY_LB_SERVICE
    uid: $SERVICE_UID
    controller: false
    blockOwnerDeletion: false
spec:
  host: $ROUTE_HOSTNAME
  to:
    kind: Service
    name: $GATEWAY_LB_SERVICE
    weight: 100
  port:
    targetPort: 443
  tls:
    termination: passthrough
    insecureEdgeTerminationPolicy: Redirect
EOF

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Successfully $ACTION Route $ROUTE_NAME"
    
    # Update the LoadBalancer service status with the Route hostname
    echo ""
    echo "📝 Updating LoadBalancer service status with Route hostname..."
    
    kubectl patch service "$GATEWAY_LB_SERVICE" -n "$GATEWAY_NAMESPACE" --subresource=status --type=merge -p="{
      \"status\": {
        \"loadBalancer\": {
          \"ingress\": [
            {
              \"hostname\": \"$ROUTE_HOSTNAME\"
            }
          ]
        }
      }
    }" 2>/dev/null || echo "⚠️  Note: Unable to patch service status (may require additional permissions)"
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📋 Configuration Summary"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Gateway:              $GATEWAY_NAMESPACE/$GATEWAY_NAME"
    echo "LoadBalancer Service: $GATEWAY_LB_SERVICE"
    echo "OpenShift Route:      $ROUTE_NAME"
    echo "Hostname:             $ROUTE_HOSTNAME"
    echo ""
    echo "🌐 Gateway is now accessible via:"
    echo "   https://$ROUTE_HOSTNAME"
    echo ""
    echo "✨ Any HTTPRoutes attached to this Gateway will now be"
    echo "   accessible through the OpenShift Route!"
    echo ""
    echo "📊 Check status:"
    echo "   oc get gateway,svc,route -n $GATEWAY_NAMESPACE"
    echo ""
    echo "🔍 View Gateway HTTPRoutes:"
    echo "   oc get httproute -A -o json | jq -r '.items[] | select(.spec.parentRefs[]?.name==\"$GATEWAY_NAME\") | \"\(.metadata.namespace)/\(.metadata.name)\"'"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
else
    echo "❌ Error: Failed to create Route"
    exit 1
fi