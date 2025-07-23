#!/usr/bin/env python3
"""
OpenDataHub Gateway API Migration Tool

This is a comprehensive project management tool for the OpenDataHub Gateway API
migration project. It provides an integrated workflow for repository management,
build orchestration, and development environment setup.

Key Features:
- GitHub operations: forking, cloning, branch management
- Project configuration management via YAML
- Automated repository setup with upstream configuration
- Multi-repository batch operations
- Secure token management from .github_token file
- Command execution with error handling and logging
- Workflow-based build and deployment automation

Core Workflows:
- Repository setup: fork, clone, rebase, branch creation
- Batch operations across manifest dependencies and additional repositories
- Configuration-driven development environment management
- YAML-based workflow execution for build/deploy operations

Usage Context:
This tool is designed for the odh-security-2.0 project where multiple
opendatahub-io repositories need to be forked, cloned, and patched for
Gateway API migration. Repository dependencies are discovered from
get_all_manifests.sh, with additional repositories configurable in config.yaml.
All repository checkouts are managed in the src/ directory structure to keep
the main project clean.

Security:
- GitHub token is read from .github_token file (not committed to git)
- Token is set as GITHUB_TOKEN environment variable for gh CLI
- No token values are logged or exposed in output

Dependencies:
- GitHub CLI ('gh') must be installed and available in PATH
- Python 3.6+ for subprocess and pathlib support
- PyYAML for configuration file parsing
- .github_token file must exist with valid GitHub token
- config.yaml file must exist with project configuration

Author: Generated for OpenDataHub Security 2.0 Migration Project
License: Project-specific usage
"""

import os
import sys
import subprocess
import logging
import argparse
import time
import yaml
from pathlib import Path
from typing import List, Optional, Dict, Any

# Add lib directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "lib"))

# Import from lib directory
from github_wrapper import GitHubWrapper, RepoInfo
from ansible_engine import AnsibleEngine


def cmd_whoami(args):
    """Handle whoami subcommand"""
    try:
        gh = GitHubWrapper()
        user_data = gh.whoami()

        print(f"Authenticated as: {user_data['login']}")
        print(f"Name: {user_data['name']}")
        print(f"Email: {user_data.get('email', 'Not public')}")
        print(f"Profile: {user_data.get('html_url', 'N/A')}")

        return 0

    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        return 1


def cmd_list_repos(args):
    """Handle list-repos subcommand"""
    try:
        gh = GitHubWrapper()
        repos = gh.list_repositories(args.owner, args.limit)

        print(f"Repositories for {args.owner}:")
        for repo in repos:
            privacy = "🔒" if repo.get("isPrivate", False) else "🌐"
            print(f"  {privacy} {repo['name']} - {repo.get('url', 'N/A')}")

        return 0

    except Exception as e:
        print(f"❌ Error listing repositories: {e}")
        return 1


def cmd_fork_repo(args):
    """Handle fork-repo subcommand"""
    try:
        gh = GitHubWrapper()

        # Fork the repository
        print(f"🔄 Forking {args.repository}...")
        fork_result = gh.fork_repository(args.repository)

        if fork_result["created"]:
            print(f"✅ Fork created: {fork_result['fork_url']}")
        else:
            print(f"ℹ️  Fork already exists: {fork_result['fork_url']}")

        # Clone if requested
        if args.clone:
            print(f"🔄 Cloning fork...")
            clone_result = gh.clone_repository(args.repository)

            if clone_result["cloned"]:
                print(f"✅ Repository cloned to: {clone_result['local_path']}")
            else:
                print(f"ℹ️  Repository already exists at: {clone_result['local_path']}")

        return 0

    except Exception as e:
        print(f"❌ Error forking repository: {e}")
        return 1


def cmd_clone_repo(args):
    """Handle clone-repo subcommand"""
    try:
        gh = GitHubWrapper()

        print(f"🔄 Cloning {args.repository}...")
        result = gh.clone_repository(args.repository)

        if result["cloned"]:
            print(f"✅ Repository cloned to: {result['local_path']}")
        else:
            print(f"ℹ️  Repository already exists at: {result['local_path']}")

        return 0

    except Exception as e:
        print(f"❌ Error cloning repository: {e}")
        return 1


