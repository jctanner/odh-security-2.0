# ODH Gateway Controller Design Document

This document outlines the design for a new "gateway controller" for the `opendatahub-operator`. This controller will manage the ingress architecture for Open Data Hub (ODH), transitioning from multiple OpenShift Routes to a single, centralized Ingress Gateway using the Kubernetes Gateway API.

The controller will enforce authentication at the gateway level and streamline the exposure of ODH services.

## 1. Requirements

### 1.1. Functional Requirements

| ID      | Description                                                                                                                                                             |
| :------ | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| FR-001  | The controller MUST create and manage a `GatewayClass` resource named `odh-gateway-class` using the `openshift.io/gateway-controller/v1` controller.                      |
| FR-002  | The controller MUST create and manage a `Gateway` resource named `odh-gateway` in the `openshift-ingress` namespace.                                                    |
| FR-003  | The gateway MUST listen on port 443 and terminate TLS traffic.                                                                                                          |
| FR-004  | The gateway MUST support hostname routing for services within the ODH deployment.                                                                                       |
| FR-005  | The gateway controller MUST enforce authentication at the gateway level using envoy's `ext_authz` filter and `kube-auth-proxy`.                                           |
| FR-006  | The controller MUST support two authentication modes for `kube-auth-proxy`: OpenShift OAuth and OIDC.                                                                   |
| FR-007  | In OpenShift OAuth mode, the controller MUST automatically configure `kube-auth-proxy`'s client and client secret.                                                      |
| FR-008  | In OIDC mode, the controller MUST allow administrators to provide an issuer URL, client ID, and client secret via a Secret.                                            |
| FR-009  | The controller MUST be able to determine the cluster's authentication configuration (OpenShift OAuth vs. OIDC) or allow explicit configuration in the `DSCI` spec.      |
| FR-010  | The controller MUST support TLS certificate management using `cert-manager` for automatic certificate generation.                                                       |
| FR-011  | The controller MUST allow administrators to provide their own TLS certificate bundle via a Secret.                                                                      |
| FR-012  | All services currently exposed via OpenShift Routes (e.g., Prometheus, Alertmanager, KServe) MUST be migrated to use `HTTPRoutes` parented to the central `Gateway`.     |
| FR-013  | The `oauth-proxy` sidecar in existing component deployments MUST be replaced with a `kube-rbac-proxy` sidecar.                                                            |
| FR-014  | The controller MUST normalize the auth token header to `x-forwarded-token` for downstream services.                                                                     |
| FR-015  | The controller SHOULD provide an `x-forwarded-user` header.                                                                                                             |
| FR-016  | The `kube-auth-proxy` service MUST expose its `ext_authz` endpoint over a secure TLS connection.                                                                          |

### 1.2. Non-Functional Requirements

| ID       | Description                                                                                                                                      |
| :------- | :----------------------------------------------------------------------------------------------------------------------------------------------- |
| NFR-001  | The gateway controller and its components MUST be highly available.                                                                              |
| NFR-002  | The gateway architecture MUST be scalable to handle a large number of services and high traffic volumes.                                         |
| NFR-003  | The controller MUST be designed to be extensible for future enhancements.                                                                        |
| NFR-004  | The `kube-auth-proxy` image version MUST be configurable to allow pinning to a specific SHA digest for security.                                   |
| NFR-005  | The controller's actions MUST be idempotent.                                                                                                     |

## 2. Architecture

```mermaid
graph TD;
    A["main() [cmd/main.go]"] --> B{"ctrl.NewManager"};
    A --> C["initServices()"];
    C --> D["sr.ForEach(handler)"];
    subgraph "Service Controllers";
        direction LR;
        E["_ [internal/controller/services/auth]"];
        F["_ [internal/controller/services/monitoring]"];
        G["_ [/gateway]"];
    end;
    D -- "runs init() on import" --> G;
    A --> H["CreateServiceReconcilers()"];
    H --> I["sr.ForEach(handler)"];
    I --> J{"handler.NewReconciler(mgr)"};
    J -- "registers with manager" --> B;
    B --> K["mgr.Start()"];
```

The new gateway controller will be located in `internal/controller/services/gateway` within the `opendatahub-operator` repository, aligning with the existing project structure.

### 2.1. Components

1.  **Gateway CRD:** A new `Gateway` Custom Resource Definition will be introduced under the `services.platform.opendatahub.io` API group. This CRD will serve as the top-level configuration for the ODH gateway, specifying details such as the domain and certificate management strategy. The POC patch (`src/poc-patch.diff`) provides a strong starting point for this CRD.

2.  **Gateway Controller:** The core reconciler that watches the `Gateway` CR and manages the lifecycle of associated Kubernetes resources, including:
    *   `gateway.networking.k8s.io/v1.GatewayClass`
    *   `gateway.networking.k8s.io/v1.Gateway`
    *   `cert-manager.io/v1.Certificate` (if `cert-manager` is used)
    *   `core/v1.Secret` for TLS certificates.

