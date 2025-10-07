# Notebooks BYOIDC Design

## Problem Statement

In ./src/kubeflow/components/odh-notebook-controller we have a kubernetes controller which spawns notebooks based on webhooks. Those notebook pods also get oauth-proxy sidecar containers. We need to first assess the current code and get an understanding of all the things it does.

The primary goal is to replace the oauth-proxy container with kube-rbac-proxy and create an equivalent config file for kube-rbac-proxy similar to the openshift-sar declarations that is added as a configmap.

The next big change is switching from an ocp route CR to an httproute CR that points at the data-science-gateway and uses the notebooks path prefix.

## Requirements

1. **Replace oauth-proxy with kube-rbac-proxy**: Replace the oauth-proxy sidecar container with kube-rbac-proxy
2. **Create kube-rbac-proxy ConfigMap**: Generate equivalent config file for kube-rbac-proxy similar to openshift-sar declarations
3. **Switch to HTTPRoute**: Replace OpenShift Route CR with HTTPRoute CR that points to data-science-gateway
4. **Implement Path-based Routing**: Use notebooks path prefix for routing through data-science-gateway
5. **Remove OpenShift OAuth Dependencies**: Remove OAuthClient creation and OpenShift OAuth-specific configurations
6. **Maintain RBAC Authorization**: Preserve Kubernetes RBAC-based authorization for notebook access control
7. **Minimal Code Changes**: Modify the controller with as few changes as possible

## Design Considerations

### Current Architecture Analysis

The ODH Notebook Controller is a Kubernetes controller built with Kubebuilder that extends the Kubeflow notebook controller with OpenShift-specific capabilities:

#### Core Components:
1. **Main Controller** (`notebook_controller.go`): Watches Notebook CRD events and manages reconciliation
2. **Mutating Webhook** (`notebook_webhook.go`): Injects OAuth proxy sidecar into notebook pods
3. **OAuth Management** (`notebook_oauth.go`): Creates and manages OpenShift OAuth resources
4. **RBAC Management** (`notebook_rbac.go`): Handles RoleBindings and ClusterRoleBindings
5. **Route Management** (`notebook_route.go`): Creates OpenShift Routes for notebook access

#### Current OAuth Flow:
1. **Notebook Creation**: User creates Notebook with `notebooks.opendatahub.io/inject-oauth: "true"` annotation
2. **Webhook Injection**: Mutating webhook injects oauth-proxy sidecar container
3. **OAuth Resources**: Controller creates:
   - ServiceAccount with OAuth redirect reference
   - OAuthClient for OpenShift OAuth integration
   - OAuth secrets (cookie secret, client secret)
   - TLS Service for OAuth proxy
   - OpenShift Route with TLS termination
4. **Authentication**: Users authenticate via OpenShift OAuth service
5. **Authorization**: oauth-proxy uses `--openshift-sar` flag for RBAC checks

#### Current oauth-proxy Configuration:
```yaml
container:
  name: oauth-proxy
  image: registry.redhat.io/openshift4/ose-oauth-proxy@sha256:4f8d66597feeb32bb18699326029f9a71a5aca4a57679d636b876377c2e95695
  imagePullPolicy: Always
  env:
  - name: NAMESPACE
    valueFrom:
      fieldRef:
        fieldPath: metadata.namespace
  args:
  - --provider=openshift
  - --https-address=:8443
  - --http-address=
  - --openshift-service-account=<notebook-name>
  - --cookie-secret-file=/etc/oauth/config/cookie_secret
  - --cookie-expire=24h0m0s
  - --tls-cert=/etc/tls/private/tls.crt
  - --tls-key=/etc/tls/private/tls.key
  - --upstream=http://localhost:8888
  - --upstream-ca=/var/run/secrets/kubernetes.io/serviceaccount/ca.crt
  - --email-domain=*
  - --skip-provider-button
  - --client-id=<notebook-name>-<notebook-namespace>-oauth-client
  - --client-secret-file=/etc/oauth/client/secret
  - --scope=user:info user:check-access
  - --openshift-sar={"verb":"get","resource":"notebooks","resourceAPIGroup":"kubeflow.org","resourceName":"<notebook-name>","namespace":"$(NAMESPACE)"}
  ports:
  - name: oauth-proxy
    containerPort: 8443
    protocol: TCP
  volumeMounts:
  - name: oauth-client
    mountPath: /etc/oauth/client
  - name: oauth-config
    mountPath: /etc/oauth/config
  - name: tls-certificates
    mountPath: /etc/tls/private
  resources:
    requests:
      cpu: 100m
      memory: 64Mi
    limits:
      cpu: 100m
      memory: 64Mi
  livenessProbe:
    httpGet:
      path: /oauth/healthz
      port: oauth-proxy
      scheme: HTTPS
    initialDelaySeconds: 30
    timeoutSeconds: 1
    periodSeconds: 5
    successThreshold: 1
    failureThreshold: 3
  readinessProbe:
    httpGet:
      path: /oauth/healthz
      port: oauth-proxy
      scheme: HTTPS
    initialDelaySeconds: 5
    timeoutSeconds: 1
    periodSeconds: 5
    successThreshold: 1
    failureThreshold: 3
```