def cmd_clone_forks(args):
    """Handle clone-forks subcommand - clone all fork repositories"""
    try:
        gh = GitHubWrapper()
        
        print("🔄 Cloning all fork repositories...")
        
        # Step 1: Ensure opendatahub-operator is available for dependency parsing
        operator_repo = "opendatahub-io/opendatahub-operator"
        operator_local_path = gh.src_dir / "opendatahub-operator"
        fork_org = gh.get_fork_org()
        operator_fork_url = f"{fork_org}/opendatahub-operator"
        
        if not operator_local_path.exists():
            print(f"📋 First setting up {operator_repo} (required for manifest parsing)...")
            try:
                print(f"  🔄 Cloning fork...")
                result = gh.clone_repository(operator_fork_url)
                if result["cloned"]:
                    print(f"    ✅ Repository cloned to: {result['local_path']}")
                else:
                    print(f"    ℹ️  Repository already exists at: {result['local_path']}")
                
                # Setup upstream and feature branch for operator too
                print(f"  🔄 Setting up upstream and rebasing...")
                repo_path = Path(result["local_path"])
                upstream_url = f"https://github.com/{operator_repo}"
                gh.setup_upstream(repo_path, upstream_url)
                
                print(f"  🔄 Setting up feature branch...")
                feature_branch = gh.get_branch_name()
                base_branch = "main"  # opendatahub-operator uses main branch
                
                if not gh.branch_exists(repo_path, feature_branch):
                    print(f"    🆕 Creating feature branch '{feature_branch}'...")
                    gh.create_branch(repo_path, feature_branch, base_branch)
                else:
                    print(f"    ✅ Feature branch '{feature_branch}' already exists, updating from origin...")
                    # Fetch latest from origin and checkout with tracking
                    gh._run_command(["git", "fetch", "origin"], cwd=repo_path)
                    gh._run_command(["git", "checkout", "--track", f"origin/{feature_branch}"], cwd=repo_path)
                
                print(f"    ✅ Operator setup complete!")
                
            except Exception as e:
                print(f"❌ Error setting up operator repository: {e}")
                print("🔍 This repository is required to parse manifest dependencies")
                return 1
        else:
            print(f"✅ Operator repository already available at: {operator_local_path}")
            # Ensure we're on the feature branch if the repo already exists
            try:
                feature_branch = gh.get_branch_name()
                if gh.branch_exists(operator_local_path, feature_branch):
                    print(f"    🔄 Updating feature branch '{feature_branch}' from origin...")
                    gh._run_command(["git", "fetch", "origin"], cwd=operator_local_path)
                    gh._run_command(["git", "checkout", "--track", f"origin/{feature_branch}"], cwd=operator_local_path)
            except Exception as e:
                print(f"    ⚠️  Could not checkout feature branch: {e}")
        
        # Step 2: Parse manifest repositories from get_all_manifests.sh
        try:
            print("📋 Parsing manifest dependencies...")
            manifest_repos = gh.parse_manifest_repositories()
            print(f"📋 Found {len(manifest_repos)} repositories in manifest dependencies")
        except Exception as e:
            print(f"❌ Error parsing manifest repositories: {e}")
            return 1
        
        # Get additional repositories from config
        additional_repos = gh.get_additional_repositories()
        print(f"📋 Found {len(additional_repos)} additional repositories in configuration")
        
        if args.dry_run:
            print("\n🔍 DRY RUN - Would clone the following repositories:")
            fork_org = gh.get_fork_org()
            
            print("  📦 Manifest Dependencies:")
            for repo_name, base_branch in manifest_repos.items():
                fork_url = f"{fork_org}/{repo_name}"
                local_path = gh.src_dir / repo_name
                status = "exists" if local_path.exists() else "would clone"
                print(f"    • {fork_url} (base: {base_branch}) - {status}")
            
            print("\n  ➕ Additional Repositories:")
            for repo_url in additional_repos:
                repo_name = repo_url.split("/")[-1]
                fork_url = f"{fork_org}/{repo_name}"
                local_path = gh.src_dir / repo_name
                status = "exists" if local_path.exists() else "would clone"
                # For additional repos, default branch will be detected at runtime
                print(f"    • {fork_url} (base: auto-detect) - {status}")
            
            return 0
        
        # Step 3: Clone all repositories and set them up
        fork_org = gh.get_fork_org()
        results = []
        processed = 0
        skipped = 0
        
        # Process manifest repositories
        print(f"\n📦 Processing manifest dependencies ({len(manifest_repos)} repositories):")
        for repo_name, base_branch in manifest_repos.items():
            # Skip opendatahub-operator since we already handled it in Step 1
            if repo_name == "opendatahub-operator":
                print(f"⏭️  Skipping {repo_name} (already processed in Step 1)")
                skipped += 1
                continue
                
            fork_url = f"{fork_org}/{repo_name}"
            original_repo = f"opendatahub-io/{repo_name}"
            local_path = gh.src_dir / repo_name
            
            # Skip if local checkout exists and --skip-existing is set
            if local_path.exists() and args.skip_existing:
                print(f"⏭️  Skipping {fork_url} (local checkout exists)")
                skipped += 1
                continue
            
            try:
                print(f"\n📂 Processing {fork_url}...")
                processed += 1
                
                # Step 3a: Clone fork
                print(f"  🔄 Cloning fork...")
                result = gh.clone_repository(fork_url)
                
                if result["cloned"]:
                    print(f"    ✅ Repository cloned to: {result['local_path']}")
                else:
                    print(f"    ℹ️  Repository already exists at: {result['local_path']}")
                
                # Step 3b: Setup upstream and rebase
                print(f"  🔄 Setting up upstream and rebasing...")
                repo_path = Path(result["local_path"])
                upstream_url = f"https://github.com/{original_repo}"
                gh.setup_upstream(repo_path, upstream_url)
                
                # Step 3c: Create or checkout feature branch
                print(f"  🔄 Setting up feature branch...")
                feature_branch = gh.get_branch_name()
                
                if not gh.branch_exists(repo_path, feature_branch):
                    print(f"    🆕 Creating feature branch '{feature_branch}'...")
                    gh.create_branch(repo_path, feature_branch, base_branch)
                else:
                    print(f"    ✅ Feature branch '{feature_branch}' already exists, updating from origin...")
                    # Fetch latest from origin and checkout with tracking
                    gh._run_command(["git", "fetch", "origin"], cwd=repo_path)
                    gh._run_command(["git", "checkout", "--track", f"origin/{feature_branch}"], cwd=repo_path)
                
                print(f"    ✅ Setup complete for {fork_url}")
                results.append({"repo": fork_url, "success": True})
                
            except Exception as e:
                print(f"    ❌ Error processing {fork_url}: {e}")
                results.append({"repo": fork_url, "success": False, "error": str(e)})
        
        # Process additional repositories
        if additional_repos:
            print(f"\n➕ Processing additional repositories ({len(additional_repos)} repositories):")
            for repo_url in additional_repos:
                repo_name = repo_url.split("/")[-1]
                fork_url = f"{fork_org}/{repo_name}"
                local_path = gh.src_dir / repo_name
                
                # Skip if local checkout exists and --skip-existing is set
                if local_path.exists() and args.skip_existing:
                    print(f"⏭️  Skipping {fork_url} (local checkout exists)")
                    skipped += 1
                    continue
                
                try:
                    print(f"\n📂 Processing {fork_url}...")
                    processed += 1
                    
                    # Step 3a: Clone fork
                    print(f"  🔄 Cloning fork...")
                    result = gh.clone_repository(fork_url)
                    
                    if result["cloned"]:
                        print(f"    ✅ Repository cloned to: {result['local_path']}")
                    else:
                        print(f"    ℹ️  Repository already exists at: {result['local_path']}")
                    
                    # Step 3b: Setup upstream and rebase
                    print(f"  🔄 Setting up upstream and rebasing...")
                    repo_path = Path(result["local_path"])
                    upstream_url = f"https://github.com/{repo_url}"
                    gh.setup_upstream(repo_path, upstream_url)
                    
                    # Step 3c: Detect default branch and create/checkout feature branch
                    print(f"  🔄 Setting up feature branch...")
                    feature_branch = gh.get_branch_name()
                    default_branch = gh.get_default_branch(repo_path)
                    print(f"    📋 Detected default branch: {default_branch}")
                    
                    if not gh.branch_exists(repo_path, feature_branch):
                        print(f"    🆕 Creating feature branch '{feature_branch}' from '{default_branch}'...")
                        gh.create_branch(repo_path, feature_branch, default_branch)
                    else:
                        print(f"    ✅ Feature branch '{feature_branch}' already exists, updating from origin...")
                        # Fetch latest from origin and checkout with tracking
                        gh._run_command(["git", "fetch", "origin"], cwd=repo_path)
                        gh._run_command(["git", "checkout", "--track", f"origin/{feature_branch}"], cwd=repo_path)
                    
                    print(f"    ✅ Setup complete for {fork_url}")
                    results.append({"repo": fork_url, "success": True})
                    
                except Exception as e:
                    print(f"    ❌ Error processing {fork_url}: {e}")
                    results.append({"repo": fork_url, "success": False, "error": str(e)})

        # Summary
        successful = sum(1 for r in results if r["success"])
        failed = len(results) - successful
        
        print(f"\n📊 Summary:")
        print(f"  📂 Processed: {processed}")
        print(f"  ⏭️  Skipped: {skipped}")
        print(f"  ✅ Successful: {successful}")
        print(f"  ❌ Failed: {failed}")
        
        if failed > 0:
            print("\n❌ Failed repositories:")
            for r in results:
                if not r["success"]:
                    print(f"  • {r['repo']}: {r.get('error', 'Unknown error')}")
        
        return 0 if failed == 0 else 1
        
    except Exception as e:
        print(f"❌ Error in clone-forks operation: {e}")
        return 1


