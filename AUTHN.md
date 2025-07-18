# ODH Gateway Authentication Plan

## Overview

This document outlines the authentication and authorization implementation for the ODH Gateway using **Gateway-level authentication** with Istio's Envoy proxy and OpenShift OAuth integration.

## ⚠️ Current Status: Gateway-Level Authentication Not Working

**UPDATE**: After extensive testing and troubleshooting, we discovered that **Gateway-level authorization policies are not enforcing access control** in this environment, despite being correctly applied to the Envoy configuration.

### What We Tested
1. ✅ **Policy Application**: RequestAuthentication, AuthorizationPolicy, and EnvoyFilter resources are created and applied correctly
2. ✅ **Envoy Configuration**: Policies appear in the Gateway pod's Envoy configuration dump
3. ✅ **OAuth Setup**: OpenShift OAuth client, secret, and cluster configuration are working
4. ❌ **Access Control**: Authorization policies do not block unauthenticated traffic

### Evidence of the Issue
- Simple `DENY` policies with `notPaths` exclusions allow all traffic through
- JWT authentication filters are present in Envoy config but not enforcing
- No 401/403 responses are generated for unauthenticated requests
- Health endpoints and main application both return 200 OK without authentication

### Root Cause Analysis
The issue appears to be a **compatibility problem** between:
- Gateway API Gateway implementation
- Istio revision `openshift-gateway` 
- Authorization policies applied to Gateway-level traffic

### Recommended Alternatives
1. **OpenShift Route Authentication**: Use OpenShift's built-in authentication mechanisms
2. **Application-Level Authentication**: Implement authentication in the dashboard application
3. **Middleware Proxy**: Deploy a dedicated authentication proxy (e.g., OAuth2 Proxy)
4. **Full Service Mesh**: Enable sidecar injection for all services (more complex)

---

## Architecture Decision: Gateway-Level vs Service Mesh-Level Authentication

### Two Approaches Available

#### 1. **Full Service Mesh Approach** (NOT USED)
- **Requires**: Sidecar injection for all services (`istio-proxy` container in each pod)
- **Where auth happens**: At each service's sidecar proxy
- **Namespace**: `opendatahub` (where services run)
- **Selector**: `app=odh-dashboard`
- **Context**: `SIDECAR_INBOUND`
- **Pros**: Fine-grained per-service policies, full mesh observability
- **Cons**: Complex, requires mesh adoption for all services

#### 2. **Gateway-Level Approach** (ATTEMPTED - NOT WORKING)
- **Requires**: Only the Gateway (which already has Envoy via `istio-proxy`)
- **Where auth happens**: At the Gateway entry point before traffic reaches services
- **Namespace**: `openshift-ingress` (where Gateway runs)
- **Selector**: `app.kubernetes.io/name=odh-gateway`
- **Context**: `GATEWAY`
- **Pros**: Simpler, leverages existing Gateway infrastructure, no sidecar injection needed
- **Cons**: Coarser-grained control (Gateway-level only), **NOT WORKING IN THIS ENVIRONMENT**

### Why Gateway-Level Was Chosen (But Failed)

1. **Existing Infrastructure**: The ODH Gateway already runs an Envoy proxy (`istio-proxy` container)
2. **No Service Mesh Required**: Dashboard services don't need sidecar injection
3. **Simpler Deployment**: Single point of authentication at the Gateway
4. **Better Performance**: No additional proxy hops for internal traffic
5. **Easier Troubleshooting**: Centralized authentication logic

**However**, this approach **does not work** in the current environment due to compatibility issues between Gateway API and Istio authorization policies.

## Current State

- **Gateway**: `odh-gateway` in `openshift-ingress` namespace with Envoy proxy
- **HTTPRoute**: Routes `odh-gateway.odh.apps-crc.testing` to `odh-dashboard` service
- **Service**: `odh-dashboard` running without sidecar injection
- **Authentication**: None (direct access to dashboard) - **POLICIES NOT ENFORCING**

## Available Envoy Capabilities

The Gateway's Envoy proxy supports the following authentication/authorization features:

### WASM Runtime Support
- **Runtime**: `envoy.wasm.runtime.v8` (JavaScript/WebAssembly)
- **Use Cases**: Custom authentication, request/response transformation, rate limiting
- **Status**: Available for custom plugins if needed

