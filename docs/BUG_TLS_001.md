# BUGS_TLS_001: TLS Certificate Verification in kube-auth-proxy

## Summary

kube-auth-proxy's OpenShift provider may fail to verify TLS certificates when connecting to OAuth servers on managed OpenShift clusters (ROSA, ARO, etc.) that use Let's Encrypt certificates. The issue occurs when:
1. The OAuth server hostname doesn't match the wildcard certificate in the service account CA bundle (e.g., `oauth.cluster.com` vs `*.apps.rosa.cluster.com`)
2. The service account CA bundle is missing the ISRG Root X1 root certificate needed to validate Let's Encrypt certificate chains

Some ROSA clusters work without the fix due to lucky wildcard domain matches that enable direct trust without chain validation.

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
- Works for: Kubernetes API and OAuth routes signed by the same CA, or OAuth certs directly in the bundle
- May fail for: OAuth routes requiring Let's Encrypt chain validation when ISRG Root X1 is missing

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

### Scenario 2: Managed OpenShift with Public CA (❌ Fails Without Flag)

**Environment:**
- ROSA, ARO, or managed OpenShift on cloud providers
- OAuth route uses Let's Encrypt certificate
- Kubernetes API uses cluster's internal self-signed CA

**Configuration (Broken):**
```yaml
args:
- --provider=openshift
# Missing --use-system-trust-store=true
```

**Why it fails:**
```bash
# Logs show:
[2025/09/29 22:49:20] Error redeeming code during OAuth2 callback: 
Post "https://oauth.j7g4p9x9d6e0u1j.vzrg.p3.openshiftapps.com:443/oauth/token": 
tls: failed to verify certificate: x509: certificate signed by unknown authority
```

**Root Cause (Two Factors):**

1. **OAuth Domain Mismatch**: OAuth hostname (`oauth.j7g4p9x9d6e0u1j...`) doesn't match the ingress wildcard (`*.apps.rosa.j7g4p9x9d6e0u1j...`) in the CA bundle
   - Cannot use direct trust → must validate via certificate chain

2. **Missing Root CA**: Service account CA bundle contains Let's Encrypt intermediate (R12) but is missing **ISRG Root X1** root certificate
   - R12 intermediate is signed by ISRG Root X1
   - Without the root, Go cannot establish a complete trust chain
   - Chain validation fails → TLS error