def cmd_show_config(args):
    """Handle show-config subcommand"""
    try:
        gh = GitHubWrapper()
        config = gh.config

        print("📋 Current Configuration:")
        print(f"  Project Root: {gh.project_root}")
        print(f"  Config File: {gh.config_file}")
        print(f"  Token File: {gh.token_file}")
        print()

        print("🔗 GitHub Settings:")
        github_config = config.get("github", {})
        print(f"  Fork Organization: {github_config.get('fork_org', 'N/A')}")
        print(f"  Branch Name: {github_config.get('branch_name', 'N/A')}")
        print(f"  Base Branch: {github_config.get('base_branch', 'N/A')}")
        print()

        print("📦 Repository Sources:")
        print("  Manifest Dependencies: Parsed from get_all_manifests.sh")
        additional_repos = config.get("additional_repositories", [])
        if additional_repos:
            print("  ➕ Additional Repositories:")
            for repo in additional_repos:
                print(f"    • {repo} → {github_config.get('fork_org', 'N/A')}/{repo.split('/')[-1]}")
        else:
            print("  ➕ Additional Repositories: None configured")
        print()

        print("🐳 Registry Settings:")
        registry_config = config.get("registry", {})
        print(f"  URL: {registry_config.get('url', 'N/A')}")
        print(f"  Namespace: {registry_config.get('namespace', 'N/A')}")
        print(f"  Tag: {registry_config.get('tag', 'N/A')}")
        print()

        print("🏗️ Build Settings:")
        build_config = config.get("build", {})
        print(f"  Local Mode: {build_config.get('local', 'N/A')}")
        print(f"  Use Branch: {build_config.get('use_branch', 'N/A')}")
        print(f"  Build Image: {build_config.get('image', 'N/A')}")
        print(f"  Custom Registry: {build_config.get('custom_registry', 'N/A')}")
        print(f"  Manifests Only: {build_config.get('manifests_only', 'N/A')}")
        print()

        print("🔄 Migration Settings:")
        migration_config = config.get("migration", {})
        print(f"  Target API: {migration_config.get('target_api', 'N/A')}")
        print(f"  Source Path: {migration_config.get('source_path', 'N/A')}")
        print(f"  Pattern: {migration_config.get('pattern', 'N/A')}")

        return 0

    except Exception as e:
        print(f"❌ Error loading configuration: {e}")
        return 1


