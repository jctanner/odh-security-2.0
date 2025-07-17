#!/bin/bash
# manual-tinylb.sh

SERVICE_NAME="odh-lb-svc"
NAMESPACE="opendatahub"

if [ -z "$SERVICE_NAME" ] || [ -z "$NAMESPACE" ]; then
    echo "Usage: $0 <service-name> <namespace>"
    exit 1
fi

# Create the load-balancer service
kubectl apply -f - <<EOF
apiVersion: v1
kind: Service
metadata:
  name: $SERVICE_NAME
  namespace: $NAMESPACE
spec:
  type: LoadBalancer
  ports:
  - port: 443
    targetPort: 8443
    name: https
  - port: 80
    targetPort: 8080
    name: http
  selector:
    app: odh-gateway
EOF

# Get service details
SERVICE_UID=$(kubectl get service $SERVICE_NAME -n $NAMESPACE -o jsonpath='{.metadata.uid}')
SERVICE_TYPE=$(kubectl get service $SERVICE_NAME -n $NAMESPACE -o jsonpath='{.spec.type}')

# Check if it's a LoadBalancer service
if [ "$SERVICE_TYPE" != "LoadBalancer" ]; then
    echo "Service $SERVICE_NAME is not a LoadBalancer service"
    exit 1
fi

# Check if it already has external IP
EXTERNAL_IP=$(kubectl get service $SERVICE_NAME -n $NAMESPACE -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
if [ -n "$EXTERNAL_IP" ]; then
    echo "Service $SERVICE_NAME already has external IP: $EXTERNAL_IP"
    exit 0
fi

# Create the route
ROUTE_NAME="tinylb-$SERVICE_NAME"
HOSTNAME="$SERVICE_NAME-$NAMESPACE.apps-crc.testing"

kubectl apply -f - <<EOF
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: $ROUTE_NAME
  namespace: $NAMESPACE
  labels:
    tinylb.io/managed: "true"
    tinylb.io/service: $SERVICE_NAME
    tinylb.io/service-uid: $SERVICE_UID
  ownerReferences:
  - apiVersion: v1
    kind: Service
    name: $SERVICE_NAME
    uid: $SERVICE_UID
    controller: true
    blockOwnerDeletion: true
spec:
  host: $HOSTNAME
  to:
    kind: Service
    name: $SERVICE_NAME
    weight: 100
  port:
    targetPort: 443
  tls:
    termination: passthrough
    insecureEdgeTerminationPolicy: Redirect
EOF

# Update service status
kubectl patch service $SERVICE_NAME -n $NAMESPACE --subresource=status --type=merge -p="{
  \"status\": {
    \"loadBalancer\": {
      \"ingress\": [
        {
          \"hostname\": \"$HOSTNAME\"
        }
      ]
    }
  }
}"

echo "Successfully created route and updated service status for $SERVICE_NAME"
echo "External hostname: $HOSTNAME"