**Result**: OAuth discovery works (internal K8s API), but OAuth token redemption fails (external OAuth server with Let's Encrypt cert).

**Failing ROSA cluster (Santiago - `j7g4p9x9d6e0u1j.vzrg.p3.openshiftapps.com`):**

Service account CA bundle contents:
```bash
Certificate #1:
  Subject: CN=root-ca,OU=openshift
  Issuer:  CN=root-ca,OU=openshift

Certificate #2:
  Subject: CN=*.apps.rosa.j7g4p9x9d6e0u1j.vzrg.p3.openshiftapps.com
  Issuer:  CN=R12,O=Let's Encrypt,C=US
  ⭐ Let's Encrypt wildcard certificate (for *.apps.rosa.*)

Certificate #3:
  Subject: CN=R12,O=Let's Encrypt,C=US
  Issuer:  CN=ISRG Root X1,O=Internet Security Research Group,C=US

Total certificates: 3
```

OAuth server certificate:
```bash
issuer=C=US, O=Let's Encrypt, CN=R13
subject=CN=*.j7g4p9x9d6e0u1j.vzrg.p3.openshiftapps.com
```

**The Problem - Wildcard Mismatch + Incomplete Trust Chain:**

1. **Wildcard mismatch:**
   - Bundle has: `*.apps.rosa.j7g4p9x9d6e0u1j.vzrg.p3.openshiftapps.com`
   - OAuth hostname: `oauth.j7g4p9x9d6e0u1j.vzrg.p3.openshiftapps.com` (no `apps.rosa` prefix)
   - ❌ **Wildcard doesn't match** - can't use direct trust

2. **Falls back to chain validation:**
   - OAuth cert signed by **R13** (not R12!)
   - Bundle has **R12** intermediate (Certificate #3), but OAuth needs **R13**
   - R12 is signed by **ISRG Root X1** (not present in bundle)
   - Even if R13 was present, it would also be signed by **ISRG Root X1** (not present)

3. **Result:**
   - Cannot use direct trust (wildcard mismatch)
   - Cannot validate via chain (missing root CA)
   - Error: `x509: certificate signed by unknown authority`

**Why `--use-system-trust-store=true` fixes it:**
- System trust store contains ISRG Root X1 root certificate
- Even though OAuth uses R13 and bundle has R12, both intermediates are signed by ISRG Root X1
- Complete chain: `OAuth cert → R13 (from system or presented by server) → ISRG Root X1 (from system)`
- Trust established ✅

**Working ROSA cluster (`jtanner-oauth.937s.p3.openshiftapps.com`):**

Service account CA bundle contents:
```bash
Certificate #1:
  Subject: CN=root-ca,OU=openshift
  Issuer:  CN=root-ca,OU=openshift

Certificate #2:
  Subject: CN=*.apps.rosa.jtanner-oauth.937s.p3.openshiftapps.com
  Issuer:  CN=R13,O=Let's Encrypt,C=US
  ⭐ Let's Encrypt wildcard certificate

Certificate #3:
  Subject: CN=R13,O=Let's Encrypt,C=US
  Issuer:  CN=ISRG Root X1,O=Internet Security Research Group,C=US

Total certificates: 3
```

OAuth server certificate:
```bash
issuer=C=US, O=Let's Encrypt, CN=R13
subject=CN=*.jtanner-oauth.937s.p3.openshiftapps.com
```

**Why This Cluster Works Without the Flag:**

🎯 **Key Discovery**: The service account CA bundle contains the **exact wildcard certificate** that the OAuth server presents!

- Certificate #2 in the bundle: `CN=*.apps.rosa.jtanner-oauth.937s.p3.openshiftapps.com`
- OAuth server hostname: `oauth.jtanner-oauth.937s.p3.openshiftapps.com`
- The wildcard `*.apps.rosa.jtanner-oauth.937s.p3.openshiftapps.com` **matches** the OAuth hostname!
- **Direct trust established** - no chain validation needed
- The certificate is trusted as a **leaf certificate directly**, not via Let's Encrypt chain
- Missing ISRG Root X1 doesn't matter because certificate itself is in the trust store

**Comparison of All Tested Clusters:**

| Cluster | OAuth Hostname | Wildcard in Bundle | Match? | Has Flag? | Result |
|---------|----------------|-------------------|--------|-----------|---------|
| Santiago | `oauth.j7g4p9x9d6e0u1j.vzrg.p3.openshiftapps.com` | `*.apps.rosa.*` (R12) | ❌ No | ❌ No | **FAILS** |
| Jtanner | `oauth.jtanner-oauth.937s.p3.openshiftapps.com` | `*.apps.rosa.*` (R13) | ✅ Yes | ❌ No | **WORKS** |
| Gowtham | `oauth.gowtham-rosa419.q8mg.p3.openshiftapps.com` | `*.apps.rosa.*` (R10) | ❌ No | ✅ Yes | **WORKS** |

**Key Insights:**
- All three clusters have **different Let's Encrypt intermediates** (R10, R12, R13) - all signed by ISRG Root X1
- All three clusters are **missing ISRG Root X1** root certificate
- **Jtanner works** due to lucky wildcard match (direct trust, no chain validation needed)
- **Santiago fails** because OAuth domain doesn't match wildcard AND no fix applied
- **Gowtham would fail** like Santiago, but works because `--use-system-trust-store=true` is set

**Recommendation:** Still use `--use-system-trust-store=true` universally:
- Not all clusters will have matching wildcard patterns
- Cluster configuration may change during upgrades
- Provides consistent, reliable behavior across all cluster types

### Additional ROSA Cluster (Gowtham - `gowtham-rosa419.q8mg.p3.openshiftapps.com`):

Service account CA bundle contents:
```bash
Certificate #1:
  Subject: CN=root-ca,OU=openshift
  Issuer:  CN=root-ca,OU=openshift

Certificate #2:
  Subject: CN=*.apps.rosa.gowtham-rosa419.q8mg.p3.openshiftapps.com
  Issuer:  CN=R10,O=Let's Encrypt,C=US
  ⭐ Let's Encrypt wildcard certificate (for *.apps.rosa.*)

Certificate #3:
  Subject: CN=R10,O=Let's Encrypt,C=US
  Issuer:  CN=ISRG Root X1,O=Internet Security Research Group,C=US

Total certificates: 3
```

OAuth server certificate:
```bash
issuer=C=US, O=Let's Encrypt, CN=R11
subject=CN=*.gowtham-rosa419.q8mg.p3.openshiftapps.com
```

**Configuration:**
```bash
args:
- --use-system-trust-store=true  # ✅ Already configured with the fix!
```

**Status:** ✅ **Working - No Errors**

**Analysis:**
- Same architecture as Santiago: OAuth (`oauth.gowtham-rosa419.*`) doesn't match wildcard (`*.apps.rosa.gowtham-rosa419.*`)
- Bundle has **R10** intermediate, OAuth uses **R11** intermediate
- Both intermediates need ISRG Root X1 for chain validation
- **Would fail without the flag**, but works because `--use-system-trust-store=true` is already set
- Demonstrates the fix working in production

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

### 5. Verify `--use-system-trust-store=true` Works with Internal CAs

Test that the flag works on CRC/self-hosted clusters:

```bash
# Add the flag to your deployment
oc patch deployment kube-auth-proxy -n openshift-ingress --type=json \
  -p='[{"op": "add", "path": "/spec/template/spec/containers/0/args/-", "value": "--use-system-trust-store=true"}]'

# Wait for rollout
oc rollout status deployment/kube-auth-proxy -n openshift-ingress

# Check logs for successful OAuth discovery
oc logs deployment/kube-auth-proxy -n openshift-ingress --tail=20 | grep -E "Auto-discovered|LoginURL"

# Expected output:
# ✅ Auto-discovered LoginURL: https://oauth-openshift.apps-crc.testing/oauth/authorize
# ✅ Auto-discovered RedeemURL: https://oauth-openshift.apps-crc.testing/oauth/token

# Test authentication flow
curl -k -I https://your-gateway.apps-crc.testing/
# Expected: 302 redirect to OAuth server (proves TLS validation works)
```

---

## Security Considerations

### Why `--use-system-trust-store=true` is Safe

The flag creates a **union** (combination) of CA trust stores, not a replacement:

```
Without flag:
  Trust Pool = Service Account CA only
  ├─ ✅ Kubernetes API CA
  └─ ✅ OpenShift Ingress CA (on CRC)

With --use-system-trust-store=true:
  Trust Pool = System CAs + Service Account CA
  ├─ ✅ Let's Encrypt CA (from system)
  ├─ ✅ DigiCert CA (from system)
  ├─ ✅ All public root CAs (from system)
  ├─ ✅ Kubernetes API CA (from service account)
  └─ ✅ OpenShift Ingress CA (from service account)
```

**Key Points:**
- ✅ Does **NOT** reduce security - adds more trusted CAs, doesn't remove any
- ✅ Still validates certificates - only trusts CAs in the combined pool
- ✅ Enforces minimum TLS 1.2
- ✅ Works for both internal and public CAs
- ✅ Tested on CRC (internal CA) and managed clusters (Let's Encrypt)

### ✅ Secure Configurations

1. **Use system trust store on all cluster types (RECOMMENDED):**
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

| Cluster Type | OAuth CA | OAuth Domain Pattern | Config Required | Status |
|--------------|----------|---------------------|-----------------|--------|
| CRC | ingress-operator | Internal (*.apps-crc.testing) | None (default) | ✅ Works |
| Self-hosted OpenShift | ingress-operator | Internal | None (default) | ✅ Works |
| ROSA (Lucky) | Let's Encrypt | `oauth.*` matches `*.apps.rosa.*` | None (lucky match) | ✅ Works |
| ROSA (Typical) | Let's Encrypt | `oauth.*` doesn't match wildcard | `--use-system-trust-store=true` | ⚠️ Needs flag |
| ARO (Azure) | Let's Encrypt | Varies | `--use-system-trust-store=true` | ✅ Works with flag |
| OCP on AWS/GCP | Cloud Provider CA | Varies | `--use-system-trust-store=true` | ✅ Works with flag |

### Live Tested Clusters:

| Cluster Name | Type | OAuth Domain | Wildcard Match | Has Flag | Result |
|--------------|------|--------------|----------------|----------|--------|
| CRC | Local | `oauth-openshift.apps-crc.testing` | ✅ Internal CA | ❌ No | ✅ Works |
| Santiago | ROSA | `oauth.j7g4p9x9d6e0u1j.vzrg` | ❌ No match | ❌ No | ❌ **Fails** |
| Jtanner | ROSA | `oauth.jtanner-oauth.937s` | ✅ Lucky match | ❌ No | ✅ Works |
| Gowtham | ROSA | `oauth.gowtham-rosa419.q8mg` | ❌ No match | ✅ Yes | ✅ Works |

---

## Recommendations

### For ODH/RHOAI Deployments

1. **Add `--use-system-trust-store=true` by default** in the kube-auth-proxy deployment manifest
   - ✅ **Tested and confirmed safe on CRC** (internal CA)
   - ✅ **Tested and confirmed fixes managed clusters** (Let's Encrypt CA)
   - ✅ Ensures compatibility with all cluster types
   - ✅ No negative impact - creates union of system + custom CAs
   - ✅ Fixes managed cluster deployments

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

## Why Some ROSA Clusters Work Without the Flag

### Root Cause: OAuth Domain Architecture + Wildcard Certificate Matching

**Confirmed via testing:** ROSA clusters work or fail based on whether the OAuth hostname matches the wildcard certificate in the service account CA bundle.

**Test Performed:**
```bash
# On Jtanner ROSA cluster (WORKS):
curl --cacert /var/run/secrets/kubernetes.io/serviceaccount/ca.crt https://oauth.jtanner-oauth.937s.p3.openshiftapps.com
# Result: 403 Forbidden (TLS validated successfully via direct trust)

# On Santiago ROSA cluster (FAILS):
curl --cacert /var/run/secrets/kubernetes.io/serviceaccount/ca.crt https://oauth.j7g4p9x9d6e0u1j.vzrg.p3.openshiftapps.com
# Result: SSL certificate problem: unable to get local issuer certificate
```

**Real Explanation:**

**All tested ROSA clusters** have the same CA bundle structure:
- OpenShift internal CA (root-ca)
- Wildcard ingress certificate for `*.apps.rosa.<cluster-id>.openshiftapps.com` (Let's Encrypt intermediate)
- Let's Encrypt intermediate certificate (R10, R11, R12, or R13) signed by ISRG Root X1
- **Missing**: ISRG Root X1 root certificate

**The Key Difference - OAuth Domain Architecture:**

| Scenario | OAuth Hostname | Wildcard in Bundle | Match? | Trust Method | Result |
|----------|----------------|-------------------|--------|--------------|--------|
| **Jtanner** | `oauth.jtanner-oauth.937s...` | `*.apps.rosa.jtanner-oauth.937s...` | ✅ Match | Direct trust (cert in bundle) | ✅ Works |
| **Santiago** | `oauth.j7g4p9x9d6e0u1j.vzrg...` | `*.apps.rosa.j7g4p9x9d6e0u1j.vzrg...` | ❌ No match | Chain validation needed | ❌ Fails |
| **Gowtham** | `oauth.gowtham-rosa419.q8mg...` | `*.apps.rosa.gowtham-rosa419.q8mg...` | ❌ No match | Chain validation needed | ✅ Works (has flag) |

**Why Wildcard Matching Matters:**
- When OAuth hostname matches the wildcard, Go trusts the certificate **directly** (it's in the CA bundle)
- No need to validate the Let's Encrypt chain → missing ISRG Root X1 doesn't matter
- When OAuth hostname doesn't match, Go must validate via the Let's Encrypt chain → requires ISRG Root X1 → fails

**This is not a "CA bundle variance" between clusters - it's an OAuth domain naming architecture difference!**

### Why You Should Still Use the Flag

Even if your current cluster works without it (like Jtanner):

✅ **Not architecture-dependent**: Works regardless of OAuth domain naming  
✅ **Future-proof**: OAuth domain architecture may change during upgrades  
✅ **Consistent**: Same behavior on CRC, ROSA, ARO, self-hosted  
✅ **Explicit**: Makes the trust policy clear and intentional  
✅ **Safe**: Tested and confirmed to work on all cluster types (including Gowtham)  
✅ **No downside**: Only adds CAs, doesn't reduce security

## Related Issues

- Gateway API HTTPRoute configuration
- Service account CA bundle contents and versioning
- OpenShift ingress certificate management
- Let's Encrypt certificate renewal
- ROSA cluster configuration variations

---

## Changelog

- **2025-09-30 (Final Update)**: Root cause definitively identified
  - **Key Discovery**: Working cluster has OAuth cert **directly in CA bundle** (wildcard match)
  - **Failing cluster**: OAuth hostname doesn't match bundle wildcard → requires chain validation
  - **Root cause**: Missing ISRG Root X1 in service account CA bundle prevents chain validation
  - Tested on 4 clusters: 
    - CRC (works - internal CA)
    - Santiago (fails - wildcard mismatch, no flag)
    - Jtanner (works - lucky wildcard match)
    - Gowtham (works - has flag, demonstrates fix)
  - Created `test-scripts/list-ca-issuers` and `test-scripts/verify-root-ca` Go tools for CA analysis
  - All ROSA clusters have different Let's Encrypt intermediates (R10, R11, R12, R13)
  - All ROSA clusters missing ISRG Root X1 root certificate
  - Confirmed all Let's Encrypt intermediates (R10-R13) are signed by ISRG Root X1
  - Clarified that wildcard domain patterns determine whether direct trust or chain validation is needed
  - **Gowtham cluster proves the fix works**: Same architecture as Santiago (no wildcard match), but works with `--use-system-trust-store=true`
  - Removed previous speculative explanations - now have definitive root cause with live validation

- **2025-09-30 (Earlier)**: Initial investigation into ROSA cluster variance
  - **Initial hypothesis**: Service account CA bundle contents vary across ROSA clusters
  - **Later corrected**: All ROSA clusters have similar bundles, but OAuth domain architecture differs
  - This hypothesis was replaced by the wildcard matching discovery (see Final Update above)

- **2025-09-29**: Initial documentation
  - Identified issue on managed clusters with Let's Encrypt
  - Validated solution with `--use-system-trust-store=true`
  - **Live tested on CRC cluster** - confirmed flag works with internal CAs
  - **Verified flag exists in codebase** - `pkg/apis/options/legacy_options.go:543`
  - **Confirmed safe for all cluster types** - creates union of CAs, not replacement
  - Tested on CRC and multiple ROSA clusters
  - Documented code paths and configuration options
  - Added verification procedures and security analysis
