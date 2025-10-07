# Dashboard BYOIDC Design

## Problem Statement

In ./src/odh-dashboard is the code for the opendatahub-dashboard. It's current architecture is very tied to openshift's internal oauth mechanisms and an oauth-proxy sidecar setting headers for it. Within the backend code, it makes queries to the openshift API for user and group info. In a cluster with BYOIDC (external oidc) and no internal oauth service, the user and group CRDs don't exist so it's user+group queries fail.

```
odh-dashboard-568585d48f-z5tqt kube-rbac-proxy I1001 21:33:46.456872       1 round_trippers.go:466] curl -v -XPOST  -H "Content-Type: application/json" -H "User-Agent: kube-rbac-proxy/v0.0.0 (linux/amd64) kubernetes/$Format" -H "Authorization: Bearer <masked>" -H "Accept: application/json, */*" 'https://172.30.0.1:443/apis/authentication.k8s.io/v1/tokenreviews'
odh-dashboard-568585d48f-z5tqt kube-rbac-proxy I1001 21:33:46.457326       1 round_trippers.go:510] HTTP Trace: Dial to tcp:172.30.0.1:443 succeed
odh-dashboard-568585d48f-z9fgg odh-dashboard {"level":50,"time":1759354426464,"pid":12,"hostname":"odh-dashboard-568585d48f-z9fgg","msg":"Failed to retrieve username: Error getting Oauth Info for user, HTTP request failed"}
odh-dashboard-568585d48f-z9fgg odh-dashboard {"level":50,"time":1759354426464,"pid":12,"hostname":"odh-dashboard-568585d48f-z9fgg","reqId":"req-s","req":{"method":"GET","url":"/api/config","hostname":"data-science-gateway.apps.rosa.jtanner-byoidc2.pkym.p3.openshiftapps.com","remoteAddress":"127.0.0.1","remotePort":36010},"res":{"statusCode":500},"err":{"type":"InternalServerError","message":"Failed to retrieve username: Error getting Oauth Info for user, HTTP request failed","stack":"InternalServerError: Failed to retrieve username: Error getting Oauth Info for user, HTTP request failed\n    at createCustomError (/usr/src/app/backend/dist/utils/requestUtils.js:7:45)\n    at getUserInfo (/usr/src/app/backend/dist/utils/userUtils.js:74:60)\n    at process.processTicksAndRejections (node:internal/process/task_queues:95:5)\n    at async testAdmin (/usr/src/app/backend/dist/utils/route-security.js:12:22)\n    at async handleSecurityOnRouteData (/usr/src/app/backend/dist/utils/route-security.js:112:13)\n    at async Object.<anonymous> (/usr/src/app/backend/dist/utils/route-security.js:136:5)","code":500,"explicitInternalServerError":true,"error":"Unauthorized","status":500,"statusCode":500,"expose":false},"msg":"Failed to retrieve username: Error getting Oauth Info for user, HTTP request failed"}
odh-dashboard-568585d48f-z9fgg odh-dashboard {"level":30,"time":1759354426465,"pid":12,"hostname":"odh-dashboard-568585d48f-z9fgg","reqId":"req-s","res":{"statusCode":500},"responseTime":11.75662299990654,"msg":"request completed"}
odh-dashboard-568585d48f-z9fgg odh-dashboard {"level":50,"time":1759354426470,"pid":12,"hostname":"odh-dashboard-568585d48f-z9fgg","msg":"Failed to retrieve username: Error getting Oauth Info for user, HTTP request failed"}
odh-dashboard-568585d48f-z9fgg odh-dashboard {"level":50,"time":1759354426470,"pid":12,"hostname":"odh-dashboard-568585d48f-z9fgg","msg":"Error writing log. Failed to retrieve username: Error getting Oauth Info for user, HTTP request failed"}
```

We know in a BYOIDC setup that it shouldn't try to make those queries. Instead, the code can actually obtain most of what it needs about the users and their member groups from the request headers. Here's some example header data from a live system ...

