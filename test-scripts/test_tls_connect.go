package main

import (
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"fmt"
	"io/ioutil"
	"net/http"
	"os"
	"time"
)

const (
	serviceAccountCAPath = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
	kubernetesAPIURL     = "https://kubernetes.default.svc:443/.well-known/oauth-authorization-server"
	timeout             = 10 * time.Second
)

type OAuthDiscovery struct {
	Issuer                string `json:"issuer"`
	AuthorizationEndpoint string `json:"authorization_endpoint"`
	TokenEndpoint         string `json:"token_endpoint"`
}

func main() {
	fmt.Println("=== TLS Connection Test (Simulating kube-auth-proxy behavior) ===")
	fmt.Println()

	// Auto-discover OAuth URL from Kubernetes API (just like kube-auth-proxy does)
	oauthURL, err := discoverOAuthURL()
	if err != nil {
		fmt.Printf("❌ FAIL: OAuth discovery failed: %v\n", err)
		os.Exit(1)
	}

	fmt.Printf("✅ Auto-discovered OAuth Token URL: %s\n\n", oauthURL)

	// Test 1: Service Account CA only (default kube-auth-proxy behavior)
	fmt.Println("--- Test 1: Service Account CA Only ---")
	fmt.Println("(This simulates default kube-auth-proxy OpenShift provider behavior)")
	testWithServiceAccountCA(oauthURL)

	fmt.Println()

	// Test 2: System Trust Store + Service Account CA (--use-system-trust-store=true)
	fmt.Println("--- Test 2: System Trust Store + Service Account CA ---")
	fmt.Println("(This simulates kube-auth-proxy with --use-system-trust-store=true)")
	testWithSystemTrustStore(oauthURL)

	fmt.Println()

	// Test 3: System Trust Store Only (for comparison)
	fmt.Println("--- Test 3: System Trust Store Only ---")
	fmt.Println("(This simulates curl without --cacert flag)")
	testWithSystemOnly(oauthURL)
}

func testWithServiceAccountCA(url string) {
	// Load service account CA
	caPEM, err := ioutil.ReadFile(serviceAccountCAPath)
	if err != nil {
		fmt.Printf("❌ FAIL: Cannot read service account CA: %v\n", err)
		return
	}

	// Create cert pool with only service account CA
	certPool := x509.NewCertPool()
	if !certPool.AppendCertsFromPEM(caPEM) {
		fmt.Printf("❌ FAIL: Cannot parse service account CA\n")
		return
	}

	// Create HTTP client
	client := &http.Client{
		Timeout: timeout,
		Transport: &http.Transport{
			TLSClientConfig: &tls.Config{
				RootCAs:    certPool,
				MinVersion: tls.VersionTLS12,
			},
		},
	}

	// Attempt connection
	resp, err := client.Get(url)
	if err != nil {
		fmt.Printf("❌ FAIL: %v\n", err)
		fmt.Println("   → TLS validation failed with service account CA only")
		return
	}
	defer resp.Body.Close()

	fmt.Printf("✅ SUCCESS: HTTP %d\n", resp.StatusCode)
	fmt.Println("   → TLS validation succeeded (certificate trusted via service account CA)")
}

func testWithSystemTrustStore(url string) {
	// Load system cert pool first
	certPool, err := x509.SystemCertPool()
	if err != nil {
		fmt.Printf("⚠️  WARNING: Cannot load system cert pool: %v\n", err)
		certPool = x509.NewCertPool()
	}

	// Add service account CA on top
	caPEM, err := ioutil.ReadFile(serviceAccountCAPath)
	if err != nil {
		fmt.Printf("❌ FAIL: Cannot read service account CA: %v\n", err)
		return
	}

	if !certPool.AppendCertsFromPEM(caPEM) {
		fmt.Printf("⚠️  WARNING: Cannot parse service account CA\n")
	}

	// Create HTTP client
	client := &http.Client{
		Timeout: timeout,
		Transport: &http.Transport{
			TLSClientConfig: &tls.Config{
				RootCAs:    certPool,
				MinVersion: tls.VersionTLS12,
			},
		},
	}

	// Attempt connection
	resp, err := client.Get(url)
	if err != nil {
		fmt.Printf("❌ FAIL: %v\n", err)
		fmt.Println("   → TLS validation failed even with system trust store")
		return
	}
	defer resp.Body.Close()

	fmt.Printf("✅ SUCCESS: HTTP %d\n", resp.StatusCode)
	fmt.Println("   → TLS validation succeeded (system CAs + service account CA)")
}

