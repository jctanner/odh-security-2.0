#!/bin/bash

# Script to create an OAuth Proxy for the ODH Gateway with OpenShift authentication
# This provides authentication before traffic reaches the Gateway

set -e

echo "🔐 Setting up OAuth Proxy for ODH Gateway..."

# Configuration
NAMESPACE="openshift-ingress"
OAUTH_CLIENT_NAME="odh-gateway-oauth-client"
OAUTH_PROXY_NAME="odh-gateway-oauth-proxy"
GATEWAY_SERVICE="odh-gateway-odh-gateway-class"
#HOSTNAME="demo.odh.apps-crc.testing"  # Different hostname to avoid circular reference
HOSTNAME="gateway.apps-crc.testing"  # Different hostname to avoid circular reference

# Delete existing route if it exists
echo "🗑️  Removing existing route..."
kubectl delete route odh-gateway-route -n $NAMESPACE --ignore-not-found=true

# Generate cookie secret (32 bytes exactly for AES)
COOKIE_SECRET=$(openssl rand -hex 16)  # 32 hex chars = 16 bytes
CLIENT_SECRET=$(openssl rand -base64 32)

# Create OAuth client
echo "📝 Creating OAuth client..."
cat <<EOF | kubectl apply -f -
apiVersion: oauth.openshift.io/v1
kind: OAuthClient
metadata:
  name: $OAUTH_CLIENT_NAME
grantMethod: auto
redirectURIs:
- https://$HOSTNAME
- https://$HOSTNAME/oauth/callback
secret: $CLIENT_SECRET
EOF

# Create service account and RBAC
echo "👤 Creating service account and RBAC..."
kubectl create serviceaccount ${OAUTH_PROXY_NAME} -n $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -

cat <<EOF | kubectl apply -f -
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: ${OAUTH_PROXY_NAME}-tokenreviews
rules:
- apiGroups:
  - authentication.k8s.io
  resources:
  - tokenreviews
  verbs:
  - create
- apiGroups:
  - authorization.k8s.io
  resources:
  - subjectaccessreviews
  verbs:
  - create
EOF

cat <<EOF | kubectl apply -f -
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: ${OAUTH_PROXY_NAME}-tokenreviews
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: ${OAUTH_PROXY_NAME}-tokenreviews
subjects:
- kind: ServiceAccount
  name: ${OAUTH_PROXY_NAME}
  namespace: $NAMESPACE
EOF

# Create secrets
echo "🔑 Creating OAuth secrets..."
kubectl create secret generic ${OAUTH_PROXY_NAME}-client-secret \
  --from-literal=secret=$CLIENT_SECRET \
  -n $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic ${OAUTH_PROXY_NAME}-cookie-secret \
  --from-literal=cookie_secret=$COOKIE_SECRET \
  -n $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -

# Create a TLS secret for the proxy (using the same cert as gateway)
echo "🔐 Creating TLS secret for OAuth proxy..."
kubectl delete secret ${OAUTH_PROXY_NAME}-tls-secret -n $NAMESPACE --ignore-not-found=true
kubectl get secret odh-gateway-tls-secret -n $NAMESPACE -o yaml | \
  sed "s/name: odh-gateway-tls-secret/name: ${OAUTH_PROXY_NAME}-tls-secret/" | \
  sed '/resourceVersion:/d' | \
  sed '/uid:/d' | \
  sed '/creationTimestamp:/d' | \
  kubectl apply -f -