```
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "en-US,en;q=0.5",
    "Cookie": "ajs_user_id=6a8c46c42de0a8567f5be9472393f431c2731f87; ajs_anonymous_id=bbdc2084-28a9-44ee-856c-1564274ed1dd; analytics_session_id=1759324714884; analytics_session_id.last_access=1759324784935; _oauth2_proxy=l7iYDRYdRx5h..",
    "Dnt": "1",
    "Host": "data-science-gateway.apps.rosa.jtanner-byoidc2.pkym.p3.openshiftapps.com",
    "Priority": "u=0, i",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Sec-Gpc": "1",
    "Te": "trailers",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:143.0) Gecko/20100101 Firefox/143.0",
    "X-Auth-Request-Access-Token": "eyJhbGciOiJSUzI1N...",
    "X-Auth-Request-Email": "kubeadmin@example.com",
    "X-Auth-Request-Groups": "cluster-admins|system:authenticated",
    "X-Auth-Request-User": "https://keycloak.tannerjc.net/realms/ocp-byoidc-realm#kubeadmin",
    "X-Envoy-Attempt-Count": "1",
    "X-Envoy-Decorator-Operation": "echo-server.opendatahub.svc.cluster.local:8443/*",
    "X-Envoy-External-Address": "100.64.0.3",
    "X-Envoy-Peer-Metadata": "ChoKCkNMVVNURVJfSUQSDBoKS3...",
    "X-Envoy-Peer-Metadata-Id": "router~10.129.0.43~data-science-gateway-data-science-gateway-class-8585985cf9rdhpr.openshift-ingress~openshift-ingress.svc.cluster.local",
    "X-Forwarded-Access-Token": "eyJhbGciOiJSUzI1NiIsInR5...",
    "X-Forwarded-For": "100.64.0.3, 10.129.0.43",
    "X-Forwarded-Proto": "https",
    "X-Request-Id": "89b178f9-7282-4408-85a0-ea8c0a302797",
```

Theoretically, in a BYOIDC setup we can get the username from x-auth-request-user and we can get it's member groups from x-auth-request-groups.

I'd like to redesign the dashboard backend code (with as minimal change as possible) to detect those available headers and use the values instead of trying to query the cluster APIs.

## Requirements

1. **Minimal Code Changes**: Modify the dashboard backend with as few changes as possible
2. **Header-Based Authentication**: Use `X-Auth-Request-User` and `X-Auth-Request-Groups` headers when available
3. **Fallback Compatibility**: Maintain existing OpenShift OAuth behavior when headers are not present
4. **User Info Extraction**: Extract username and groups from headers instead of making API calls
5. **Admin Detection**: Determine admin status from group membership in headers
6. **Error Handling**: Graceful fallback when header-based auth fails

## Design Considerations

### Current Authentication Flow Analysis

The current authentication flow in `odh-dashboard` works as follows:

1. **Token Extraction**: Gets access token from `x-forwarded-access-token` header (line 62 in `userUtils.ts`)
2. **User Lookup**: Makes API call to OpenShift's `user.openshift.io/v1/users/~` endpoint (lines 74-80 in `userUtils.ts`)
3. **User Info**: Extracts username and user ID from the OpenShift User resource (lines 100-103 in `userUtils.ts`)
4. **Admin Check**: Uses `isUserAdmin()` function to check admin status via OpenShift API

### Key Files to Modify

- `backend/src/utils/userUtils.ts` - Main user authentication logic
- `backend/src/utils/route-security.ts` - Security and admin checks
- `backend/src/utils/constants.ts` - Header constants

### Header Mapping Strategy

- `X-Auth-Request-User`: Contains user identifier (e.g., `https://keycloak.tannerjc.net/realms/ocp-byoidc-realm#kubeadmin`)
- `X-Auth-Request-Groups`: Contains pipe-separated groups (e.g., `cluster-admins|system:authenticated`)
- `X-Auth-Request-Email`: Contains user email for additional context