func testWithSystemOnly(url string) {
	// Use system cert pool only
	certPool, err := x509.SystemCertPool()
	if err != nil {
		fmt.Printf("❌ FAIL: Cannot load system cert pool: %v\n", err)
		return
	}

	// Create HTTP client
	client := &http.Client{
		Timeout: timeout,
		Transport: &http.Transport{
			TLSClientConfig: &tls.Config{
				RootCAs:    certPool,
				MinVersion: tls.VersionTLS12,
			},
		},
	}

	// Attempt connection
	resp, err := client.Get(url)
	if err != nil {
		fmt.Printf("❌ FAIL: %v\n", err)
		fmt.Println("   → TLS validation failed with system trust store only")
		return
	}
	defer resp.Body.Close()

	fmt.Printf("✅ SUCCESS: HTTP %d\n", resp.StatusCode)
	fmt.Println("   → TLS validation succeeded (system CAs only)")
}

func discoverOAuthURL() (string, error) {
	fmt.Println("--- OAuth Discovery from Kubernetes API ---")
	fmt.Printf("Discovery URL: %s\n", kubernetesAPIURL)
	
	// Load service account CA for talking to Kubernetes API
	caPEM, err := ioutil.ReadFile(serviceAccountCAPath)
	if err != nil {
		return "", fmt.Errorf("cannot read service account CA: %v", err)
	}

	certPool := x509.NewCertPool()
	if !certPool.AppendCertsFromPEM(caPEM) {
		return "", fmt.Errorf("cannot parse service account CA")
	}

	// Load service account token
	tokenBytes, err := ioutil.ReadFile("/var/run/secrets/kubernetes.io/serviceaccount/token")
	if err != nil {
		return "", fmt.Errorf("cannot read service account token: %v", err)
	}
	token := string(tokenBytes)

	// Create HTTP client for Kubernetes API
	client := &http.Client{
		Timeout: timeout,
		Transport: &http.Transport{
			TLSClientConfig: &tls.Config{
				RootCAs:    certPool,
				MinVersion: tls.VersionTLS12,
			},
		},
	}

	// Make discovery request
	req, err := http.NewRequest("GET", kubernetesAPIURL, nil)
	if err != nil {
		return "", fmt.Errorf("cannot create request: %v", err)
	}
	req.Header.Set("Authorization", "Bearer "+token)

	resp, err := client.Do(req)
	if err != nil {
		return "", fmt.Errorf("discovery request failed: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("discovery returned HTTP %d", resp.StatusCode)
	}

	// Parse discovery response
	body, err := ioutil.ReadAll(resp.Body)
	if err != nil {
		return "", fmt.Errorf("cannot read discovery response: %v", err)
	}

	var discovery OAuthDiscovery
	if err := json.Unmarshal(body, &discovery); err != nil {
		return "", fmt.Errorf("cannot parse discovery response: %v", err)
	}

	if discovery.TokenEndpoint == "" {
		return "", fmt.Errorf("no token_endpoint in discovery response")
	}

	fmt.Printf("✅ Discovery successful\n")
	fmt.Printf("   Issuer: %s\n", discovery.Issuer)
	fmt.Printf("   Token Endpoint: %s\n", discovery.TokenEndpoint)

	return discovery.TokenEndpoint, nil
}