def cmd_fork_all(args):
    """Handle fork-all subcommand - forks additional repositories from configuration"""
    try:
        gh = GitHubWrapper()

        print("🔄 Forking additional repositories...")
        additional_repos = gh.get_additional_repositories()
        
        if not additional_repos:
            print("ℹ️  No additional repositories configured in config.yaml")
            print("💡 Note: Manifest dependencies are handled automatically by clone-forks")
            return 0
        
        results = []
        fork_org = gh.get_fork_org()

        print(f"\n📂 Processing {len(additional_repos)} additional repositories:")

        for repo_url in additional_repos:
            try:
                print(f"  🔄 Forking {repo_url}...")
                fork_result = gh.fork_repository(repo_url)

                # Since fork_repository returns RepoInfo, just show that fork is available
                print(f"    ✅ Fork available: {fork_result.fork_owner}/{fork_result.name}")

                # Clone if requested
                if args.clone:
                    print(f"  🔄 Cloning fork...")
                    clone_result = gh.clone_repository(f"{fork_result.fork_owner}/{fork_result.name}")
                    
                    if clone_result["cloned"]:
                        print(f"    ✅ Repository cloned to: {clone_result['local_path']}")
                    else:
                        print(f"    ℹ️  Repository already exists at: {clone_result['local_path']}")

                results.append({"repo": repo_url, "success": True})

            except Exception as e:
                print(f"    ❌ Error processing {repo_url}: {e}")
                results.append({"repo": repo_url, "success": False, "error": str(e)})

        # Summary
        successful = sum(1 for r in results if r["success"])
        failed = len(results) - successful

        print(f"\n📊 Summary:")
        print(f"  ✅ Successful: {successful}")
        print(f"  ❌ Failed: {failed}")

        if failed > 0:
            print("\n❌ Failed repositories:")
            for r in results:
                if not r["success"]:
                    print(f"  • {r['repo']}: {r.get('error', 'Unknown error')}")
        
        print("\n💡 Tip: Use 'clone-forks' for complete setup with manifest dependencies")

        return 0 if failed == 0 else 1

    except Exception as e:
        print(f"❌ Error in fork-all operation: {e}")
        return 1


def cmd_setup_operator(args):
    """Handle setup-operator subcommand"""
    try:
        gh = GitHubWrapper()

        operator_repo = "opendatahub-io/opendatahub-operator"

        print("🔄 Setting up OpenDataHub operator...")

        # Check if local checkout already exists
        repo_name = operator_repo.split("/")[-1]
        local_path = gh.project_root / "src" / repo_name

        if local_path.exists() and not args.force:
            print(f"ℹ️  Local checkout already exists at: {local_path}")
            print("   Use --force to recreate or proceed with existing checkout")
            return 0

        # Step 1: Fork repository
        print("📋 Step 1: Forking repository...")
        fork_result = gh.fork_repository(operator_repo)

        if fork_result["created"]:
            print(f"✅ Fork created: {fork_result['fork_url']}")
        else:
            print(f"ℹ️  Fork already exists: {fork_result['fork_url']}")

        # Step 2: Clone fork
        print("📋 Step 2: Cloning fork...")
        clone_result = gh.clone_repository(operator_repo)

        if clone_result["cloned"]:
            print(f"✅ Repository cloned to: {clone_result['local_path']}")
        else:
            print(f"ℹ️  Repository already exists at: {clone_result['local_path']}")

        # Step 3: Setup upstream and rebase
        print("📋 Step 3: Setting up upstream and rebasing...")
        gh.setup_upstream(operator_repo)

        # Step 4: Create feature branch
        print("📋 Step 4: Creating feature branch...")
        feature_branch = gh.config["github"]["feature_branch"]
        gh.create_branch(operator_repo, feature_branch)

        print(f"✅ OpenDataHub operator setup complete!")
        print(f"   📁 Location: {clone_result['local_path']}")
        print(f"   🌿 Branch: {feature_branch}")
        print(f"   🔗 Fork: {fork_result['fork_url']}")

        return 0

    except Exception as e:
        print(f"❌ Error setting up operator: {e}")
        return 1


