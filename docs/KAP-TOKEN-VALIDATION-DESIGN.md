# kube-auth-proxy Token Validation Design

## Problem Summary

The kube-auth-proxy currently rejects OpenShift service account bearer tokens, preventing API clients from authenticating with standard Kubernetes/OpenShift authentication mechanisms. While cookie-based OAuth authentication works correctly for browser-based users, programmatic access using bearer tokens fails.

**Important Note on JWT Security**: JWTs ARE fully validated by the proxy with comprehensive OIDC verification (signature, expiry, issuer, audience). The problem is NOT weak validation—it's that valid OpenShift tokens (format: `sha256~...`) are rejected before validation because they don't match JWT format (format: `eyJ...`). This document proposes adding support for non-JWT bearer tokens without weakening the existing strong JWT validation.

## Current Behavior

### Working: Cookie-Based Authentication
Requests with the `_oauth2_proxy` cookie successfully authenticate:
```
Cookie: _oauth2_proxy=<encoded_session>
→ 200 OK (authenticated as kubeadmin@cluster.local)
```

### Failing: Bearer Token Authentication
Requests with OpenShift service account tokens are rejected:
```
Authorization: Bearer sha256~tk6tyeWJfk_r-pnPfABdnuv0hyrPWPJndfA1i-MSx8Y
→ 302 Redirect to login page (authentication failed)
```

### Error Logs
```
[jwt_session.go:54] Error retrieving session from token in Authorization header: 
    no valid bearer token found in authorization header
[oauthproxy.go:1031] No valid authentication in request. Initiating login.
```

## Root Cause Analysis

### Location
`src/kube-auth-proxy/pkg/middleware/jwt_session.go`

### The Problem

The JWT session loader only accepts tokens matching JWT format:

```go
const jwtRegexFormat = `^ey[a-zA-Z0-9_-]*\.ey[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]+$`

func (j *jwtSessionLoader) findTokenFromHeader(header string) (string, error) {
    tokenType, token, err := splitAuthHeader(header)
    if err != nil {
        return "", err
    }

    if tokenType == "Bearer" && j.jwtRegex.MatchString(token) {
        // Found a JWT as a bearer token
        return token, nil
    }
    // ...
    return "", fmt.Errorf("no valid bearer token found in authorization header")
}
```

**JWT tokens** start with `ey` (base64-encoded `{"alg":...}` and `{"typ":...}`)  
**OpenShift SA tokens** use format `sha256~<base62-encoded-value>`

The regex check at line 117 fails for OpenShift tokens, causing immediate rejection before any validation or pass-through logic can occur.

### JWT Validation Process (When Token Passes Regex)

**Important**: JWTs that pass the regex check ARE fully validated. The validation is comprehensive and includes:

#### 1. Format Check (`jwt_session.go:117`)
```go
if tokenType == "Bearer" && j.jwtRegex.MatchString(token) {
    return token, nil  // Pass to validation
}
```

#### 2. OIDC Verification (`pkg/providers/oidc/verifier.go:46`)
When a JWT passes format check, it undergoes full OIDC validation via `github.com/coreos/go-oidc/v3/oidc`:

```go
func (v *idTokenVerifier) Verify(ctx context.Context, rawIDToken string) (*oidc.IDToken, error) {
    // Full OIDC library validation includes:
    // - Signature verification against JWKS (public keys from issuer)
    // - Expiration check (exp claim)
    // - Not-before check (nbf claim)
    // - Issuer validation (iss claim matches expected)
    // - Claims parsing and validation
    token, err := v.verifier.Verify(ctx, rawIDToken)
    if err != nil {
        return nil, fmt.Errorf("failed to verify token: %v", err)
    }

    // Additional custom audience validation
    if isValidAudience, err := v.verifyAudience(token, claims); !isValidAudience {
        return nil, err
    }
    
    return token, err
}
```