### Detection Strategy

Use the presence of `X-Auth-Request-User` header to detect BYOIDC mode vs traditional OpenShift OAuth.

## Implementation Notes

### Solution Plan

#### 1. Create Header-Based User Info Function

Create a new function `getUserInfoFromHeaders()` in `userUtils.ts` that:
- Extracts username from `X-Auth-Request-User` header (extract part after `#`)
- Extracts groups from `X-Auth-Request-Groups` header (pipe-separated)
- Uses `X-Auth-Request-Email` for user ID, fallback to extracted username
- Returns the same format as the existing `getUserInfo()` function
- **Key insight**: kube-rbac-proxy already performs TokenReview and maps OIDC groups to Kubernetes groups

#### 2. Modify getUserInfo() Function

Update the existing `getUserInfo()` function to:
- First check for `X-Auth-Request-User` header presence (BYOIDC detection)
- If present, use `getUserInfoFromHeaders()` with fallback to OpenShift API on error
- If not present, use existing OpenShift API logic
- **Critical**: Always fallback to OpenShift API calls if header-based auth fails
- Maintain the same return type and error handling

#### 3. Update Admin Detection

Modify admin detection logic to:
- Check for admin groups in the `X-Auth-Request-Groups` header
- Look for groups like `cluster-admins`, `system:admin`, etc. (already mapped by kube-rbac-proxy)
- Fall back to existing OpenShift API admin check when headers not available or on error
- **Key insight**: Groups are already properly mapped by kube-rbac-proxy TokenReview

#### 4. Add Constants

Add new constants for BYOIDC headers:
```typescript
export const BYOIDC_USER_HEADER = 'x-auth-request-user';
export const BYOIDC_GROUPS_HEADER = 'x-auth-request-groups';
export const BYOIDC_EMAIL_HEADER = 'x-auth-request-email';
```

Add configuration option for username format:
```typescript
export const BYOIDC_EXTRACT_USERNAME = process.env.BYOIDC_EXTRACT_USERNAME !== 'false'; // default true
```

#### 5. Minimal Changes Approach

- Keep all existing code paths intact
- Add new functions alongside existing ones
- Use feature detection (header presence) rather than configuration flags
- **Always fallback to OpenShift API calls** for maximum compatibility
- Maintain backward compatibility with existing OpenShift deployments
- Auto-detect BYOIDC mode based on `X-Auth-Request-User` header presence

### Implementation Steps

1. Add header constants to `constants.ts`
2. Create `getUserInfoFromHeaders()` function in `userUtils.ts`
3. Modify `getUserInfo()` to use header-based auth when available
4. Update admin detection logic in `route-security.ts`
5. Test with both BYOIDC and traditional OpenShift setups

## Open Questions

1. **Group Mapping**: How should we map external OIDC groups to OpenShift admin groups? Should we look for specific group names like `cluster-admins` or `system:admin`?

Do we know the actual openshift groups and do we need to konw? Given the lack of a group CRD, we can at best query the clusterrolebindings ... 

apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: rosa-admins
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cluster-admin
subjects:
- apiGroup: rbac.authorization.k8s.io
  kind: Group
  name: cluster-admins

We can then do a SAR to see if that user is mapped into those groups then I guess ...