#### Key Dependencies on OpenShift OAuth:
- **OAuthClient Resource**: Creates OpenShift OAuthClient for each notebook
- **OAuth Redirect Reference**: ServiceAccount annotation references OpenShift Route
- **OpenShift OAuth Service**: Relies on internal OpenShift OAuth for authentication
- **oauth-proxy Sidecar**: Uses OpenShift-specific OAuth proxy image and configuration

### Key Components to Modify

#### 1. **Webhook Sidecar Injection** (`notebook_webhook.go`)
- **Function**: `InjectOAuthProxy()` - Replace oauth-proxy with kube-rbac-proxy
- **Changes**: 
  - Update container image from `registry.redhat.io/openshift4/ose-oauth-proxy` to kube-rbac-proxy
  - Modify environment variables and command arguments
  - Remove OpenShift OAuth-specific configuration
- **Image Configuration**: 
  - **Current**: Image passed via `--oauth-proxy-image` flag to main.go, defaults to `OAuthProxyImage` constant
  - **New**: Need to add `--kube-rbac-proxy-image` flag or update existing flag
  - **Default**: Should default to `kube-rbac-proxy` image

#### 2. **OAuth Resource Management** (`notebook_oauth.go`)
- **Functions to Remove/Modify**:
  - `ReconcileOAuthClient()` - Remove OAuthClient creation
  - `createOAuthClient()` - Remove OpenShift OAuthClient dependency
  - `NewNotebookOAuthClientSecret()` - Remove OAuth client secret generation
- **Functions to Keep**:
  - `ReconcileOAuthServiceAccount()` - Keep for kube-rbac-proxy service account
  - `ReconcileOAuthService()` - Keep for TLS service
  - `ReconcileOAuthSecret()` - Keep for cookie secret only
- **New Functions to Add**:
  - `ReconcileKubeRbacProxyConfigMap()` - Create kube-rbac-proxy configuration
  - `NewKubeRbacProxyConfigMap()` - Generate ConfigMap with kube-rbac-proxy config

#### 3. **ServiceAccount Configuration** (`notebook_oauth.go`)
- **Function**: `NewNotebookServiceAccount()`
- **Changes**: Remove OAuth redirect reference annotation, keep basic ServiceAccount

#### 4. **Route Configuration** (`notebook_route.go`)
- **Functions**: Route creation and TLS configuration
- **Changes**: Replace OpenShift Route with HTTPRoute pointing to data-science-gateway
- **New Functions to Add**:
  - `ReconcileHTTPRoute()` - Create HTTPRoute instead of OpenShift Route
  - `NewNotebookHTTPRoute()` - Generate HTTPRoute with path-based routing flow

#### 5. **Main Controller** (`notebook_controller.go`)
- **Function**: `Reconcile()` method
- **Changes**: Remove OAuthClient reconciliation calls

#### 6. **Image Configuration** (`main.go`, `notebook_oauth.go`, `config/manager/manager.yaml`)
- **Current**: 
  - `OAuthProxyImage` constant in `notebook_oauth.go` (hardcoded default)
  - `--oauth-proxy-image` flag in `main.go` with default value
  - **Hardcoded in deployment**: `config/manager/manager.yaml` line 28 has the full image URL
  - Passed to webhook via `OAuthConfig.ProxyImage`