#### 3. Audience Validation (`pkg/providers/oidc/verifier.go:63-84`)
Custom validation ensures the `aud` claim matches allowed audiences:
- Client ID must match
- Or one of the extra audiences must match

#### Validation Summary Table

| Token Type | Regex Check | OIDC Validation | Result |
|------------|-------------|-----------------|--------|
| Valid JWT | ✅ Pass | ✅ Full validation (signature, expiry, issuer, audience) | Authenticated |
| Expired JWT | ✅ Pass | ❌ Fail (expiry check) | Rejected |
| Invalid signature JWT | ✅ Pass | ❌ Fail (signature verification) | Rejected |
| Wrong audience JWT | ✅ Pass | ❌ Fail (audience check) | Rejected |
| OpenShift SA token | ❌ **Fail** | Never reached | **Rejected at format check** |

**Key Insight**: The security posture for JWTs is strong. The problem is NOT that tokens are unvalidated—it's that valid OpenShift tokens are rejected before they can be processed at all.

### Current Configuration

The kube-auth-proxy deployment includes relevant flags:
```bash
--provider=openshift
--pass-access-token=true
--skip-jwt-bearer-tokens=false  # (default)
```

However, `--skip-jwt-bearer-tokens` only works for **valid** JWTs that can be verified. Non-JWT tokens are rejected before this logic is reached.

## Impact

This issue prevents:
1. **API clients** from accessing ODH dashboard APIs with service account tokens
2. **CLI tools** from authenticating (e.g., `oc`, `kubectl`, custom scripts)
3. **Service-to-service** communication using SA tokens
4. **CI/CD pipelines** from accessing protected endpoints
5. **Integration with Kubernetes RBAC** for fine-grained access control

## Proposed Solutions

### Option 1: Pass-Through Mode for Non-JWT Bearer Tokens (Recommended)

Add a new configuration flag to allow non-JWT bearer tokens to pass through to the upstream service without validation.

**Key Design Principle**: This option preserves all existing JWT validation logic. JWTs continue to be fully validated at the proxy. Only non-JWT bearer tokens (which currently fail the format check) are passed through.

#### Implementation

**1. Add new configuration option** (`src/kube-auth-proxy/pkg/apis/options/options.go`):
```go
type Options struct {
    // ... existing fields ...
    SkipJwtBearerTokens      bool `flag:"skip-jwt-bearer-tokens" cfg:"skip_jwt_bearer_tokens"`
    PassThroughBearerTokens  bool `flag:"pass-through-bearer-tokens" cfg:"pass_through_bearer_tokens"`
    // ... rest of fields ...
}
```

**2. Add flag definition** (`src/kube-auth-proxy/pkg/apis/options/options.go`):
```go
flagSet.Bool("pass-through-bearer-tokens", false, 
    "allow non-JWT bearer tokens to pass through to upstream service without validation")
```

**3. Modify JWT session loader** (`src/kube-auth-proxy/pkg/middleware/jwt_session.go`):
```go
type jwtSessionLoader struct {
    jwtRegex               *regexp.Regexp
    sessionLoaders         []middlewareapi.TokenToSessionFunc
    denyInvalidJWTs        bool
    passThroughBearerTokens bool  // NEW
}

func NewJwtSessionLoader(
    sessionLoaders []middlewareapi.TokenToSessionFunc, 
    bearerTokenLoginFallback bool,
    passThroughBearerTokens bool,  // NEW
) alice.Constructor {
    js := &jwtSessionLoader{
        jwtRegex:                regexp.MustCompile(jwtRegexFormat),
        sessionLoaders:          sessionLoaders,
        denyInvalidJWTs:         !bearerTokenLoginFallback,
        passThroughBearerTokens: passThroughBearerTokens,  // NEW
    }
    return js.loadSession
}

func (j *jwtSessionLoader) findTokenFromHeader(header string) (string, error) {
    tokenType, token, err := splitAuthHeader(header)
    if err != nil {
        return "", err
    }

    if tokenType == "Bearer" {
        if j.jwtRegex.MatchString(token) {
            // Found a JWT as a bearer token
            // This will still go through full OIDC validation (signature, expiry, etc.)
            return token, nil
        }
        
        // NEW: If pass-through mode is enabled, accept non-JWT tokens
        // These will NOT be validated at the proxy - upstream must validate them
        if j.passThroughBearerTokens {
            return token, nil
        }
    }

    if tokenType == "Basic" {
        // Check if we have a Bearer token masquerading in Basic
        return j.getBasicToken(token)
    }

    return "", fmt.Errorf("no valid bearer token found in authorization header")
}
```