def cmd_setup_manifests(args):
    """Handle setup-manifests subcommand (also used for setup-forks)"""
    try:
        gh = GitHubWrapper()

        print("🔄 Setting up manifest repository forks...")

        # Parse manifest repositories from get_all_manifests.sh
        manifest_repos = gh.parse_manifest_repositories()

        print(f"📋 Found {len(manifest_repos)} repositories in manifest dependencies")

        if args.dry_run:
            print("\n🔍 DRY RUN - Would process the following repositories:")
            for repo_info in manifest_repos:
                print(f"  • {repo_info.full_name} (base: {repo_info.base_branch})")
            return 0

        results = []
        processed = 0
        skipped = 0

        for repo_info in manifest_repos:
            repo_name = repo_info.full_name
            local_path = gh.project_root / "src" / repo_name.split("/")[-1]

            # Skip if local checkout exists and --skip-existing is set
            if local_path.exists() and args.skip_existing:
                print(f"⏭️  Skipping {repo_name} (local checkout exists)")
                skipped += 1
                continue

            try:
                print(f"\n📂 Processing {repo_name}...")
                processed += 1

                # Step 1: Fork repository
                print(f"  🔄 Forking repository...")
                fork_result = gh.fork_repository(repo_name)

                if fork_result["created"]:
                    print(f"    ✅ Fork created: {fork_result['fork_url']}")
                    # Add delay after fork creation to prevent race conditions
                    time.sleep(3)
                else:
                    print(f"    ℹ️  Fork already exists: {fork_result['fork_url']}")

                # Step 2: Clone fork
                print(f"  🔄 Cloning fork...")
                clone_result = gh.clone_repository(repo_name)

                if clone_result["cloned"]:
                    print(f"    ✅ Repository cloned to: {clone_result['local_path']}")
                else:
                    print(
                        f"    ℹ️  Repository already exists at: {clone_result['local_path']}"
                    )

                # Step 3: Setup upstream and rebase
                print(f"  🔄 Setting up upstream and rebasing...")
                gh.setup_upstream(repo_name, repo_info.base_branch)

                # Step 4: Create feature branch
                print(f"  🔄 Creating feature branch...")
                feature_branch = gh.config["github"]["feature_branch"]
                gh.create_branch(repo_name, feature_branch, repo_info.base_branch)

                print(f"    ✅ Setup complete for {repo_name}")
                results.append({"repo": repo_name, "success": True})

            except Exception as e:
                print(f"    ❌ Error processing {repo_name}: {e}")
                results.append({"repo": repo_name, "success": False, "error": str(e)})

        # Summary
        successful = sum(1 for r in results if r["success"])
        failed = len(results) - successful

        print(f"\n📊 Summary:")
        print(f"  📂 Processed: {processed}")
        print(f"  ⏭️  Skipped: {skipped}")
        print(f"  ✅ Successful: {successful}")
        print(f"  ❌ Failed: {failed}")

        if failed > 0:
            print("\n❌ Failed repositories:")
            for r in results:
                if not r["success"]:
                    print(f"  • {r['repo']}: {r.get('error', 'Unknown error')}")

        return 0 if failed == 0 else 1

    except Exception as e:
        print(f"❌ Error in setup-manifests operation: {e}")
        return 1