3.  **Authentication Layer:**
    *   **`kube-auth-proxy`:** Deployed as a central service, it will handle the `ext_authz` check from the Envoy-based gateway.
    *   **TLS Security:** The `kube-auth-proxy` service will expose its `ext_authz` endpoint over TLS. This will be secured using OpenShift's serving certificate feature. The controller will add the `service.beta.openshift.io/serving-cert-secret-name` annotation to the `kube-auth-proxy` `Service`. The OpenShift service CA operator will then automatically generate a secret containing a signed TLS certificate and key, which will be mounted into the `kube-auth-proxy` pod.
    *   **Configuration:** The controller will manage the configuration of `kube-auth-proxy` based on the cluster's auth mode (OpenShift OAuth or OIDC).

### 2.2. Authentication Flow

1.  A user attempts to access an ODH service endpoint.
2.  The request hits the central `Gateway`.
3.  The `Gateway`'s underlying Envoy proxy forwards the request to the `ext_authz` filter, which calls `kube-auth-proxy`.
4.  `kube-auth-proxy` performs authentication against either the OpenShift OAuth server or the configured external OIDC provider.
5.  If authentication is successful, `kube-auth-proxy` returns a `200 OK`. The request is then proxied to the upstream service. `kube-auth-proxy` will add the `x-forwarded-token` and `x-forwarded-user` headers.
6.  If authentication fails, `kube-auth-proxy` returns a `401 Unauthorized`, and the user is denied access.

### 2.3. Identifying Cluster Authentication Mode

Determining whether the cluster uses the internal OpenShift OAuth server or an external OIDC provider is critical.

*   **SPIKE:** A research spike is required to determine the most reliable method for detecting the cluster's authentication configuration. This may involve inspecting the cluster `authentication.config.openshift.io` resource or the status of the internal OAuth server.
*   **Fallback:** As a fallback, we will add a field to the `DSCInitialization` spec (`spec.auth.mode`) to allow administrators to explicitly set the mode to `openshift` or `oidc`.

## 3. Implementation Roadmap

This project will be implemented in phases to allow for iterative development and testing.

### Phase 1: Core Gateway Controller

1.  **Task 1.1:** Finalize and merge the `Gateway` CRD definition based on the POC patch.
2.  **Task 1.2:** Implement the basic gateway controller in `internal/controller/services/gateway`. This controller will create the `GatewayClass` and `Gateway` resources.
3.  **Task 1.3:** Implement TLS certificate management, supporting both `cert-manager` and user-provided secrets. The logic from the POC patch can be adapted for this.

### Phase 2: Authentication Integration

1.  **Task 2.1:** Implement the logic to deploy and configure `kube-auth-proxy` as a central service. This includes creating its `Deployment` and `Service`, and configuring the `Service` with the necessary annotations (`service.beta.openshift.io/serving-cert-secret-name`) to enable automatic TLS serving certificates.
2.  **Task 2.2:** Add logic to the gateway controller to configure the `Gateway` with the `ext_authz` filter pointing to `kube-auth-proxy`.
3.  **Task 2.3:** Implement the OpenShift OAuth integration for `kube-auth-proxy`.
4.  **Task 2.4:** Implement the OIDC integration, allowing configuration via a Secret.
5.  **Task 2.5:** Complete the research spike for detecting the cluster's auth mode and implement the detection logic or the explicit DSCI configuration.

### Phase 3: Component Migration

1.  **Task 3.1:** For each component currently using an OpenShift `Route` and `oauth-proxy` (e.g., KServe, Prometheus), create a separate PR to:
    *   Remove the `Route` creation logic.
    *   Create a `HTTPRoute` that attaches to the central `odh-gateway`.
    *   Replace the `oauth-proxy` sidecar with a `kube-rbac-proxy` sidecar for service-level authorization.
2.  **Task 3.2:** Update any relevant webhooks that might be affected by the move from `Route` objects to `HTTPRoute` objects.

## 4. Test Plan

### 4.1. Unit Tests

*   Each controller action (e.g., `createCertificateResources`, `initialize`) will have corresponding unit tests.
*   The logic for determining auth mode will be unit tested.
*   Reconciliation logic will be tested using a fake client.

### 4.2. E2E Tests

*   **Scenario 1: OpenShift OAuth Mode**
    *   Deploy the operator on a standard OpenShift cluster.
    *   Verify the `Gateway` is created and configured correctly.
    *   Verify that accessing a protected service redirects to the OpenShift login page.
    *   Verify successful login grants access.
*   **Scenario 2: OIDC Mode**
    *   Configure the cluster with an external OIDC provider.
    *   Provide the OIDC client secret to the operator.
    *   Verify the `Gateway` is configured for OIDC.
    *   Verify that accessing a protected service redirects to the external IDP.
*   **Scenario 3: Certificate Management**
    *   Test the `cert-manager` integration by deploying it and verifying a certificate is issued.
    *   Test the user-provided certificate functionality by creating a secret and verifying the gateway uses it.
*   **Scenario 4: Component Migration**
    *   For each migrated component, verify that its `HTTPRoute` is created and that it is accessible through the gateway.

## 5. Open Questions & Research Spikes

*   **SPIKE-001:** Determine the best method to automatically detect the cluster's authentication configuration (OpenShift OAuth vs. OIDC).
*   **Question-001:** What is the best practice for coordinating the `kube-auth-proxy` image version with the devops team to allow for pinning?
*   **Question-002:** Does `kube-auth-proxy` provide the necessary information to create an `x-forwarded-user` header?

---
*This document is based on the initial pre-design, analysis of the `opendatahub-operator` source code, the POC patch provided in `src/poc-patch.diff`, and the official OpenShift Gateway API documentation.*