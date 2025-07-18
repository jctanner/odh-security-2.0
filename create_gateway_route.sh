#!/bin/bash

# Script to create an OpenShift Route for the ODH Gateway with TLS passthrough
# This exposes the Gateway service externally so it can receive traffic

echo "Creating OpenShift Route for ODH Gateway..."

# Create the Route YAML
cat <<EOF | kubectl apply -f -
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: odh-gateway-route
  namespace: openshift-ingress
  labels:
    app.kubernetes.io/name: odh-gateway
    app.kubernetes.io/component: gateway
    app.kubernetes.io/managed-by: opendatahub-operator
  annotations:
    opendatahub.io/managed: "true"
spec:
  host: odh-gateway.odh.apps-crc.testing
  port:
    targetPort: 443
  tls:
    termination: passthrough
    insecureEdgeTerminationPolicy: Redirect
  to:
    kind: Service
    name: odh-gateway-odh-gateway-class
    weight: 100
  wildcardPolicy: None
EOF

if [ $? -eq 0 ]; then
    echo "✅ Route created successfully!"
    echo
    echo "Checking Route status..."
    kubectl get route odh-gateway-route -n openshift-ingress
    echo
    echo "The Gateway should now be accessible at:"
    echo "  https://odh-gateway.odh.apps-crc.testing"
    echo
    echo "You can test it with:"
    echo "  curl -k -v https://odh-gateway.odh.apps-crc.testing"
else
    echo "❌ Failed to create Route"
    exit 1
fi 