**4. Create pass-through session loader** (new function in jwt_session.go):
```go
// PassThroughTokenToSession creates a minimal session for non-JWT bearer tokens
// that should be passed through to the upstream service for validation
func PassThroughTokenToSession(ctx context.Context, token string) (*sessionsapi.SessionState, error) {
    // Don't validate the token - let upstream handle it
    // Create a minimal session that marks the request as authenticated
    // but delegates actual authorization to the upstream service
    return &sessionsapi.SessionState{
        AccessToken: token,
        // Set minimal user info to indicate pass-through mode
        User:  "pass-through",
        Email: "pass-through@bearer-token",
    }, nil
}
```

#### Deployment Configuration

Add to kube-auth-proxy startup args:
```yaml
args:
  - --pass-through-bearer-tokens=true
  - --pass-access-token=true
```

#### Security Considerations

- **Upstream validation required**: When using this mode, the upstream service MUST validate bearer tokens
- **No RBAC at proxy level**: Authorization decisions are delegated entirely to upstream
- **Token exposure**: Tokens are passed in `Authorization` header and/or `X-Forwarded-Access-Token`
- **Audit logging**: All pass-through requests should be logged with token type

### Option 2: OpenShift Token Validator

Implement native OpenShift service account token validation in the proxy.

#### Implementation

**1. Add OpenShift token validator**:
```go
// NewOpenShiftTokenValidator creates a validator for OpenShift SA tokens
func NewOpenShiftTokenValidator(apiServerURL string) TokenValidator {
    return &openShiftValidator{
        apiServer: apiServerURL,
        client:    &http.Client{...},
    }
}

func (v *openShiftValidator) ValidateToken(ctx context.Context, token string) (*sessionsapi.SessionState, error) {
    // Use TokenReview API to validate the token
    review := &authenticationv1.TokenReview{
        Spec: authenticationv1.TokenReviewSpec{
            Token: token,
        },
    }
    
    // Call Kubernetes API to validate token
    result, err := v.client.Create(ctx, review)
    if err != nil {
        return nil, err
    }
    
    if !result.Status.Authenticated {
        return nil, errors.New("token not authenticated")
    }
    
    return &sessionsapi.SessionState{
        User:        result.Status.User.Username,
        Email:       result.Status.User.Username,
        AccessToken: token,
        Groups:      result.Status.User.Groups,
    }, nil
}
```

**2. Update JWT session loader** to try OpenShift validator for non-JWT tokens

#### Pros
- True validation at proxy level
- Can enforce RBAC at proxy layer
- Provides user/group information

#### Cons
- Adds latency (extra API call per request)
- More complex implementation
- Requires proxy to have TokenReview permissions
- May require caching to maintain performance

### Option 3: Expand JWT Regex Pattern

Modify the JWT regex to also accept OpenShift token format.

#### Implementation
```go
const jwtRegexFormat = `^(ey[a-zA-Z0-9_-]*\.ey[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]+|sha256~[a-zA-Z0-9_-]+)$`
```

#### Pros
- Minimal code change
- Fast implementation

#### Cons
- Still requires validation logic for non-JWT tokens
- Doesn't solve the validation problem
- May accept invalid token formats

## Recommendation

**Implement Option 1: Pass-Through Mode** as the primary solution because:

1. **Simplest implementation** - minimal code changes
2. **Best performance** - no additional validation overhead
3. **Follows microservices pattern** - authentication at proxy, authorization at service
4. **Backward compatible** - disabled by default
5. **Aligns with current architecture** - upstream services already validate tokens

Later, **Option 2 can be added** as an enhancement for use cases requiring proxy-level authorization.

## Implementation Plan

### Phase 1: Pass-Through Mode (Week 1)
- [ ] Add `--pass-through-bearer-tokens` flag to options
- [ ] Modify `jwt_session.go` to accept non-JWT tokens when flag enabled
- [ ] Add pass-through session creation logic
- [ ] Update constructor to accept new parameter
- [ ] Add unit tests for pass-through behavior

### Phase 2: Testing & Validation (Week 1-2)
- [ ] Test with OpenShift service account tokens
- [ ] Test with JWT tokens (ensure no regression)
- [ ] Test with cookie-based auth (ensure no regression)
- [ ] Integration testing with ODH dashboard
- [ ] Security review of pass-through implementation

### Phase 3: Documentation & Deployment (Week 2)
- [ ] Update configuration documentation
- [ ] Add security considerations guide
- [ ] Update deployment manifests
- [ ] Create upgrade guide
- [ ] Deploy to test environment

### Phase 4: Optional Enhancement (Future)
- [ ] Implement OpenShift token validator (Option 2)
- [ ] Add caching layer for validated tokens
- [ ] Add metrics for token validation
- [ ] Add proxy-level RBAC enforcement

## Testing Strategy

### Unit Tests
```go
func TestPassThroughBearerTokens(t *testing.T) {
    tests := []struct{
        name           string
        token          string
        passThrough    bool
        expectAccepted bool
    }{
        {"JWT token with passthrough off", "eyJhbG...", false, true},
        {"JWT token with passthrough on", "eyJhbG...", true, true},
        {"OpenShift token with passthrough off", "sha256~abc...", false, false},
        {"OpenShift token with passthrough on", "sha256~abc...", true, true},
    }
    // ... test implementation
}
```

### Integration Tests
- Deploy kube-auth-proxy with `--pass-through-bearer-tokens=true`
- Test API calls with OpenShift SA token
- Verify token reaches upstream service
- Verify upstream can validate token
- Test with invalid tokens (should be rejected by upstream)

### Security Tests
- Verify tokens are not logged
- Test token validation at upstream
- Verify no token leakage in error messages
- Test with expired/invalid tokens

## Deployment Configuration

### Current Configuration
```yaml
containers:
- name: kube-auth-proxy
  args:
  - --http-address=0.0.0.0:4180
  - --https-address=0.0.0.0:8443
  - --provider=openshift
  - --pass-access-token=true
  - --set-xauthrequest=true
  - --skip-provider-button
  # ... other args
```

### Proposed Configuration
```yaml
containers:
- name: kube-auth-proxy
  args:
  - --http-address=0.0.0.0:4180
  - --https-address=0.0.0.0:8443
  - --provider=openshift
  - --pass-access-token=true
  - --set-xauthrequest=true
  - --skip-provider-button
  - --pass-through-bearer-tokens=true  # NEW
  # ... other args
```

## Security Considerations

### Current Security Posture

**JWT Validation**: The proxy performs comprehensive validation of JWT tokens:
- ✅ Cryptographic signature verification against issuer's JWKS
- ✅ Expiration and not-before time checks
- ✅ Issuer validation
- ✅ Audience validation
- ✅ Claims parsing and validation

**Cookie Sessions**: OAuth cookie-based sessions are secure and fully validated.

**OpenShift Tokens**: Currently rejected at format check (the problem this design addresses).

### Threats with Pass-Through Mode

1. **Malicious tokens**: Invalid OpenShift tokens could reach upstream if not validated there
2. **Token theft**: Bearer tokens in headers could be logged or exposed
3. **Authorization bypass**: If upstream doesn't validate, unauthorized access possible
4. **Replay attacks**: Without validation, stolen tokens remain valid until upstream detects them