- **New BYOIDC Approach**:
  - **Environment Variable**: `RELATED_IMAGE_OSE_KUBE_RBAC_PROXY_IMAGE` (set by operator)
  - **Default Fallback**: `kube-rbac-proxy` (if env var not set)
  - **Implementation**: Check env var first, fall back to default constant
  - **Deployment**: Use env var in `config/manager/manager.yaml` instead of hardcoded value
- **Changes**:
  - Update `OAuthProxyImage` constant to kube-rbac-proxy default
  - Add environment variable support in `main.go`
  - Update `config/manager/manager.yaml` to use env var
  - Rename flag to `--kube-rbac-proxy-image` or keep existing name
  - Update `OAuthConfig` struct if needed

### BYOIDC Integration Strategy

#### 1. **Replace oauth-proxy with kube-rbac-proxy**
- **Current**: Uses OpenShift oauth-proxy with `--openshift-sar` flag
- **BYOIDC**: Use kube-rbac-proxy with standard Kubernetes RBAC
- **Configuration**: 
  - Remove OpenShift OAuth-specific flags
  - Use standard kube-rbac-proxy configuration
  - Maintain same RBAC authorization logic

#### 2. **Remove OpenShift OAuth Dependencies**
- **OAuthClient**: Remove creation of OpenShift OAuthClient resources
- **OAuth Redirect Reference**: Remove ServiceAccount OAuth redirect annotation
- **OAuth Secrets**: Keep only cookie secret, remove client secret

#### 3. **Maintain Authentication Flow**
- **External OIDC**: Authentication handled by external OIDC provider (e.g., Keycloak)
- **Token Validation**: kube-rbac-proxy validates tokens via Kubernetes TokenReview API
- **User Context**: User information passed via headers (X-Auth-Request-User, X-Auth-Request-Groups)

#### 4. **Preserve RBAC Authorization**
- **Current**: Uses `--openshift-sar` for authorization checks
- **BYOIDC**: Use kube-rbac-proxy's built-in RBAC authorization
- **Authorization Logic**: Maintain same notebook access control via Kubernetes RBAC

#### 5. **Route Configuration**
- **Current**: Individual OpenShift Routes for each notebook
- **BYOIDC**: HTTPRoute pointing to data-science-gateway with path-based routing
- **Path Prefix**: Use `/notebooks/<notebook-name>` for routing
- **Gateway**: Routes through data-science-gateway for centralized authentication

#### 6. **HTTPRoute Architecture**
- **Current Flow**: `User -> OpenShift Route -> oauth-proxy -> Notebook`
- **New Flow**: `User -> HTTPRoute -> data-science-gateway -> kube-rbac-proxy -> Notebook`
- **Benefits**: Centralized authentication through data-science-gateway
- **Path Structure**: `/notebooks/<notebook-name>` for each notebook

#### 7. **kube-rbac-proxy ConfigMap Creation**
- **Current**: oauth-proxy uses `--openshift-sar` flag with JSON configuration
- **BYOIDC**: Create ConfigMap with kube-rbac-proxy configuration file
- **Configuration**: Equivalent to openshift-sar declarations but for kube-rbac-proxy

#### Image Configuration Implementation:
```go
// In notebook_oauth.go
const (
    // Default kube-rbac-proxy image if env var not set
    // Based on odh-dashboard: registry.redhat.io/openshift4/ose-kube-rbac-proxy-rhel9@sha256:784c4667a867abdbec6d31a4bbde52676a0f37f8e448eaae37568a46fcdeace7
    KubeRbacProxyImage = "registry.redhat.io/openshift4/ose-kube-rbac-proxy-rhel9@sha256:784c4667a867abdbec6d31a4bbde52676a0f37f8e448eaae37568a46fcdeace7"
)

// In main.go
func getKubeRbacProxyImage() string {
    if image := os.Getenv("RELATED_IMAGE_OSE_KUBE_RBAC_PROXY_IMAGE"); image != "" {
        return image
    }
    return controllers.KubeRbacProxyImage
}

// Usage in main.go
oauthProxyImage := getKubeRbacProxyImage()
```