def cmd_forks_status(args):
    """Handle forks-status subcommand"""
    try:
        gh = GitHubWrapper()

        # Set up logging level
        if not args.verbose:
            logging.getLogger().setLevel(logging.WARNING)

        print("📋 Repository Status Summary:")
        print()

        # Get all repositories from src directory
        src_dir = gh.project_root / "src"
        if not src_dir.exists():
            print("ℹ️  No src directory found - no repositories to check")
            return 0

        repos = [d for d in src_dir.iterdir() if d.is_dir() and (d / ".git").exists()]

        if not repos:
            print("ℹ️  No git repositories found in src directory")
            return 0

        clean_repos = []
        dirty_repos = []

        for repo_dir in sorted(repos):
            try:
                repo_name = repo_dir.name

                # Get current branch
                result = subprocess.run(
                    ["git", "branch", "--show-current"],
                    cwd=repo_dir,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                current_branch = result.stdout.strip()

                # Get status
                result = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=repo_dir,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                status_lines = (
                    result.stdout.strip().split("\n") if result.stdout.strip() else []
                )

                # Count changes by type
                modified = len([line for line in status_lines if line.startswith(" M")])
                added = len([line for line in status_lines if line.startswith("A")])
                deleted = len([line for line in status_lines if line.startswith(" D")])
                untracked = len(
                    [line for line in status_lines if line.startswith("??")]
                )

                is_dirty = len(status_lines) > 0

                # Get remote URLs
                try:
                    result = subprocess.run(
                        ["git", "remote", "-v"],
                        cwd=repo_dir,
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    remotes = result.stdout.strip()

                    origin_url = "N/A"
                    upstream_url = "N/A"

                    for line in remotes.split("\n"):
                        if line.startswith("origin") and "(fetch)" in line:
                            origin_url = line.split()[1]
                        elif line.startswith("upstream") and "(fetch)" in line:
                            upstream_url = line.split()[1]

                except:
                    origin_url = upstream_url = "N/A"

                # Get fork org from origin URL
                fork_org = "N/A"
                if "github.com" in origin_url:
                    try:
                        if origin_url.startswith("git@"):
                            # SSH format: git@github.com:org/repo.git
                            fork_org = origin_url.split(":")[1].split("/")[0]
                        else:
                            # HTTPS format: https://github.com/org/repo.git
                            fork_org = origin_url.split("/")[-2]
                    except:
                        pass

                repo_info = {
                    "name": repo_name,
                    "branch": current_branch,
                    "is_dirty": is_dirty,
                    "modified": modified,
                    "added": added,
                    "deleted": deleted,
                    "untracked": untracked,
                    "origin_url": origin_url,
                    "upstream_url": upstream_url,
                    "fork_org": fork_org,
                    "status_lines": status_lines,
                }

                if is_dirty:
                    dirty_repos.append(repo_info)
                else:
                    clean_repos.append(repo_info)

            except Exception as e:
                print(f"❌ Error checking {repo_name}: {e}")
                continue

        # Filter display based on --dirty flag
        repos_to_show = dirty_repos if args.dirty else (clean_repos + dirty_repos)

        if not repos_to_show:
            if args.dirty:
                print("✅ No repositories with uncommitted changes")
            else:
                print("ℹ️  No repositories found")
            return 0

        # Display repository status
        for repo_info in repos_to_show:
            status_icon = "🔄" if repo_info["is_dirty"] else "✅"
            changes = []

            if repo_info["modified"] > 0:
                changes.append(f"{repo_info['modified']}M")
            if repo_info["added"] > 0:
                changes.append(f"{repo_info['added']}A")
            if repo_info["deleted"] > 0:
                changes.append(f"{repo_info['deleted']}D")
            if repo_info["untracked"] > 0:
                changes.append(f"{repo_info['untracked']}U")

            change_summary = f" ({', '.join(changes)})" if changes else ""

            print(
                f"{status_icon} {repo_info['fork_org']}/{repo_info['name']}:{repo_info['branch']}{change_summary}"
            )

            # Show detailed file changes if requested
            if args.show_files and repo_info["is_dirty"]:
                for line in repo_info["status_lines"]:
                    if line.strip():
                        print(f"    {line}")

            # Show remote URLs
            print(f"    🔗 origin: {repo_info['origin_url']}")
            print(f"    🔗 upstream: {repo_info['upstream_url']}")
            print()

        # Summary
        total = len(clean_repos) + len(dirty_repos)
        clean_count = len(clean_repos)
        dirty_count = len(dirty_repos)

        if not args.dirty:
            print(
                f"📊 Summary: {total} repositories ({clean_count} clean, {dirty_count} dirty)"
            )
        else:
            print(f"📊 Summary: {dirty_count} repositories with changes")

        return 0

    except Exception as e:
        print(f"❌ Error checking repository status: {e}")
        return 1


def cmd_forks_commit(args):
    """Handle forks-commit subcommand"""
    try:
        gh = GitHubWrapper()

        commit_message = args.message or "Gateway API migration changes"

        print("🔄 Committing changes across all repositories...")
        print(f"📝 Commit message: {commit_message}")
        print()

        # Get all repositories from src directory
        src_dir = gh.project_root / "src"
        if not src_dir.exists():
            print("ℹ️  No src directory found - no repositories to commit")
            return 0

        repos = [d for d in src_dir.iterdir() if d.is_dir() and (d / ".git").exists()]

        if not repos:
            print("ℹ️  No git repositories found in src directory")
            return 0

        results = []

        branch_name = gh.get_branch_name()

        for repo_dir in sorted(repos):
            try:
                repo_name = repo_dir.name

                print(f"📂 Processing {repo_name}...")

                # Check if there are changes to commit
                result = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=repo_dir,
                    capture_output=True,
                    text=True,
                    check=True,
                )

                if not result.stdout.strip():
                    print(f"    ℹ️  No changes to commit")
                    results.append({"repo": repo_name, "status": "no_changes"})
                    continue

                # Add all changes
                print(f"    📋 Adding changes...")
                subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)

                # Commit changes
                print(f"    💾 Committing changes...")
                subprocess.run(
                    ["git", "commit", "-m", commit_message], cwd=repo_dir, check=True
                )

                # Push changes
                print(f"    🚀 Pushing changes to origin {branch_name}...")
                subprocess.run(
                    ["git", "push", "origin", branch_name], cwd=repo_dir, check=True
                )

                print(f"    ✅ Successfully committed and pushed changes")
                results.append({"repo": repo_name, "status": "success"})

            except subprocess.CalledProcessError as e:
                print(f"    ❌ Error committing {repo_name}: {e}")
                results.append({"repo": repo_name, "status": "error", "error": str(e)})
            except Exception as e:
                print(f"    ❌ Unexpected error with {repo_name}: {e}")
                results.append({"repo": repo_name, "status": "error", "error": str(e)})

        # Summary
        successful = sum(1 for r in results if r["status"] == "success")
        no_changes = sum(1 for r in results if r["status"] == "no_changes")
        failed = sum(1 for r in results if r["status"] == "error")

        print(f"\n📊 Summary:")
        print(f"  ✅ Successful: {successful}")
        print(f"  ℹ️  No changes: {no_changes}")
        print(f"  ❌ Failed: {failed}")

        if failed > 0:
            print("\n❌ Failed repositories:")
            for r in results:
                if r["status"] == "error":
                    print(f"  • {r['repo']}: {r.get('error', 'Unknown error')}")

        return 0 if failed == 0 else 1

    except Exception as e:
        print(f"❌ Error in forks-commit operation: {e}")
        return 1