### Built-in HTTP Filters
- **JWT Authentication**: `envoy.filters.http.jwt_authn`
- **OAuth2**: `envoy.filters.http.oauth2` (auto-redirect to IdP)
- **RBAC**: `envoy.filters.http.rbac`
- **External Authorization**: `envoy.filters.http.ext_authz`
- **Basic Auth**: `envoy.filters.http.basic_auth`

**Note**: While these filters are available and can be configured, they are **not enforcing access control** at the Gateway level in this environment.

## Implementation Plan

### Phase 1: Gateway-Level JWT + OAuth2 Authentication ❌ FAILED

**Goal**: Enable authentication at the Gateway level with auto-redirect to OpenShift login

**Status**: **FAILED** - Policies applied but not enforcing access control

**Components**:
1. **OpenShift OAuth Client** (`odh-gateway`) ✅ Created
2. **Istio RequestAuthentication** (validates JWT tokens) ✅ Applied
3. **Istio AuthorizationPolicy** (requires authentication) ✅ Applied, Not Working
4. **Envoy OAuth2 Filter** (handles login redirect) ✅ Applied, Not Working
5. **OAuth Cluster Configuration** (connectivity to OpenShift OAuth) ✅ Applied

**Namespace**: `openshift-ingress`
**Target**: Gateway pod with `app.kubernetes.io/name=odh-gateway` label

### Phase 2: Alternative Authentication Approach (RECOMMENDED)

**Goal**: Implement working authentication using alternative methods

**Options**:
1. **OpenShift Route Authentication**: Configure OpenShift Route with authentication
2. **Application-Level**: Implement authentication in the dashboard code
3. **Authentication Proxy**: Deploy OAuth2 Proxy or similar middleware
4. **Full Service Mesh**: Enable sidecar injection for fine-grained control

### Phase 3: Enhanced Authorization (Future)

**Goal**: Add fine-grained access control
- User/group-based authorization
- Resource-specific permissions
- Admin vs user role separation

### Phase 4: Custom WASM Plugins (Optional)

**Goal**: Advanced authentication features
- Custom JWT validation logic
- Request enrichment
- Advanced rate limiting

## Authentication Flow Comparison

### JWT-Only Flow (API Clients)
```
1. Client → Gateway (with Authorization: Bearer <token>)
2. Gateway → JWT validation (NOT WORKING)
3. Gateway → Dashboard (if valid)
4. Dashboard → Response
```

### Full OAuth Flow with Auto-Redirect (Browsers)
```
1. Browser → Gateway (no auth headers)
2. Gateway → Redirect to OpenShift login (NOT WORKING)
3. User → OpenShift login page
4. OpenShift → Redirect to Gateway /callback
5. Gateway → Exchange code for token
6. Gateway → Set session cookie
7. Gateway → Redirect to original URL
8. Browser → Dashboard (authenticated)
```

**Current Reality**: Both flows bypass authentication entirely and go directly to the dashboard.

## Step-by-Step Implementation (NON-WORKING)

### 1. Create OpenShift OAuth Client
```yaml
apiVersion: oauth.openshift.io/v1
kind: OAuthClient
metadata:
  name: odh-gateway
grantMethod: auto
redirectURIs:
- https://odh-gateway.odh.apps-crc.testing/callback
secret: odh-gateway-secret
```

### 2. Create OAuth Secret
```bash
oc create secret generic odh-oauth-secret \
  --from-literal=client-secret=odh-gateway-secret \
  -n openshift-ingress
```

### 3. Apply JWT Authentication
```yaml
apiVersion: security.istio.io/v1beta1
kind: RequestAuthentication
metadata:
  name: odh-gateway-oauth-jwt
  namespace: openshift-ingress
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: odh-gateway
  jwtRules:
  - issuer: "https://oauth-openshift.openshift-authentication.svc.cluster.local"
    jwksUri: "https://oauth-openshift.openshift-authentication.svc.cluster.local/.well-known/jwks"
    forwardOriginalToken: true
    audiences:
    - "https://kubernetes.default.svc.cluster.local"
    - "https://odh-gateway.odh.apps-crc.testing"
```