odh-dashboard-568585d48f-z5tqt kube-rbac-proxy I1001 21:33:46.472799       1 round_trippers.go:553] POST https://172.30.0.1:443/apis/authentication.k8s.io/v1/tokenreviews 201 Created in 15 milliseconds
odh-dashboard-568585d48f-z5tqt kube-rbac-proxy I1001 21:33:46.472818       1 round_trippers.go:570] HTTP Statistics: DNSLookup 0 ms Dial 0 ms TLSHandshake 11 ms ServerProcessing 3 ms Duration 15 ms
odh-dashboard-568585d48f-z5tqt kube-rbac-proxy I1001 21:33:46.472826       1 round_trippers.go:577] Response Headers:
odh-dashboard-568585d48f-z5tqt kube-rbac-proxy I1001 21:33:46.472834       1 round_trippers.go:580]     Cache-Control: no-cache, private
odh-dashboard-568585d48f-z5tqt kube-rbac-proxy I1001 21:33:46.472841       1 round_trippers.go:580]     Content-Type: application/json
odh-dashboard-568585d48f-z5tqt kube-rbac-proxy I1001 21:33:46.472845       1 round_trippers.go:580]     Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
odh-dashboard-568585d48f-z5tqt kube-rbac-proxy I1001 21:33:46.472849       1 round_trippers.go:580]     X-Kubernetes-Pf-Flowschema-Uid: f08e2e8d-d91e-45bd-b6de-aeb3d16fa527
odh-dashboard-568585d48f-z5tqt kube-rbac-proxy I1001 21:33:46.472853       1 round_trippers.go:580]     X-Kubernetes-Pf-Prioritylevel-Uid: ac15d824-b8de-4ddc-82df-150bc75028af
odh-dashboard-568585d48f-z5tqt kube-rbac-proxy I1001 21:33:46.472858       1 round_trippers.go:580]     Content-Length: 1836
odh-dashboard-568585d48f-z5tqt kube-rbac-proxy I1001 21:33:46.472863       1 round_trippers.go:580]     Date: Wed, 01 Oct 2025 21:33:46 GMT
odh-dashboard-568585d48f-z5tqt kube-rbac-proxy I1001 21:33:46.472868       1 round_trippers.go:580]     Audit-Id: b7bf4abb-0734-4209-a741-d515b44d487d
odh-dashboard-568585d48f-z5tqt kube-rbac-proxy I1001 21:33:46.472899       1 request.go:1351] Response Body: {"kind":"TokenReview","apiVersion":"authentication.k8s.io/v1","metadata":{"creationTimestamp":null,"managedFields":[{"manager":"kube-rbac-proxy","operation":"Update","apiVersion":"authentication.k8s.io/v1","time":"2025-10-01T21:33:46Z","fieldsType":"FieldsV1","fieldsV1":{"f:spec":{"f:token":{}}}}]},"spec":{"token":"eyJhbG..."},"status":{"authenticated":true,"user":{"username":"https://keycloak.tannerjc.net/realms/ocp-byoidc-realm#kubeadmin","groups":["cluster-admins","system:authenticated"],"extra":{"authentication.kubernetes.io/credential-id":["JTI=onrtac:616d2555-9166-4700-b2b2-1aa14a5bd67e"]}},"audiences":["https://rh-oidc.s3.us-east-1.amazonaws.com/23c734st3pn7l167mq97d0ot8848lgrl"]}}

However, the kube-rbac-proxy sidecar is already doing that before the request makes it to the dashboard code.

2. **Username Format**: ✅ **RESOLVED** - Extract the username part after the `#` (e.g., `kubeadmin` from `https://keycloak.tannerjc.net/realms/ocp-byoidc-realm#kubeadmin`). Add a configuration option to use the full identifier if needed. The dashboard has a feature flag system that could be extended for this.

3. **User ID Mapping**: The current code looks for `toolchain.dev.openshift.com/sso-user-id` annotation. For BYOIDC, we should use the email from `X-Auth-Request-Email` header as the user ID, or fall back to the extracted username if email is not available.

4. **Error Handling**: ✅ **RESOLVED** - **DEFINITELY fallback to OpenShift API calls** if BYOIDC headers are present but malformed. This ensures maximum compatibility and graceful degradation.

5. **Testing Strategy**: ✅ **RESOLVED** - User will test the implementation in both BYOIDC and traditional OpenShift environments to ensure compatibility.

6. **Configuration**: ✅ **RESOLVED** - **Auto-detect based on incoming headers**. Use the presence of `X-Auth-Request-User` header to determine BYOIDC mode, with fallback to traditional OpenShift OAuth when headers are not present.
