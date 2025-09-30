package main

import (
	"crypto/x509"
	"encoding/pem"
	"fmt"
	"os"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Println("Usage: go run verify_root_ca.go <ca-bundle-file>")
		fmt.Println("This tool verifies if ISRG Root X1 (Let's Encrypt root) is present as a trusted root")
		os.Exit(1)
	}

	caFile := os.Args[1]
	
	// Read the CA bundle file
	caData, err := os.ReadFile(caFile)
	if err != nil {
		fmt.Printf("Error reading file: %v\n", err)
		os.Exit(1)
	}

	fmt.Println("=== Verifying Certificate Trust Chain ===\n")
	
	// Track what we find
	foundISRGRoot := false
	foundR13Intermediate := false
	var r13Cert *x509.Certificate
	
	rest := caData
	certCount := 0
	
	// Parse all certificates
	for {
		var block *pem.Block
		block, rest = pem.Decode(rest)
		if block == nil {
			break
		}
		
		if block.Type != "CERTIFICATE" {
			continue
		}
		
		cert, err := x509.ParseCertificate(block.Bytes)
		if err != nil {
			fmt.Printf("Error parsing certificate: %v\n", err)
			continue
		}
		
		certCount++
		
		// Check if this is ISRG Root X1
		if cert.Subject.CommonName == "ISRG Root X1" {
			fmt.Printf("✅ Found ISRG Root X1 (Certificate #%d)\n", certCount)
			fmt.Printf("   Subject: %s\n", cert.Subject.String())
			fmt.Printf("   Issuer:  %s\n", cert.Issuer.String())
			
			// Check if it's self-signed (root certificate)
			if cert.Subject.String() == cert.Issuer.String() {
				fmt.Printf("   ✅ Self-signed: YES (this is a ROOT certificate)\n")
				foundISRGRoot = true
			} else {
				fmt.Printf("   ⚠️  Self-signed: NO (not a root)\n")
			}
			fmt.Println()
		}
		
		// Check if this is a Let's Encrypt intermediate (R3, R10, R11, R12, R13, E1, E2, etc.)
		if cert.Subject.Organization != nil && 
		   len(cert.Subject.Organization) > 0 && cert.Subject.Organization[0] == "Let's Encrypt" &&
		   cert.Issuer.CommonName == "ISRG Root X1" {
			fmt.Printf("✅ Found Let's Encrypt Intermediate %s (Certificate #%d)\n", cert.Subject.CommonName, certCount)
			fmt.Printf("   Subject: %s\n", cert.Subject.String())
			fmt.Printf("   Issuer:  %s\n", cert.Issuer.String())
			fmt.Printf("   ✅ Signed by: ISRG Root X1\n")
			foundR13Intermediate = true
			r13Cert = cert
			fmt.Println()
		}
	}
	
	fmt.Printf("Total certificates in bundle: %d\n\n", certCount)
	
	// Analysis
	fmt.Println("=== Trust Chain Analysis ===\n")
	
	if foundR13Intermediate && !foundISRGRoot {
		fmt.Println("❌ PROBLEM DETECTED:")
		fmt.Println("   • Let's Encrypt intermediate certificate IS present")
		fmt.Println("   • Let's Encrypt intermediate is signed by ISRG Root X1")
		fmt.Println("   • ISRG Root X1 root certificate is NOT present")
		fmt.Println()
		fmt.Println("This means:")
		fmt.Println("   • The bundle references ISRG Root X1 as an issuer")
		fmt.Println("   • But the actual ISRG Root X1 root CA is missing")
		fmt.Println("   • TLS validation will FAIL for certs signed by Let's Encrypt")
		fmt.Println()
		fmt.Println("Solution: Use --use-system-trust-store=true to include")
		fmt.Println("          ISRG Root X1 from the system trust store")
		
	} else if foundR13Intermediate && foundISRGRoot {
		fmt.Println("✅ TRUST CHAIN COMPLETE:")
		fmt.Println("   • R13 intermediate certificate IS present")
		fmt.Println("   • ISRG Root X1 root certificate IS present")
		fmt.Println("   • TLS validation should work for Let's Encrypt certificates")
		
	} else if !foundR13Intermediate && !foundISRGRoot {
		fmt.Println("ℹ️  NO LET'S ENCRYPT CERTIFICATES:")
		fmt.Println("   • Neither R13 nor ISRG Root X1 found")
		fmt.Println("   • This bundle uses different CAs (likely internal only)")
		fmt.Println("   • For managed clusters with Let's Encrypt OAuth routes,")
		fmt.Println("     use --use-system-trust-store=true")
	}
	fmt.Println()
	
	// Show what's actually needed for validation
	if foundR13Intermediate && r13Cert != nil {
		fmt.Println("=== To Validate an OAuth Cert Signed by R13 ===")
		fmt.Println()
		fmt.Println("Certificate chain needed:")
		fmt.Println("  1. OAuth Server Cert (e.g., *.example.com)")
		fmt.Println("     └─ signed by: R13")
		fmt.Printf("  2. R13 Intermediate (%s in bundle)\n", checkMark(foundR13Intermediate))
		fmt.Println("     └─ signed by: ISRG Root X1")
		fmt.Printf("  3. ISRG Root X1 Root (%s in bundle)\n", checkMark(foundISRGRoot))
		fmt.Println("     └─ self-signed (root)")
		fmt.Println()
		
		if !foundISRGRoot {
			fmt.Println("❌ Chain is INCOMPLETE - missing step 3!")
		} else {
			fmt.Println("✅ Chain is COMPLETE")
		}
	}
}

func checkMark(present bool) string {
	if present {
		return "✅ PRESENT"
	}
	return "❌ MISSING"
}