### 4. Apply Authorization Policy
```yaml
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: odh-gateway-require-auth
  namespace: openshift-ingress
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: odh-gateway
  rules:
  - from:
    - source:
        requestPrincipals: ["*"]
  - to:
    - operation:
        paths: ["/api/health", "/api/status"]
```

### 5. Configure OAuth2 Filter with Hybrid Behavior
```yaml
apiVersion: networking.istio.io/v1alpha3
kind: EnvoyFilter
metadata:
  name: odh-gateway-oauth2-filter
  namespace: openshift-ingress
spec:
  workloadSelector:
    labels:
      app.kubernetes.io/name: odh-gateway
  configPatches:
  - applyTo: HTTP_FILTER
    match:
      context: GATEWAY
      listener:
        filterChain:
          filter:
            name: envoy.filters.network.http_connection_manager
    patch:
      operation: INSERT_BEFORE
      value:
        name: envoy.filters.http.oauth2
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.filters.http.oauth2.v3.OAuth2
          config:
            token_endpoint:
              cluster_name: oauth_cluster
              uri: "https://oauth-openshift.openshift-authentication.svc.cluster.local/oauth/token"
            authorization_endpoint: "https://oauth-openshift.openshift-authentication.svc.cluster.local/oauth/authorize"
            redirect_uri: "https://odh-gateway.odh.apps-crc.testing/callback"
            redirect_path_matcher:
              path:
                exact: "/callback"
            signout_path:
              path:
                exact: "/signout"
            pass_through_matcher:
            - name: "api-calls"
              headers:
              - name: "authorization"
                present_match: true
            credentials:
              client_id: "odh-gateway"
              token_secret:
                name: "odh-oauth-secret"
                sds_config:
                  path: "/etc/ssl/certs/oauth-secret.yaml"
```

### 6. Configure OAuth Cluster
```yaml
apiVersion: networking.istio.io/v1alpha3
kind: EnvoyFilter
metadata:
  name: odh-gateway-oauth-cluster
  namespace: openshift-ingress
spec:
  workloadSelector:
    labels:
      app.kubernetes.io/name: odh-gateway
  configPatches:
  - applyTo: CLUSTER
    match:
      context: GATEWAY
    patch:
      operation: ADD
      value:
        name: oauth_cluster
        type: STRICT_DNS
        lb_policy: ROUND_ROBIN
        load_assignment:
          cluster_name: oauth_cluster
          endpoints:
          - lb_endpoints:
            - endpoint:
                address:
                  socket_address:
                    address: oauth-openshift.openshift-authentication.svc.cluster.local
                    port_value: 443
        transport_socket:
          name: envoy.transport_sockets.tls
          typed_config:
            "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.UpstreamTlsContext
            sni: oauth-openshift.openshift-authentication.svc.cluster.local
```

## User Experience (EXPECTED - NOT WORKING)

### For Browser Users (Auto-Redirect)
1. **Visit**: `https://odh-gateway.odh.apps-crc.testing`
2. **Expected**: Automatically redirected to OpenShift login
3. **Actual**: Direct access to dashboard without authentication
4. **Login**: Enter OpenShift credentials
5. **Return**: Automatically redirected back to dashboard
6. **Access**: Full dashboard access with session

### For API Clients (JWT)
1. **Get Token**: `oc whoami -t`
2. **API Call**: `curl -H "Authorization: Bearer <token>" https://odh-gateway.odh.apps-crc.testing`
3. **Expected**: JWT validation and authorized access
4. **Actual**: Direct API access without token validation

## Testing (RESULTS)

### Browser Testing
```bash
# Expected: Redirect to OpenShift login
# Actual: 200 OK with dashboard HTML
curl -k -v https://odh-gateway.odh.apps-crc.testing
```

### API Testing
```bash
# Expected: JWT validation required
# Actual: Works without token
curl -k -H "Authorization: Bearer $(oc whoami -t)" https://odh-gateway.odh.apps-crc.testing
```

### Health Check Testing
```bash
# Expected: Works without authentication
# Actual: Works (correctly)
curl -k https://odh-gateway.odh.apps-crc.testing/api/health
```

## Monitoring

