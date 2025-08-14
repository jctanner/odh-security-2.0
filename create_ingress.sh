#!/bin/bash

# Script to create a simple, unauthenticated route to the ODH Gateway.

set -e

echo "🌐 Creating unauthenticated route for ODH Gateway..."

# Configuration
NAMESPACE="openshift-ingress"
GATEWAY_SERVICE="odh-gateway-odh-gateway-class"
ROUTE_NAME="odh-gateway-unauthenticated-route"
HOSTNAME="gateway.apps-crc.testing"

# Delete existing route if it exists
echo "🗑️  Removing existing route..."
kubectl delete route ${ROUTE_NAME} -n ${NAMESPACE} --ignore-not-found=true

# Create route pointing to the gateway service
echo "🌐 Creating route for ODH Gateway..."
cat <<EOF | kubectl apply -f -
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: ${ROUTE_NAME}
  namespace: ${NAMESPACE}
  labels:
    app: odh-gateway-unauthenticated-ingress
spec:
  host: ${HOSTNAME}
  port:
    targetPort: https
  tls:
    termination: passthrough
    insecureEdgeTerminationPolicy: Redirect
  to:
    kind: Service
    name: ${GATEWAY_SERVICE}
    weight: 100
  wildcardPolicy: None
EOF

if [ $? -eq 0 ]; then
    echo
    echo "✅ Unauthenticated route setup complete!"
    echo
    echo "🌐 Checking route status..."
    kubectl get route ${ROUTE_NAME} -n ${NAMESPACE}
    echo
    echo "🎯 The Gateway is now accessible without authentication at:"
    echo "  https://${HOSTNAME}"
    echo
else
    echo "❌ Failed to create the route"
    exit 1
fi