#### Updated Deployment Manifest:
```yaml
# In config/manager/manager.yaml
env:
- name: RELATED_IMAGE_OSE_KUBE_RBAC_PROXY_IMAGE
  value: "registry.redhat.io/openshift4/ose-kube-rbac-proxy-rhel9@sha256:784c4667a867abdbec6d31a4bbde52676a0f37f8e448eaae37568a46fcdeace7"
args: ["--oauth-proxy-image", "$(RELATED_IMAGE_OSE_KUBE_RBAC_PROXY_IMAGE)"]
```

#### Target kube-rbac-proxy Configuration (based on odh-dashboard):
```yaml
container:
  name: kube-rbac-proxy
  image: registry.redhat.io/openshift4/ose-kube-rbac-proxy-rhel9@sha256:784c4667a867abdbec6d31a4bbde52676a0f37f8e448eaae37568a46fcdeace7
  args:
  - --secure-listen-address=0.0.0.0:8443
  - --upstream=http://localhost:8888
  - --config-file=/etc/kube-rbac-proxy/config-file.yaml
  - --tls-cert-file=/etc/tls/private/tls.crt
  - --tls-private-key-file=/etc/tls/private/tls.key
  - --auth-header-fields-enabled=true
  - --auth-header-user-field-name=X-Auth-Request-User
  - --auth-header-groups-field-name=X-Auth-Request-Groups
  - --proxy-endpoints-port=8444
  - --v=10
  ports:
  - name: notebook-ui
    containerPort: 8443
  - name: proxy-health
    containerPort: 8444
  volumeMounts:
  - name: proxy-tls
    mountPath: /etc/tls/private
  - name: kube-rbac-proxy-config
    mountPath: /etc/kube-rbac-proxy
  resources:
    requests:
      cpu: 100m
      memory: 64Mi
    limits:
      cpu: 100m
      memory: 64Mi
  livenessProbe:
    httpGet:
      path: /healthz
      port: 8444
      scheme: HTTPS
    initialDelaySeconds: 30
    timeoutSeconds: 1
    periodSeconds: 5
    successThreshold: 1
    failureThreshold: 3
  readinessProbe:
    httpGet:
      path: /healthz
      port: 8444
      scheme: HTTPS
    initialDelaySeconds: 5
    timeoutSeconds: 1
    periodSeconds: 5
    successThreshold: 1
    failureThreshold: 3
```

#### kube-rbac-proxy ConfigMap (based on odh-dashboard):
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: <notebook-name>-kube-rbac-proxy-config
  namespace: <notebook-namespace>
data:
  config-file.yaml: |+
    authorization:
      resourceAttributes:
        namespace: "<notebook-namespace>"
        apiGroup: "kubeflow.org"
        apiVersion: "v1"
        resource: "notebooks"
        verb: "get"
        name: "<notebook-name>"
```

#### HTTPRoute Configuration (based on odh-dashboard):
```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: <notebook-name>
  namespace: <notebook-namespace>
spec:
  parentRefs:
  - name: data-science-gateway
    kind: Gateway
    namespace: openshift-ingress
  rules:
  - matches:
    - path:
        type: PathPrefix
        value: /notebooks/<notebook-name>
    backendRefs:
    - name: <notebook-name>-tls
      port: 8443
```

## Implementation Plan

### Phase 1: Remove OpenShift OAuth Dependencies
- Remove OAuthClient creation and management functions
- Remove OAuth client secret generation
- Remove OAuth redirect reference from ServiceAccount
- Update main controller to skip OAuthClient reconciliation
- **Files**: `notebook_oauth.go`, `notebook_controller.go`

### Phase 2: Replace oauth-proxy with kube-rbac-proxy
- Update webhook sidecar injection to use kube-rbac-proxy
- Modify container image and configuration
- Update environment variables and command arguments
- Remove OpenShift OAuth-specific flags
- Create kube-rbac-proxy ConfigMap generation functions
- **Files**: `notebook_webhook.go`, `notebook_oauth.go`

### Phase 3: Update Configuration and Testing
- Update constants and configuration for kube-rbac-proxy
- Ensure Route configuration works with BYOIDC
- Add feature detection for BYOIDC vs OpenShift OAuth
- Implement backward compatibility
- **Files**: All modified files, add configuration management

### Phase 4: POC Validation
- Basic functionality testing with BYOIDC setup
- Verify notebook creation and access works
- Confirm kube-rbac-proxy configuration is correct

## Technical Details

### Authentication Flow

#### Current Flow (OpenShift OAuth):
1. User accesses notebook URL
2. OpenShift Route redirects to OpenShift OAuth service
3. User authenticates with OpenShift credentials
4. OAuth service redirects back with authorization code
5. oauth-proxy exchanges code for access token
6. oauth-proxy validates token and performs SAR check
7. User gains access to notebook

#### New Flow (BYOIDC):
1. User accesses notebook URL
2. External OIDC provider handles authentication
3. kube-rbac-proxy receives request with OIDC token
4. kube-rbac-proxy validates token via Kubernetes TokenReview API
5. kube-rbac-proxy performs RBAC authorization check
6. User gains access to notebook

### User Context Handling

#### Header-Based User Information:
- **X-Auth-Request-User**: Contains user identifier (e.g., `https://keycloak.example.com/realms/ocp#username`)
- **X-Auth-Request-Groups**: Contains pipe-separated groups (e.g., `odh-users|system:authenticated`)
- **X-Auth-Request-Email**: Contains user email for additional context