### Key Metrics
- **Authentication Success Rate**: Not applicable (no authentication happening)
- **OAuth Flow Completion**: Not applicable (no redirects happening)
- **Response Times**: Normal (no authentication overhead)
- **Error Rates**: No 401/403 responses generated

### Debugging Commands
```bash
# Check Gateway pod status
kubectl get pods -n openshift-ingress | grep odh-gateway

# Check authentication policies
kubectl get requestauthentication,authorizationpolicy -n openshift-ingress

# Check EnvoyFilter configurations
kubectl get envoyfilter -n openshift-ingress

# View Gateway logs
kubectl logs -n openshift-ingress -l app.kubernetes.io/name=odh-gateway -f

# Check OAuth client
oc get oauthclient odh-gateway -o yaml

# Verify Envoy configuration includes policies
kubectl exec -n openshift-ingress <gateway-pod> -- pilot-agent request GET config_dump | grep -A10 rbac
```

## Troubleshooting

### Common Issues

1. **No Authentication Happening** ⚠️ **CURRENT ISSUE**
   - **Symptom**: All requests return 200 OK without authentication
   - **Root Cause**: Gateway-level authorization policies not enforcing access control
   - **Solution**: Use alternative authentication approach

2. **Policies Applied But Not Working** ⚠️ **CURRENT ISSUE**
   - **Symptom**: Policies visible in Envoy config but not blocking traffic
   - **Root Cause**: Compatibility issue between Gateway API and Istio authorization
   - **Solution**: Consider OpenShift Route authentication or application-level auth

3. **No Redirect Happening**
   - Check EnvoyFilter is applied to Gateway
   - Verify OAuth2 filter configuration
   - Check Gateway pod logs

4. **Redirect Loop**
   - Verify callback URL in OAuth client
   - Check redirect_uri in EnvoyFilter
   - Ensure OAuth secret exists

5. **JWT Validation Failures**
   - Check issuer and jwksUri in RequestAuthentication
   - Verify token audience matches configuration
   - Check OpenShift OAuth service accessibility

6. **Authorization Denied**
   - Verify AuthorizationPolicy rules
   - Check requestPrincipals in JWT
   - Ensure user has proper OpenShift access

## Security Considerations

### Token Security
- **JWT Validation**: Cryptographic signature verification
- **Audience Restriction**: Tokens only valid for specific services
- **Expiration**: Tokens have limited lifetime
- **Revocation**: OpenShift can revoke tokens

### TLS Security
- **End-to-End**: TLS from client to Gateway and Gateway to OpenShift
- **Certificate Validation**: Proper certificate chain verification
- **Secure Headers**: Authentication headers protected by TLS

### Session Management
- **Secure Cookies**: Session cookies with secure flags
- **Session Timeout**: Configurable session expiration
- **Logout**: Proper session cleanup on signout

## Performance Considerations

### Latency Impact
- **JWT Validation**: ~1-2ms per request (when working)
- **OAuth Flow**: Only impacts initial login
- **Caching**: JWT public keys cached for performance

### Throughput
- **No Sidecar Overhead**: Gateway-level authentication avoids service mesh performance impact
- **Connection Pooling**: Efficient connections to OpenShift OAuth
- **Filter Ordering**: OAuth2 filter positioned optimally

## Deployment

### Automated Deployment (NON-WORKING)
```bash
cd gateway.auth
./deploy-auth.sh
```

### Manual Steps (NON-WORKING)
1. Create OAuth client and secret
2. Apply authentication policies
3. Configure EnvoyFilters
4. Verify deployment
5. Test authentication flow

## Files Organization

```
gateway.auth/
├── deploy-auth.sh                    # Automated deployment script (creates non-working setup)
├── odh-gateway-authentication.yaml   # All Gateway-level auth policies (not enforcing)
├── odh-request-authentication.yaml   # (Legacy: service-level)
├── odh-authorization-policy.yaml     # (Legacy: service-level)
├── odh-oauth2-filter.yaml           # (Legacy: service-level)
├── odh-oauth-cluster.yaml           # (Legacy: service-level)
└── test-simple-deny.yaml            # Simple test policy (also not working)
```

**Note**: The legacy service-level files are preserved for reference but not used in the Gateway-level implementation. The Gateway-level files are created and applied correctly but do not enforce access control in this environment. 