# Create OAuth proxy deployment
echo "🚀 Creating OAuth proxy deployment..."
cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: $OAUTH_PROXY_NAME
  namespace: $NAMESPACE
  labels:
    app.kubernetes.io/name: $OAUTH_PROXY_NAME
    app.kubernetes.io/component: oauth-proxy
    app.kubernetes.io/managed-by: opendatahub-operator
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: $OAUTH_PROXY_NAME
  template:
    metadata:
      labels:
        app.kubernetes.io/name: $OAUTH_PROXY_NAME
        app.kubernetes.io/component: oauth-proxy
    spec:
      containers:
      - name: oauth-proxy
        #image: registry.redhat.io/openshift4/ose-oauth-proxy:latest
        image: registry.tannerjc.net/oauth-proxy:latest
        args:
        - --https-address=:8443
        - --provider=openshift
        - --upstream=https://${GATEWAY_SERVICE}.${NAMESPACE}.svc.cluster.local:443
        #- --upstream=https://odh-gateway.odh.apps-crc.testing/
        #- --upstream=https://gateway.apps-crc.testing/
        # Use service account CA which should include OpenShift route certificates
        - --upstream-ca=/var/run/secrets/kubernetes.io/serviceaccount/ca.crt
        - --tls-cert=/etc/tls/private/tls.crt
        - --tls-key=/etc/tls/private/tls.key
        - --client-id=$OAUTH_CLIENT_NAME
        - --client-secret-file=/etc/oauth/client/secret
        - --scope=user:full
        - --cookie-secret-file=/etc/oauth/config/cookie_secret
        - --cookie-expire=23h0m0s
        - --pass-access-token
        #- --skip-auth-regex=^/api/health|^/api/status
        - --skip-provider-button
        - --email-domain=*
        # oauth-proxy bug: --ssl-insecure-skip-verify doesn't work for upstream connections
        # Workaround: Connect to service IP directly to bypass route certificate issues
        - --request-logging
        - --upstream-insecure-skip-verify
        ports:
        - containerPort: 8443
          name: https
          protocol: TCP
        livenessProbe:
          httpGet:
            path: /oauth/healthz
            port: 8443
            scheme: HTTPS
          initialDelaySeconds: 30
          timeoutSeconds: 1
          periodSeconds: 5
          successThreshold: 1
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /oauth/healthz
            port: 8443
            scheme: HTTPS
          initialDelaySeconds: 5
          timeoutSeconds: 1
          periodSeconds: 5
          successThreshold: 1
          failureThreshold: 3
        volumeMounts:
        - name: tls-secret
          mountPath: /etc/tls/private
          readOnly: true
        - name: client-secret
          mountPath: /etc/oauth/client
          readOnly: true
        - name: cookie-secret
          mountPath: /etc/oauth/config
          readOnly: true
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 500m
            memory: 256Mi
      volumes:
      - name: tls-secret
        secret:
          secretName: ${OAUTH_PROXY_NAME}-tls-secret
      - name: client-secret
        secret:
          secretName: ${OAUTH_PROXY_NAME}-client-secret
      - name: cookie-secret
        secret:
          secretName: ${OAUTH_PROXY_NAME}-cookie-secret
      serviceAccountName: ${OAUTH_PROXY_NAME}
EOF

# Create service for OAuth proxy
echo "🔗 Creating OAuth proxy service..."
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Service
metadata:
  name: $OAUTH_PROXY_NAME
  namespace: $NAMESPACE
  labels:
    app.kubernetes.io/name: $OAUTH_PROXY_NAME
    app.kubernetes.io/component: oauth-proxy
    app.kubernetes.io/managed-by: opendatahub-operator
spec:
  selector:
    app.kubernetes.io/name: $OAUTH_PROXY_NAME
  ports:
  - name: https
    port: 443
    targetPort: 8443
    protocol: TCP
  type: ClusterIP
EOF

# Create route pointing to OAuth proxy
echo "🌐 Creating route for OAuth proxy..."
cat <<EOF | kubectl apply -f -
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: odh-gateway-oauth-route
  namespace: $NAMESPACE
  labels:
    app.kubernetes.io/name: $OAUTH_PROXY_NAME
    app.kubernetes.io/component: oauth-proxy
    app.kubernetes.io/managed-by: opendatahub-operator
  annotations:
    opendatahub.io/managed: "true"
spec:
  host: $HOSTNAME
  port:
    targetPort: https
  tls:
    termination: passthrough
    insecureEdgeTerminationPolicy: Redirect
  to:
    kind: Service
    name: $OAUTH_PROXY_NAME
    weight: 100
  wildcardPolicy: None
EOF

if [ $? -eq 0 ]; then
    echo
    echo "✅ OAuth Proxy setup complete!"
    echo
    echo "📊 Checking deployment status..."
    kubectl get deployment $OAUTH_PROXY_NAME -n $NAMESPACE
    echo
    echo "🔗 Checking service status..."
    kubectl get service $OAUTH_PROXY_NAME -n $NAMESPACE
    echo
    echo "🌐 Checking route status..."
    kubectl get route odh-gateway-oauth-route -n $NAMESPACE
    echo
    echo "🎯 The Gateway is now accessible with authentication at:"
    echo "  https://$HOSTNAME"
    echo
    echo "🧪 Test the setup:"
    echo "  1. Visit https://$HOSTNAME in your browser"
    echo "  2. You should be redirected to OpenShift login"
    echo "  3. After login, you'll be proxied to the ODH Gateway (which routes to Dashboard)"
    echo
    echo "🔍 Debug commands:"
    echo "  kubectl logs -n $NAMESPACE -l app.kubernetes.io/name=$OAUTH_PROXY_NAME"
    echo "  kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=$OAUTH_PROXY_NAME"
else
    echo "❌ Failed to create OAuth proxy setup"
    exit 1
fi 