#### kube-rbac-proxy Configuration:
- Validates OIDC tokens via Kubernetes TokenReview API
- Maps OIDC groups to Kubernetes groups
- Performs RBAC authorization based on user's group membership
- Forwards user context to notebook application

### Security Considerations

#### 1. **Token Validation**
- kube-rbac-proxy validates OIDC tokens before allowing access
- Tokens are validated against the configured OIDC provider
- Invalid or expired tokens are rejected

#### 2. **RBAC Authorization**
- Maintains existing Kubernetes RBAC-based authorization
- Users must have appropriate permissions to access notebooks
- Group-based access control preserved

#### 3. **TLS Security**
- OpenShift Route provides TLS termination
- kube-rbac-proxy handles secure communication with notebook
- Cookie-based session management for user experience

#### 4. **Network Security**
- Notebook pods remain isolated within cluster
- kube-rbac-proxy acts as security boundary
- No direct external access to notebook containers

## POC Validation Strategy

### Basic Functionality Testing
- Verify notebook creation with BYOIDC annotation works
- Confirm kube-rbac-proxy sidecar is injected correctly
- Test notebook access through external OIDC provider
- Validate RBAC authorization still works

### Configuration Validation
- Verify kube-rbac-proxy ConfigMap is created correctly
- Confirm container arguments match expected configuration
- Test TLS certificate mounting and usage

## POC Implementation Notes

### Backward Compatibility
- For POC purposes, focus on BYOIDC mode only
- Existing OpenShift OAuth notebooks will need to be recreated
- No migration path needed for POC

### POC Deployment Strategy
- Deploy modified controller in test environment
- Create test notebooks with BYOIDC annotation
- Verify functionality with external OIDC provider

## Open Questions

1. **kube-rbac-proxy Configuration**: What specific configuration parameters are needed for kube-rbac-proxy to work with BYOIDC? How should it be configured to handle OIDC token validation?

2. **Backward Compatibility**: How should the controller detect whether to use OpenShift OAuth or BYOIDC? Should this be based on annotation, environment variable, or feature detection?

3. **OAuthClient Cleanup**: How should existing OAuthClient resources be cleaned up during migration from OpenShift OAuth to BYOIDC?

4. **Route Configuration**: Do OpenShift Routes need any specific configuration changes to work with BYOIDC authentication flow?

5. **User Group Mapping**: How should external OIDC groups be mapped to Kubernetes groups for RBAC authorization? Should this be handled by kube-rbac-proxy or the controller?

6. **Error Handling**: How should the controller handle cases where BYOIDC is not properly configured or kube-rbac-proxy fails to start?

7. **POC Environment**: What's the simplest way to set up a POC environment with external OIDC provider for testing?

## Related Documentation

- [Dashboard BYOIDC Design](./dashboard-byoidc-design.md)
- [Kube-RBAC-Proxy SAR Issue](./kube-rbac-proxy-sar.md)
- [Authentication Documentation](./AUTHN.md)

## References

- [Kubeflow Notebook Controller Documentation](https://github.com/kubeflow/kubeflow/tree/master/components/notebook-controller)
- [OpenDataHub Documentation](https://opendatahub.io/)
- [BYOIDC Architecture Overview](./AUTHN.md)

---

**Last Updated:** $(date)
**Status:** Draft
**Assigned:** TBD
