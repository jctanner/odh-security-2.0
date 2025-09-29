# BUGS_TLS_001: TLS Certificate Verification in kube-auth-proxy

## Summary

kube-auth-proxy's OpenShift provider may fail to verify TLS certificates when connecting to OAuth servers on managed OpenShift clusters (ROSA, ARO, etc.) that use public CA certificates (e.g., Let's Encrypt). The issue stems from the provider's default behavior of only trusting the Kubernetes service account CA, which doesn't include public CAs.

---

## Background

### How kube-auth-proxy Handles TLS

kube-auth-proxy connects to two main endpoints:
1. **Kubernetes API Server** (e.g., `https://10.217.4.1:443`) - Uses self-signed certificates from the cluster's internal CA
2. **OAuth Server** (e.g., `https://oauth-openshift.apps-crc.testing`) - May use different certificates depending on cluster type

The application supports three TLS configuration modes:

#### 1. Default Behavior (No Flags Set)
- Uses Go's default system trust store
- Works for: Standard TLS connections with publicly-trusted CAs
- Fails for: Self-signed Kubernetes API certificates

#### 2. OpenShift Provider Auto-Detection
- Automatically loads `/var/run/secrets/kubernetes.io/serviceaccount/ca.crt`
- Works for: Kubernetes API and OAuth routes signed by the same CA
- Fails for: OAuth routes using different CAs (e.g., Let's Encrypt)

**Code Reference** (`src/kube-auth-proxy/providers/openshift.go:362-414`):
```go
func (p *OpenShiftProvider) newOpenShiftClient() (*http.Client, error) {
    capaths := p.CAFiles
    if len(capaths) == 0 {
        // DEFAULT: Auto-use service account CA
        capaths = []string{serviceAccountCAPath}  // "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
    }
    
    // Load CA certificates into pool
    for _, caPath := range capaths {
        caPEM, _ := os.ReadFile(caPath)
        pool.AppendCertsFromPEM(caPEM)
    }
    
    httpClient := &http.Client{
        Transport: &http.Transport{
            TLSClientConfig: &tls.Config{
                RootCAs:    pool,
                MinVersion: tls.VersionTLS12,
            },
        },
    }
}
```

#### 3. System Trust Store Mode (`--use-system-trust-store=true`)
- Loads system CAs **AND** adds the service account CA
- Works for: Both Kubernetes API and OAuth routes with any CA type
- Recommended for: Managed OpenShift clusters

**Code Reference** (`src/kube-auth-proxy/providers/openshift.go:379-387`):
```go
if p.useSystemTrustStore {
    // Loads system CAs first
    pool, _ = x509.SystemCertPool()
} else {
    pool = x509.NewCertPool()
}
// Then adds custom CAs on top
for _, caPath := range capaths {
    caPEM, _ := os.ReadFile(caPath)
    pool.AppendCertsFromPEM(caPEM)
}
```

---

## Problem Scenarios

### Scenario 1: CRC / Self-Hosted OpenShift (✅ Works by Default)

**Environment:**
- Local CRC cluster or self-hosted OpenShift
- OAuth route uses certificate from OpenShift's ingress CA
- Same CA signs both Kubernetes API and ingress certificates

**Configuration:**
```yaml
args:
- --provider=openshift
# No TLS flags needed
```

**Why it works:**
- Service account CA bundle includes both:
  - Kubernetes API CA: `CN=kube-apiserver-service-network-signer`
  - Ingress CA: `CN=ingress-operator@<timestamp>`
- Single CA file validates all endpoints

**Validation Test:**
```bash
# Inside pod:
curl --cacert /var/run/secrets/kubernetes.io/serviceaccount/ca.crt https://10.217.4.1:443/.well-known/oauth-authorization-server
# ✅ SSL certificate verify ok

curl --cacert /var/run/secrets/kubernetes.io/serviceaccount/ca.crt https://oauth-openshift.apps-crc.testing
# ✅ SSL certificate verify ok
```

### Scenario 2: Managed OpenShift with Public CA (❌ Fails by Default)

**Environment:**
- ROSA, ARO, or managed OpenShift on cloud providers
- OAuth route uses Let's Encrypt or other public CA
- Kubernetes API uses cluster's internal self-signed CA

**Configuration (Broken):**
```yaml
args:
- --provider=openshift
# Missing --use-system-trust-store=true
```

**Why it fails:**
```bash
# Inside pod:
curl --cacert /var/run/secrets/kubernetes.io/serviceaccount/ca.crt https://oauth.j7g4p9x9d6e0u1j.vzrg.p3.openshiftapps.com
# ❌ curl: (60) SSL certificate problem: unable to get local issuer certificate
```

- Service account CA only contains Kubernetes API CA
- Let's Encrypt CA is **not** in the service account CA bundle
- kube-auth-proxy cannot validate the OAuth server certificate

---

## Solution

### For Managed Clusters (ROSA, ARO, etc.)

Add the `--use-system-trust-store=true` flag to enable both system CAs and the Kubernetes CA:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kube-auth-proxy
spec:
  template:
    spec:
      containers:
      - name: kube-auth-proxy
        args:
        - --provider=openshift
        - --use-system-trust-store=true  # ADD THIS
        - --redirect-url=https://your-gateway.example.com/oauth2/callback
        # ... other args
```

**What this does:**
- ✅ Trusts Let's Encrypt CA (from system bundle) → validates OAuth route
- ✅ Trusts Kubernetes API CA (from service account) → validates K8s API
- ✅ Maintains full TLS verification (no insecure skip)

**Validation Test:**
```bash
# Inside pod with --use-system-trust-store=true:
curl https://oauth.j7g4p9x9d6e0u1j.vzrg.p3.openshiftapps.com
# ✅ SSL certificate verify ok (uses system CA bundle by default)
```

### Alternative: Explicit CA Files

If you prefer explicit control:

```yaml
args:
- --provider=openshift
- --provider-ca-file=/etc/pki/tls/certs/ca-bundle.crt
- --provider-ca-file=/var/run/secrets/kubernetes.io/serviceaccount/ca.crt
```

However, `--use-system-trust-store=true` is cleaner and recommended.

---

## Configuration Options Reference

### TLS-Related Flags

| Flag | Default | Purpose | When to Use |
|------|---------|---------|-------------|
| `--ssl-insecure-skip-verify` | `false` | **Disables all TLS verification** | ⚠️ Development only, never production |
| `--provider-ca-file` | (none) | Adds custom CA certificate files | When you need specific CA certificates |
| `--use-system-trust-store` | `false` | Includes system CA bundle + custom CAs | **Recommended for managed clusters** |

### OpenShift Provider Behavior

The OpenShift provider has built-in intelligence:

**Without any flags:**
- Auto-loads `/var/run/secrets/kubernetes.io/serviceaccount/ca.crt`
- Works for CRC and self-hosted clusters

**With `--use-system-trust-store=true`:**
- Loads system CAs (`/etc/pki/tls/certs/ca-bundle.crt`)
- **AND** adds service account CA
- Works for managed clusters with public CAs

**With `--provider-ca-file=/path/to/ca.crt`:**
- Uses specified CA file(s) instead of service account CA
- If `--use-system-trust-store=true` is also set, adds system CAs too

---

## Verification Steps

### 1. Check Certificate Chain

Determine what CA signs your OAuth route:

```bash
# From outside the cluster:
openssl s_client -showcerts -servername oauth.your-cluster.com -connect oauth.your-cluster.com:443 </dev/null 2>/dev/null | grep "issuer="

# Examples:
# CRC/Self-hosted: issuer=CN=ingress-operator@1756890346
# Managed/ROSA:    issuer=C=US; O=Let's Encrypt; CN=R13
```

### 2. Test Inside Pod

Exec into the kube-auth-proxy pod and test:

```bash
# Test with service account CA only:
curl --cacert /var/run/secrets/kubernetes.io/serviceaccount/ca.crt https://oauth.your-cluster.com
# If this fails but the next succeeds, you need --use-system-trust-store=true

# Test with system CA bundle:
curl https://oauth.your-cluster.com
# If this succeeds, the certificate is from a public CA
```

### 3. Verify kube-auth-proxy Configuration

Check the deployed configuration:

```bash
oc get deployment kube-auth-proxy -n openshift-ingress -o yaml | grep -A 20 "args:"
```

Look for:
- ✅ `--use-system-trust-store=true` (for managed clusters)
- ❌ `--ssl-insecure-skip-verify` (should never be present in production)

### 4. Check Logs

Monitor kube-auth-proxy logs for TLS errors:

```bash
oc logs -n openshift-ingress deployment/kube-auth-proxy --tail=100 -f
```

Look for:
- ❌ `x509: certificate signed by unknown authority`
- ❌ `tls: failed to verify certificate`
- ✅ `Auto-discovered LoginURL:` (indicates successful OAuth discovery)
- ✅ `Authenticated via OAuth2:` (indicates successful authentication)

---

## Security Considerations

### ✅ Secure Configurations

1. **Use system trust store on managed clusters:**
   ```yaml
   args:
   - --use-system-trust-store=true
   ```
   - Trusts both public CAs and Kubernetes CA
   - Full TLS verification enabled
   - Minimum TLS 1.2 enforced

2. **Default on CRC/self-hosted:**
   ```yaml
   args:
   - --provider=openshift
   # No additional flags needed
   ```
   - Auto-uses service account CA
   - Full TLS verification enabled

### ❌ Insecure Configurations (Never Use in Production)

```yaml
args:
- --ssl-insecure-skip-verify  # NEVER DO THIS
```

This flag:
- Disables **all** TLS certificate verification
- Allows man-in-the-middle attacks
- Should only be used in development/testing

---

## Related Code References

### Key Files

1. **`src/kube-auth-proxy/providers/openshift.go`**
   - Lines 361-414: `newOpenShiftClient()` - Creates HTTP client with CA configuration
   - Lines 379-387: System trust store loading logic
   - Lines 38-40: Service account path constants

2. **`src/kube-auth-proxy/pkg/validation/options.go`**
   - Lines 33-47: Global TLS configuration logic
   - Handles `--ssl-insecure-skip-verify` and `--provider-ca-file`

3. **`src/kube-auth-proxy/pkg/util/util.go`**
   - Lines 17-62: `GetCertPool()` - CA certificate loading utility

### Configuration Options

1. **`src/kube-auth-proxy/pkg/apis/options/providers.go`**
   - Lines 47-52: Provider CA file options
   - Defines `CAFiles` and `UseSystemTrustStore`

2. **`src/kube-auth-proxy/pkg/apis/options/options.go`**
   - Line 62: `SSLInsecureSkipVerify` option

---

## Testing Matrix

| Cluster Type | OAuth CA | Config Required | Status |
|--------------|----------|-----------------|--------|
| CRC | ingress-operator | None (default) | ✅ Works |
| Self-hosted OpenShift | ingress-operator | None (default) | ✅ Works |
| ROSA | Let's Encrypt | `--use-system-trust-store=true` | ✅ Works with flag |
| ARO (Azure) | Let's Encrypt | `--use-system-trust-store=true` | ✅ Works with flag |
| OCP on AWS/GCP | Cloud Provider CA | `--use-system-trust-store=true` | ✅ Works with flag |

---

## Recommendations

### For ODH/RHOAI Deployments

1. **Add `--use-system-trust-store=true` by default** in the kube-auth-proxy deployment manifest
   - Ensures compatibility with all cluster types
   - No negative impact on CRC/self-hosted (already trusted)
   - Fixes managed cluster deployments

2. **Update deployment templates:**
   ```yaml
   # src/odh-platform/controllers/gateway/kube_auth_proxy.go (or equivalent)
   args:
   - --use-system-trust-store=true  # Add this to default args
   ```

3. **Document in user-facing docs:**
   - Explain the difference between cluster types
   - Provide troubleshooting steps for TLS errors
   - Reference this document for technical details

### For Custom Deployments

- **Managed clusters**: Always use `--use-system-trust-store=true`
- **Air-gapped/custom CA**: Use `--provider-ca-file=/path/to/custom-ca.crt`
- **Development only**: `--ssl-insecure-skip-verify` (with strong warnings)

---

## Related Issues

- Gateway API HTTPRoute configuration
- Service account CA bundle contents
- OpenShift ingress certificate management
- Let's Encrypt certificate renewal

---

## Changelog

- **2025-09-29**: Initial documentation
  - Identified issue on managed clusters with Let's Encrypt
  - Validated solution with `--use-system-trust-store=true`
  - Tested on CRC and managed cluster environments
  - Documented code paths and configuration options