def cmd_workflow(args):
    """Handle workflow subcommand with multiple operations"""
    try:
        engine = AnsibleEngine()

        # Handle --list operation
        if args.list:
            task_names = engine.list_tasks()
            if not task_names:
                print("No task files found in tasks/ directory")
                return 0

            print("Available tasks:")
            for task_name in task_names:
                task_path = engine.get_task_file_path(task_name)
                if task_path:
                    try:
                        # Read first few lines to get description/comment
                        with open(task_path, "r") as f:
                            lines = f.readlines()
                            description = "Ansible task file"
                            # Look for description in comments
                            for line in lines[:5]:
                                line = line.strip()
                                if line.startswith("#") and any(
                                    word in line.lower()
                                    for word in ["ansible", "task", "file"]
                                ):
                                    description = line[1:].strip()
                                    break

                        print(f"  • {task_name} - {description}")
                        print(f"    File: {task_path}")
                        print()
                    except Exception as e:
                        print(f"  • {task_name} - Error reading task file: {e}")
                        print()
                else:
                    print(f"  • {task_name} - Task file not found")
                    print()
            return 0

        # Handle --vars operation
        if args.vars is not None:
            if args.vars == "":
                # Show all config variables
                engine.show_available_variables()
            else:
                # Show variables for specific task (same as global since they come from config)
                print(f"Variables available for task '{args.vars}':")
                engine.show_available_variables()
            return 0

        # Handle --show operation
        if args.show:
            try:
                engine.show_task_info(args.show)
                return 0
            except Exception as e:
                print(f"❌ Error showing task '{args.show}': {e}")
                return 1

        # Handle --name operation (requires --exec)
        if args.name:
            if not args.exec:
                print("❌ --name requires --exec flag to execute the task")
                return 1

            # Parse runtime variables
            runtime_vars = {}
            if args.var:
                for var_assignment in args.var:
                    if "=" not in var_assignment:
                        print(
                            f"❌ Invalid variable format: {var_assignment} (expected KEY=VALUE)"
                        )
                        return 1
                    key, value = var_assignment.split("=", 1)
                    runtime_vars[key] = value

            # Execute task
            try:
                print(f"🔄 Executing task: {args.name}")
                if runtime_vars:
                    print(f"📋 Runtime variables: {runtime_vars}")
                print()

                verbose = getattr(args, "verbose", False)
                success = engine.execute_task(args.name, runtime_vars, verbose)

                if success:
                    print(f"\n✅ Task '{args.name}' completed successfully")
                    return 0
                else:
                    print(f"\n❌ Task '{args.name}' failed")
                    return 1

            except Exception as e:
                print(f"❌ Error executing task '{args.name}': {e}")
                return 1

        # If we get here, no valid operation was specified
        print(
            "❌ No operation specified. Use --list, --show, --vars, or --name with --exec"
        )
        return 1

    except Exception as e:
        print(f"❌ Error in task operation: {e}")
        return 1


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="OpenDataHub Gateway API Migration Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s whoami
  %(prog)s show-config
  %(prog)s setup-operator
  %(prog)s setup-forks
  %(prog)s setup-forks --dry-run
  %(prog)s setup-forks --skip-existing
  %(prog)s forks-status
  %(prog)s forks-status --show-files
  %(prog)s forks-status --dirty
  %(prog)s forks-status --dirty --show-files
  %(prog)s forks-commit
  %(prog)s forks-commit -m "Custom commit message"
  %(prog)s workflow --list
  %(prog)s workflow --show build-push-deploy
  %(prog)s workflow --name build --exec
  %(prog)s workflow --name build-push-deploy --exec --var registry_tag=dev
  %(prog)s workflow --name deploy --exec --var namespace=test
  %(prog)s workflow --vars
  %(prog)s workflow --vars build-push-deploy
  %(prog)s list-repos opendatahub-io
  %(prog)s fork-repo opendatahub-io/odh-dashboard --clone
  %(prog)s fork-all --clone
  %(prog)s clone-repo opendatahub-io/odh-dashboard
  %(prog)s clone-forks --dry-run
  %(prog)s clone-forks --skip-existing

Note: This tool can be run from anywhere within the project directory tree.
      It will automatically find config.yaml and .github_token files in the project root.

