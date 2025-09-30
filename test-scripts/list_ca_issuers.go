package main

import (
	"crypto/x509"
	"encoding/pem"
	"fmt"
	"os"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Println("Usage: go run list_ca_issuers.go <ca-bundle-file>")
		fmt.Println("Example: go run list_ca_issuers.go /tmp/ca.crt")
		os.Exit(1)
	}

	caFile := os.Args[1]
	
	// Read the CA bundle file
	caData, err := os.ReadFile(caFile)
	if err != nil {
		fmt.Printf("Error reading file: %v\n", err)
		os.Exit(1)
	}

	fmt.Println("=== Certificates in CA Bundle ===\n")
	
	count := 0
	rest := caData
	
	// Parse all PEM blocks
	for {
		var block *pem.Block
		block, rest = pem.Decode(rest)
		if block == nil {
			break
		}
		
		if block.Type != "CERTIFICATE" {
			continue
		}
		
		// Parse the certificate
		cert, err := x509.ParseCertificate(block.Bytes)
		if err != nil {
			fmt.Printf("Error parsing certificate: %v\n", err)
			continue
		}
		
		count++
		fmt.Printf("Certificate #%d:\n", count)
		fmt.Printf("  Subject: %s\n", cert.Subject.String())
		fmt.Printf("  Issuer:  %s\n", cert.Issuer.String())
		
		// Check for Let's Encrypt
		issuerStr := cert.Issuer.String()
		if contains(issuerStr, "Let's Encrypt") || 
		   contains(issuerStr, "ISRG") ||
		   contains(cert.Issuer.CommonName, "R3") ||
		   contains(cert.Issuer.CommonName, "R10") ||
		   contains(cert.Issuer.CommonName, "R11") ||
		   contains(cert.Issuer.CommonName, "E1") ||
		   contains(cert.Issuer.CommonName, "E2") {
			fmt.Printf("  ⭐ Let's Encrypt certificate detected!\n")
		}
		
		fmt.Println()
	}
	
	fmt.Printf("Total certificates: %d\n", count)
}

func contains(s, substr string) bool {
	return len(s) >= len(substr) && 
	       (s == substr || len(s) > len(substr) && 
	        (hasSubstring(s, substr)))
}

func hasSubstring(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}