### Mitigations

1. **Upstream validation mandatory**: 
   - Document requirement for upstream token validation
   - Upstream MUST use Kubernetes TokenReview API or similar
   - Upstream MUST enforce RBAC based on validated identity

2. **Secure logging**: 
   - Never log bearer token values (only log token type/format)
   - Redact Authorization headers in debug logs

3. **HTTPS only**: 
   - Enforce TLS for all proxy communications
   - No plaintext token transmission

4. **Header sanitization**: 
   - Remove duplicate auth headers
   - Normalize header forwarding

5. **Rate limiting**: 
   - Implement rate limits on authentication failures
   - Detect and block brute force attempts

6. **Monitoring**: 
   - Alert on unusual patterns (many pass-through tokens)
   - Track validation failures at upstream

### Security Comparison: Current vs Pass-Through Mode

| Scenario | Current Behavior | With Pass-Through Mode |
|----------|------------------|------------------------|
| Valid JWT | ✅ Validated at proxy | ✅ Validated at proxy (unchanged) |
| Invalid JWT | ✅ Rejected at proxy | ✅ Rejected at proxy (unchanged) |
| Valid OpenShift token | ❌ Rejected at proxy | ⚠️ Passed to upstream for validation |
| Invalid OpenShift token | ❌ Rejected at proxy | ⚠️ Passed to upstream (rejected there) |
| Cookie session | ✅ Validated at proxy | ✅ Validated at proxy (unchanged) |

**Note**: Pass-through mode does NOT weaken JWT security. It only adds a path for non-JWT tokens to reach upstream services.

### Validation Points
```
┌──────────┐     Bearer Token     ┌────────────────┐     Token + Headers     ┌──────────┐
│  Client  │ ─────────────────────> │ kube-auth-proxy│ ────────────────────────> │ Upstream │
└──────────┘                        └────────────────┘                          └──────────┘
                                           │                                          │
                                           │ Format Check                             │ Token Validation
                                           │ (JWT or pass-through)                    │ (TokenReview API)
                                           │ No validation                            │ RBAC enforcement
```

## Monitoring & Observability

### Metrics to Add
- `kube_auth_proxy_passthrough_tokens_total` - Count of pass-through token requests
- `kube_auth_proxy_jwt_tokens_total` - Count of JWT token requests
- `kube_auth_proxy_token_validation_errors_total` - Failed validations
- `kube_auth_proxy_token_type` - Label: jwt, passthrough, cookie

### Log Events
- `[INFO] Pass-through bearer token request to <upstream>`
- `[DEBUG] Token type detected: openshift-sa`
- `[WARN] Pass-through token with no upstream validation`

## References

### Related Code
- `src/kube-auth-proxy/pkg/middleware/jwt_session.go` - JWT session loader
- `src/kube-auth-proxy/pkg/apis/options/options.go` - Configuration options
- `src/opendatahub-operator/internal/controller/services/gateway/gateway_support.go` - Gateway deployment

### OpenShift Token Format
- Service Account tokens: `sha256~<base62-characters>`
- OAuth tokens: `sha256~<base62-characters>`
- JWT format: `eyJhbGc...` (base64 JSON header)

### Related Issues
- Requests with Bearer tokens redirect to login (302)
- Error: "no valid bearer token found in authorization header"
- Cookie-based auth works, token-based auth fails

## Future Considerations

1. **Multiple authentication methods**: Support both JWT and OpenShift tokens simultaneously
2. **Token caching**: Cache validated tokens to reduce upstream API calls
3. **Custom token formats**: Allow regex patterns for custom token formats
4. **Proxy-level RBAC**: Implement authorization checks in proxy
5. **Token transformation**: Convert OpenShift tokens to JWTs for upstream
6. **Audit logging**: Detailed audit trail of all authentication attempts