For build and deployment operations, use the Ansible-based task system:
  %(prog)s workflow --name build --exec                    # Build operator
  %(prog)s workflow --name build-push --exec               # Build and push
  %(prog)s workflow --name push --exec                     # Push image
  %(prog)s workflow --name deploy --exec                   # Deploy to cluster
  %(prog)s workflow --name build-push-deploy --exec        # Full pipeline
        """,
    )

    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )

    # Create subparsers for different commands
    subparsers = parser.add_subparsers(
        dest="command", help="Available commands", required=True
    )

    # whoami subcommand
    whoami_parser = subparsers.add_parser(
        "whoami", help="Check GitHub authentication status"
    )
    whoami_parser.set_defaults(func=cmd_whoami)

    # show-config subcommand
    config_parser = subparsers.add_parser(
        "show-config", help="Display current configuration settings"
    )
    config_parser.set_defaults(func=cmd_show_config)

    # list-repos subcommand
    list_repos_parser = subparsers.add_parser(
        "list-repos", help="List repositories for a user or organization"
    )
    list_repos_parser.add_argument("owner", help="GitHub username or organization name")
    list_repos_parser.add_argument(
        "--limit",
        type=int,
        default=30,
        help="Maximum number of repositories to list (default: 30)",
    )
    list_repos_parser.set_defaults(func=cmd_list_repos)

    # fork-repo subcommand
    fork_repo_parser = subparsers.add_parser("fork-repo", help="Fork a repository")
    fork_repo_parser.add_argument(
        "repository", help="Repository to fork (e.g., opendatahub-io/odh-dashboard)"
    )
    fork_repo_parser.add_argument(
        "--clone", action="store_true", help="Clone the fork after creating it"
    )
    fork_repo_parser.set_defaults(func=cmd_fork_repo)

    # clone-repo subcommand
    clone_repo_parser = subparsers.add_parser("clone-repo", help="Clone a repository")
    clone_repo_parser.add_argument(
        "repository", help="Repository to clone (e.g., opendatahub-io/odh-dashboard)"
    )
    clone_repo_parser.set_defaults(func=cmd_clone_repo)

    # clone-forks subcommand
    clone_forks_parser = subparsers.add_parser(
        "clone-forks", help="Clone all fork repositories from manifest dependencies"
    )
    clone_forks_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    clone_forks_parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip repositories that already have local checkouts",
    )
    clone_forks_parser.set_defaults(func=cmd_clone_forks)

    # fork-all subcommand
    fork_all_parser = subparsers.add_parser(
        "fork-all", help="Fork additional repositories from configuration"
    )
    fork_all_parser.add_argument(
        "--clone", action="store_true", help="Clone repositories after forking"
    )
    fork_all_parser.set_defaults(func=cmd_fork_all)

    # setup-operator subcommand
    setup_operator_parser = subparsers.add_parser(
        "setup-operator",
        help="Set up OpenDataHub operator fork, clone, and feature branch",
    )
    setup_operator_parser.add_argument(
        "--force", action="store_true", help="Force setup even if local checkout exists"
    )
    setup_operator_parser.set_defaults(func=cmd_setup_operator)

    # setup-forks subcommand (alias for setup-manifests)
    setup_forks_parser = subparsers.add_parser(
        "setup-forks", help="Set up all required manifest repository forks"
    )
    setup_forks_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    setup_forks_parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip repositories that already have local checkouts",
    )
    setup_forks_parser.set_defaults(func=cmd_setup_manifests)

    # forks-status subcommand
    forks_status_parser = subparsers.add_parser(
        "forks-status", help="Show status of all local repository forks"
    )
    forks_status_parser.add_argument(
        "--dirty",
        action="store_true",
        help="Show only repositories with uncommitted changes",
    )
    forks_status_parser.add_argument(
        "--show-files",
        action="store_true",
        help="Show detailed file changes for dirty repositories",
    )
    forks_status_parser.set_defaults(func=cmd_forks_status)

    # forks-commit subcommand
    forks_commit_parser = subparsers.add_parser(
        "forks-commit", help="Commit and push changes across all local repositories"
    )
    forks_commit_parser.add_argument(
        "-m",
        "--message",
        help='Commit message (default: "Gateway API migration changes")',
    )
    forks_commit_parser.set_defaults(func=cmd_forks_commit)

    # Workflow subcommand with multiple operations (now using Ansible tasks)
    workflow_parser = subparsers.add_parser(
        "workflow", help="Ansible-based task management operations"
    )

    # Create mutually exclusive group for main operations
    workflow_group = workflow_parser.add_mutually_exclusive_group(required=True)

    workflow_group.add_argument(
        "--list", action="store_true", help="List all available Ansible task files"
    )

    workflow_group.add_argument(
        "--show", metavar="NAME", help="Show details of a specific task file"
    )

    workflow_group.add_argument(
        "--vars",
        nargs="?",
        const="",
        metavar="NAME",
        help="Show available Ansible variables (all config vars if no name specified)",
    )

    workflow_group.add_argument(
        "--name",
        metavar="NAME",
        help="Specify task name for execution (requires --exec)",
    )

    # Additional flags for task execution
    workflow_parser.add_argument(
        "--exec", action="store_true", help="Execute the task specified by --name"
    )

    workflow_parser.add_argument(
        "--var",
        action="append",
        metavar="KEY=VALUE",
        help="Set Ansible variables (format: KEY=VALUE). Can be used multiple times.",
    )

    workflow_parser.set_defaults(func=cmd_workflow)

    args = parser.parse_args()

    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\n❌ Operation cancelled by user")
        return 1
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
