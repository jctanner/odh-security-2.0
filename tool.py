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
- Integration with build systems and manifest management

Core Workflows:
- Repository setup: fork, clone, rebase, branch creation
- Batch operations across multiple target repositories
- Configuration-driven development environment management
- Build system integration for manifest management

Usage Context:
This tool is designed for the odh-security-2.0 project where multiple
opendatahub-io repositories need to be forked, cloned, and patched for
Gateway API migration. All repository checkouts are managed in the src/
directory structure to keep the main project clean.

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
from workflow_engine import WorkflowEngine


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
            privacy = "🔒" if repo.get('isPrivate', False) else "🌐"
            print(f"  {privacy} {repo['name']} - {repo.get('url', 'N/A')}")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error listing repositories: {e}")
        return 1


def cmd_fork_repo(args):
    """Handle fork-repo subcommand"""
    try:
        gh = GitHubWrapper()
        repo_info = gh.fork_repository(args.repository, clone_after_fork=args.clone)
        
        print(f"Successfully forked {repo_info.url}")
        print(f"Fork available at: https://github.com/{repo_info.fork_owner}/{repo_info.name}")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error forking repository: {e}")
        return 1


def cmd_clone_repo(args):
    """Handle clone-repo subcommand"""
    try:
        gh = GitHubWrapper()
        repo_path = gh.clone_repository(args.repository)
        
        print(f"Repository cloned to: {repo_path}")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error cloning repository: {e}")
        return 1


def cmd_show_config(args):
    """Handle show-config subcommand"""
    try:
        gh = GitHubWrapper()
        config = gh.config
        
        print("Current Configuration:")
        print("=" * 50)
        
        # GitHub settings
        github_config = config.get('github', {})
        print(f"GitHub:")
        print(f"  Fork Organization: {github_config.get('fork_org', 'Not set')}")
        print(f"  Branch Name: {github_config.get('branch_name', 'Not set')}")
        print(f"  Base Branch: {github_config.get('base_branch', 'Not set')}")
        
        # Target repositories
        target_repos = config.get('target_repositories', [])
        print(f"\nTarget Repositories ({len(target_repos)}):")
        for repo in target_repos:
            print(f"  - {repo}")
        
        # Migration settings
        migration_config = config.get('migration', {})
        print(f"\nMigration Settings:")
        print(f"  Auto Create Branch: {migration_config.get('auto_create_branch', 'Not set')}")
        print(f"  Setup Upstream: {migration_config.get('setup_upstream', 'Not set')}")
        
        # Registry settings
        registry_config = config.get('registry', {})
        print(f"\nRegistry Settings:")
        print(f"  URL: {registry_config.get('url', 'Not set')}")
        print(f"  Namespace: {registry_config.get('namespace', 'Not set')}")
        print(f"  Tag: {registry_config.get('tag', 'Not set')}")
        
        # Build settings
        build_config = config.get('build', {})
        print(f"\nBuild Configuration:")
        print(f"  Local: {build_config.get('local', 'Not set')}")
        print(f"  Use Branch: {build_config.get('use_branch', 'Not set')}")
        print(f"  Image: {build_config.get('image', 'Not set')}")
        print(f"  Custom Registry: {build_config.get('custom_registry', 'Not set')}")
        print(f"  Manifests Only: {build_config.get('manifests_only', 'Not set')}")
        
        # Example commands
        print(f"\nExample Commands:")
        print(f"  Setup workflow:")
        print(f"   - python3 tool.py whoami")
        print(f"   - python3 tool.py setup-operator")
        print(f"   - python3 tool.py setup-forks")
        print(f"   - python3 tool.py build-operator  # Uses config defaults")
        print(f"   - python3 tool.py build-operator --local --use-branch --manifests-only")
        print(f"   - python3 tool.py build-operator --local --use-branch --image")
        print(f"   - python3 tool.py build-and-push --local --use-branch --custom-registry")
        print(f"   - python3 tool.py image-push --custom-registry")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error displaying configuration: {e}")
        return 1


def cmd_fork_all(args):
    """Handle fork-all subcommand"""
    try:
        gh = GitHubWrapper()
        target_repos = gh.get_target_repositories()
        
        if not target_repos:
            print("No target repositories configured")
            return 1
        
        print(f"Forking {len(target_repos)} repositories...")
        
        successful = []
        failed = []
        
        for repo in target_repos:
            try:
                print(f"\n🔀 Forking {repo}...")
                repo_info = gh.fork_repository(repo, clone_after_fork=args.clone)
                successful.append(repo)
                print(f"✅ Successfully forked {repo}")
                
            except Exception as e:
                failed.append((repo, str(e)))
                print(f"❌ Failed to fork {repo}: {e}")
        
        print(f"\n📊 Summary:")
        print(f"   ✅ Successful: {len(successful)}")
        print(f"   ❌ Failed: {len(failed)}")
        
        if failed:
            print(f"\nFailed repositories:")
            for repo, error in failed:
                print(f"   - {repo}: {error}")
            return 1
        
        return 0
        
    except Exception as e:
        print(f"❌ Error in fork-all: {e}")
        return 1


def cmd_setup_operator(args):
    """Handle setup-operator subcommand"""
    try:
        gh = GitHubWrapper()
        operator_repo = "opendatahub-io/opendatahub-operator"
        
        # Check if local checkout already exists
        if gh.local_checkout_exists("opendatahub-operator") and not args.force:
            print("❌ Local checkout already exists. Use --force to recreate.")
            return 1
        
        print(f"🚀 Setting up OpenDataHub Operator...")
        print(f"   Repository: {operator_repo}")
        print(f"   Fork organization: {gh.get_fork_org()}")
        print(f"   Feature branch: {gh.get_branch_name()}")
        
        # Fork if needed
        if not gh.fork_exists(operator_repo):
            print("🔀 Creating fork...")
            gh.fork_repository(operator_repo, clone_after_fork=False)
        else:
            print("✅ Fork already exists")
        
        # Clone repository
        print("📥 Cloning repository...")
        clone_path = gh.clone_repository(f"{gh.get_fork_org()}/opendatahub-operator", "opendatahub-operator")
        
        # Setup upstream
        print("🔗 Setting up upstream remote...")
        upstream_url = f"https://github.com/{operator_repo}"
        gh.setup_upstream(clone_path, upstream_url)
        
        # Rebase from upstream
        print("🔄 Rebasing from upstream...")
        gh.rebase_from_upstream(clone_path)
        
        # Create feature branch
        branch_name = gh.get_branch_name()
        print(f"🌿 Creating feature branch: {branch_name}")
        gh.create_branch(clone_path, branch_name)
        
        print(f"✅ OpenDataHub Operator setup complete!")
        print(f"   Local path: {clone_path}")
        print(f"   Current branch: {branch_name}")
        print(f"   Ready for Gateway API migration development")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error setting up operator: {e}")
        return 1


def cmd_build_operator(args):
    """Handle build-operator subcommand"""
    try:
        gh = GitHubWrapper()
        operator_path = gh.src_dir / "opendatahub-operator"
        
        if not operator_path.exists():
            print("❌ opendatahub-operator not found. Run 'tool.py setup-operator' first.")
            return 1
        
        # Apply config defaults for flags not explicitly provided
        build_defaults = gh.get_build_defaults()
        
        # Apply defaults only if the flag wasn't explicitly provided
        use_local = getattr(args, 'local', False) or build_defaults.get('local', False)
        use_branch = getattr(args, 'use_branch', False) or build_defaults.get('use_branch', False)
        build_image = getattr(args, 'image', False) or build_defaults.get('image', False)
        use_custom_registry = getattr(args, 'custom_registry', False) or build_defaults.get('custom_registry', False)
        manifests_only = getattr(args, 'manifests_only', False) or build_defaults.get('manifests_only', False)
        
        # Override args with resolved values
        args.local = use_local
        args.use_branch = use_branch
        args.image = build_image
        args.custom_registry = use_custom_registry
        args.manifests_only = manifests_only
        
        print(f"🔧 Building OpenDataHub Operator...")
        print(f"   Fork organization: {gh.get_fork_org()}")
        print(f"   Local mode: {args.local}")
        print(f"   Manifests only: {args.manifests_only}")
        print(f"   Image build: {args.image}")
        print(f"   Custom registry: {args.custom_registry}")
        if args.use_branch:
            print(f"   Using feature branch: {gh.get_branch_name()}")
        
        # Show which settings came from config defaults
        config_applied = []
        if build_defaults.get('local', False) and not hasattr(args, '_local_from_cli'):
            config_applied.append("--local")
        if build_defaults.get('use_branch', False) and not hasattr(args, '_use_branch_from_cli'):
            config_applied.append("--use-branch")
        if build_defaults.get('image', False) and not hasattr(args, '_image_from_cli'):
            config_applied.append("--image")
        if build_defaults.get('custom_registry', False) and not hasattr(args, '_custom_registry_from_cli'):
            config_applied.append("--custom-registry")
        if build_defaults.get('manifests_only', False) and not hasattr(args, '_manifests_only_from_cli'):
            config_applied.append("--manifests-only")
        
        if config_applied:
            print(f"   Config defaults applied: {', '.join(config_applied)}")
        
        # Prepare environment variables
        build_env = os.environ.copy()
        
        # Prevent git from prompting for credentials - fail fast instead of hanging
        build_env['GIT_TERMINAL_PROMPT'] = '0'
        build_env['GIT_ASKPASS'] = ''
        build_env['SSH_ASKPASS'] = ''
        
        # Set fork organization for manifest fetching
        fork_org = gh.get_fork_org()
        build_env['FORK_ORG'] = fork_org
        
        # Set branch name if using branch
        if args.use_branch:
            build_env['BRANCH_NAME'] = gh.get_branch_name()
        
        # Set custom registry environment variables if using custom registry
        if args.custom_registry:
            build_env['CUSTOM_REGISTRY_URL'] = gh.get_registry_url()
            build_env['CUSTOM_REGISTRY_NAMESPACE'] = gh.get_registry_namespace()
            build_env['CUSTOM_REGISTRY_TAG'] = gh.get_registry_tag()
        
        # Set local mode environment variables if using local checkouts
        if args.local:
            build_env['LOCAL_MODE'] = 'true'
            build_env['LOCAL_CHECKOUTS_DIR'] = str(gh.src_dir.absolute())
        
        # Determine what to build using the new Makefile targets
        if args.manifests_only:
            print("📦 Fetching manifests only...")
            if args.local:
                if args.use_branch:
                    command = ["make", "get-manifests-local-branch"]
                else:
                    command = ["make", "get-manifests-local"]
            else:
                if args.use_branch:
                    command = ["make", "get-manifests-fork-branch"]
                else:
                    command = ["make", "get-manifests-fork"]
        elif args.image:
            print("🐳 Building container image...")
            if args.custom_registry:
                if args.local:
                    if args.use_branch:
                        command = ["make", "image-build-custom-registry-local-branch"]
                    else:
                        command = ["make", "image-build-custom-registry-local"]
                else:
                    command = ["make", "image-build-custom-registry"]
            else:
                if args.local:
                    if args.use_branch:
                        command = ["make", "image-build-local-branch"]
                    else:
                        command = ["make", "image-build-local"]
                else:
                    if args.use_branch:
                        command = ["make", "image-build-fork-branch"]
                    else:
                        command = ["make", "image-build-fork"]
        else:
            print("🔨 Building operator binary...")
            command = ["make", "build"]
        
        print(f"   Executing: {' '.join(command)}")
        print(f"   Working directory: {operator_path}")
        
        # Execute the build command
        result = subprocess.run(
            command,
            cwd=operator_path,
            env=build_env,
            capture_output=False,
            text=True
        )
        
        if result.returncode == 0:
            print("✅ Build completed successfully!")
            if args.manifests_only:
                print(f"   Manifests available in: {operator_path}/opt/manifests/")
            elif args.image:
                print(f"   Container image built")
            else:
                print(f"   Binary available in: {operator_path}/bin/manager")
        else:
            print("❌ Build failed!")
            
        return result.returncode
        
    except Exception as e:
        print(f"❌ Error building operator: {e}")
        return 1


def cmd_setup_manifests(args):
    """Handle setup-forks/setup-manifests subcommands"""
    try:
        gh = GitHubWrapper()
        
        # First ensure opendatahub-operator is set up (required for parsing get_all_manifests.sh)
        operator_path = gh.src_dir / "opendatahub-operator"
        if not operator_path.exists():
            print("⚠️  opendatahub-operator not found. Setting up first...")
            setup_args = type('Args', (), {'force': False})()
            result = cmd_setup_operator(setup_args)
            if result != 0:
                print("❌ Failed to set up opendatahub-operator")
                return 1
        
        print("🔍 Parsing fork requirements from get_all_manifests.sh...")
        try:
            repo_branches = gh.parse_manifest_repositories()
        except Exception as e:
            print(f"❌ Failed to parse required repositories: {e}")
            return 1
        
        print(f"📋 Found {len(repo_branches)} repositories that need forks:")
        for repo, branch in repo_branches.items():
            print(f"   - {repo} (base branch: {branch})")
        
        print(f"\n🚀 Setting up fork repositories...")
        print(f"   Fork organization: {gh.get_fork_org()}")
        print(f"   Feature branch: {gh.get_branch_name()}")
        print(f"   Using base branches from get_all_manifests.sh")
        
        # Track success/failure
        successful = []
        failed = []
        skipped = []
        
        for repo_name, base_branch in repo_branches.items():
            if args.skip_existing and gh.local_checkout_exists(repo_name):
                print(f"⏭️  Skipping {repo_name} (already exists)")
                skipped.append(repo_name)
                continue
            
            if args.dry_run:
                print(f"🔍 Would set up: {repo_name} (base: {base_branch})")
                continue
            
            print(f"\n📦 Setting up {repo_name}...")
            if gh.setup_manifest_repository(repo_name, base_branch):
                successful.append(repo_name)
                print(f"✅ Successfully set up {repo_name}")
            else:
                failed.append(repo_name)
                print(f"❌ Failed to set up {repo_name}")
        
        if args.dry_run:
            print(f"\n🔍 Dry run completed. Would process {len(repo_branches)} repositories.")
            return 0
        
        print(f"\n📊 Summary:")
        print(f"   ✅ Successful: {len(successful)}")
        print(f"   ❌ Failed: {len(failed)}")
        print(f"   ⏭️  Skipped: {len(skipped)}")
        
        if failed:
            print(f"\n⚠️  Some repositories failed to set up. You can:")
            print(f"   - Re-run this command to retry failed repositories")
            print(f"   - Use --skip-existing to only process missing repositories")
            return 1
        else:
            print(f"\n🎉 All fork repositories are ready!")
            print(f"   You can now run:")
            print(f"   - python3 tool.py build-operator  # Uses config defaults")
            print(f"   - python3 tool.py build-operator --local --use-branch --manifests-only")
            print(f"   - python3 tool.py build-operator --local --use-branch --image")
            print(f"   - python3 tool.py build-and-push --local --use-branch --custom-registry")
            print(f"   - python3 tool.py image-push --custom-registry")
            return 0
        
    except Exception as e:
        print(f"❌ Error setting up fork repositories: {e}")
        return 1


def cmd_image_push(args):
    """Handle image-push subcommand"""
    try:
        gh = GitHubWrapper()
        
        # Ensure opendatahub-operator exists
        operator_path = gh.src_dir / "opendatahub-operator"
        if not operator_path.exists():
            print("❌ opendatahub-operator not found. Run setup-operator first.")
            return 1
        
        # Apply config defaults for image-push flags
        build_defaults = gh.get_build_defaults()
        
        # Apply defaults only if the flag wasn't explicitly provided
        use_custom_registry = getattr(args, 'custom_registry', False) or build_defaults.get('custom_registry', False)
        
        # Override args with resolved values
        args.custom_registry = use_custom_registry
        
        print("📤 Pushing container image...")
        print(f"   Custom registry: {args.custom_registry}")
        
        # Show which settings came from config defaults
        config_applied = []
        if build_defaults.get('custom_registry', False) and not hasattr(args, '_custom_registry_from_cli'):
            config_applied.append("--custom-registry")
        
        if config_applied:
            print(f"   Config defaults applied: {', '.join(config_applied)}")
        
        # Prepare environment variables for push
        push_env = os.environ.copy()
        
        # Set custom registry environment variables if using custom registry
        if args.custom_registry:
            push_env['CUSTOM_REGISTRY_URL'] = gh.get_registry_url()
            push_env['CUSTOM_REGISTRY_NAMESPACE'] = gh.get_registry_namespace()
            push_env['CUSTOM_REGISTRY_TAG'] = gh.get_registry_tag()
            print(f"   Using custom registry: {gh.get_registry_url()}")
            print(f"   Namespace: {gh.get_registry_namespace()}")
            print(f"   Tag: {gh.get_registry_tag()}")
            print(f"   Full image: {gh.get_full_image_name('odh-operator')}")
            command = ["make", "image-push-custom-registry"]
        else:
            command = ["make", "image-push"]
        
        print(f"   Executing: {' '.join(command)}")
        print(f"   Working directory: {operator_path}")
        
        # Execute the push command
        result = subprocess.run(
            command,
            cwd=operator_path,
            env=push_env,
            capture_output=False,
            text=True
        )
        
        if result.returncode == 0:
            print("✅ Image pushed successfully!")
        else:
            print("❌ Image push failed!")
            
        return result.returncode
        
    except Exception as e:
        print(f"❌ Error pushing image: {e}")
        return 1


def cmd_build_and_push(args):
    """Handle build-and-push subcommand - builds image and pushes in one operation"""
    try:
        gh = GitHubWrapper()
        
        print("🚀 Building and pushing container image...")
        
        # Apply config defaults for build-and-push flags
        build_defaults = gh.get_build_defaults()
        
        # Apply defaults only if the flag wasn't explicitly provided
        use_local = getattr(args, 'local', False) or build_defaults.get('local', False)
        use_branch = getattr(args, 'use_branch', False) or build_defaults.get('use_branch', False)
        use_custom_registry = getattr(args, 'custom_registry', False) or build_defaults.get('custom_registry', False)
        
        # Override args with resolved values
        args.local = use_local
        args.use_branch = use_branch
        args.custom_registry = use_custom_registry
        
        print(f"🔧 Build and Push Settings:")
        print(f"   Fork organization: {gh.get_fork_org()}")
        print(f"   Local mode: {args.local}")
        print(f"   Custom registry: {args.custom_registry}")
        if args.use_branch:
            print(f"   Using feature branch: {gh.get_branch_name()}")
        
        # Show which settings came from config defaults
        config_applied = []
        if build_defaults.get('local', False) and not hasattr(args, '_local_from_cli'):
            config_applied.append("--local")
        if build_defaults.get('use_branch', False) and not hasattr(args, '_use_branch_from_cli'):
            config_applied.append("--use-branch")
        if build_defaults.get('custom_registry', False) and not hasattr(args, '_custom_registry_from_cli'):
            config_applied.append("--custom-registry")
        
        if config_applied:
            print(f"   Config defaults applied: {', '.join(config_applied)}")
        
        # First, build the image
        # Force image mode for build
        build_args = type('BuildArgs', (), {
            'local': args.local,
            'use_branch': args.use_branch,
            'custom_registry': args.custom_registry,
            'manifests_only': False,  # Always build image, not just manifests
            'image': True  # Always build image
        })()
        
        print("🔨 Step 1: Building container image...")
        build_result = cmd_build_operator(build_args)
        
        if build_result != 0:
            print("❌ Build failed, skipping push step")
            return build_result
        
        print("✅ Build completed successfully!")
        
        # Then, push the image
        push_args = type('PushArgs', (), {
            'custom_registry': args.custom_registry
        })()
        
        print("📤 Step 2: Pushing container image...")
        push_result = cmd_image_push(push_args)
        
        if push_result == 0:
            print("🎉 Build and push completed successfully!")
        else:
            print("❌ Push failed!")
            
        return push_result
        
    except Exception as e:
        print(f"❌ Error in build-and-push: {e}")
        return 1


def cmd_forks_status(args):
    """Handle forks-status subcommand"""
    try:
        gh = GitHubWrapper()
        repos = gh.get_all_local_repositories()
        
        if not repos:
            print("No local repositories found in src/ directory")
            return 0
        
        print(f"📊 Repository Status ({len(repos)} repositories):")
        print()
        
        dirty_count = 0
        
        for repo_name in repos:
            repo_path = gh.src_dir / repo_name
            status = gh.get_repository_status(repo_path)
            
            # Skip clean repos if --dirty flag is used
            if args.dirty and status['clean']:
                continue
            
            if not status['clean']:
                dirty_count += 1
            
            # Display compact status
            status_icon = "🟢" if status['clean'] else "🟡"
            fork_org = gh.get_fork_org()
            
            print(f"{status_icon} {fork_org}/{repo_name}:{status['current_branch']}")
            
            # Show change summary if dirty
            if not status['clean']:
                changes = []
                if status['modified'] > 0:
                    changes.append(f"{status['modified']}M")
                if status['untracked'] > 0:
                    changes.append(f"{status['untracked']}U")
                if status['added'] > 0:
                    changes.append(f"{status['added']}A")
                if status['deleted'] > 0:
                    changes.append(f"{status['deleted']}D")
                
                if changes:
                    print(f"   Changes: {', '.join(changes)}")
            
            # Show detailed file list if requested
            if args.show_files and status['dirty_files']:
                print(f"   Files:")
                for file_status in status['dirty_files']:
                    print(f"     {file_status}")
            
            # Show remote URLs if verbose
            if args.verbose and status['remotes']:
                print(f"   Remotes:")
                for remote_name, remote_url in status['remotes'].items():
                    print(f"     {remote_name}: {remote_url}")
            
            print()
        
        # Summary
        if args.dirty:
            print(f"📈 Summary: {dirty_count} repositories with changes")
        else:
            clean_count = len(repos) - dirty_count
            print(f"📈 Summary: {clean_count} clean, {dirty_count} with changes")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error getting repository status: {e}")
        return 1


def cmd_forks_commit(args):
    """Handle forks-commit subcommand"""
    try:
        gh = GitHubWrapper()
        repos = gh.get_all_local_repositories()
        
        if not repos:
            print("No local repositories found in src/ directory")
            return 0
        
        message = args.message or "Gateway API migration changes"
        
        print(f"🚀 Committing and pushing changes across {len(repos)} repositories...")
        print(f"   Commit message: '{message}'")
        print()
        
        successful = []
        failed = []
        no_changes = []
        
        for repo_name in repos:
            repo_path = gh.src_dir / repo_name
            status = gh.get_repository_status(repo_path)
            
            print(f"📦 Processing {repo_name}...")
            
            if status['clean']:
                print(f"   ⏭️  No changes to commit")
                no_changes.append(repo_name)
                continue
            
            # Show what will be committed
            changes = []
            if status['modified'] > 0:
                changes.append(f"{status['modified']} modified")
            if status['untracked'] > 0:
                changes.append(f"{status['untracked']} untracked")
            if status['added'] > 0:
                changes.append(f"{status['added']} added")
            if status['deleted'] > 0:
                changes.append(f"{status['deleted']} deleted")
            
            print(f"   📝 Changes: {', '.join(changes)}")
            
            if gh.commit_and_push_repository(repo_path, message):
                print(f"   ✅ Successfully committed and pushed")
                successful.append(repo_name)
            else:
                print(f"   ❌ Failed to commit and push")
                failed.append(repo_name)
            
            print()
        
        # Summary
        print(f"📊 Commit Summary:")
        print(f"   ✅ Successful: {len(successful)}")
        print(f"   ❌ Failed: {len(failed)}")
        print(f"   ⏭️  No changes: {len(no_changes)}")
        
        if failed:
            print(f"\nFailed repositories:")
            for repo in failed:
                print(f"   - {repo}")
            return 1
        
        if successful:
            print(f"\n🎉 All repositories with changes have been committed and pushed!")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error committing repositories: {e}")
        return 1


def cmd_workflow(args):
    """Handle workflow subcommand with various operations"""
    try:
        workflow_engine = WorkflowEngine()
        
        # Determine which operation to perform based on flags
        if args.list:
            # List all workflows
            workflows = workflow_engine.list_workflows()
            
            if not workflows:
                print("No workflows found in workflows/ directory")
                return
            
            print("Available workflows:")
            print()
            
            for workflow_name in workflows:
                try:
                    workflow = workflow_engine.load_workflow(workflow_name)
                    includes_info = f" (includes: {', '.join(workflow.includes)})" if workflow.includes else ""
                    print(f"  {workflow_name}")
                    print(f"    Name: {workflow.name}")
                    print(f"    Description: {workflow.description}")
                    print(f"    Steps: {len(workflow.steps)}{includes_info}")
                    print()
                except Exception as e:
                    print(f"  {workflow_name}")
                    print(f"    Error: Could not load workflow: {e}")
                    print()
        
        elif args.show:
            # Show workflow details
            workflow = workflow_engine.load_workflow(args.show)
            
            print(f"Workflow: {workflow.name}")
            print(f"Description: {workflow.description}")
            print()
            
            if workflow.includes:
                print(f"Includes: {', '.join(workflow.includes)}")
                print()
            
            if workflow.variables:
                print("Workflow Variables:")
                for key, value in workflow.variables.items():
                    print(f"  {key}: {value}")
                print()
            
            print(f"Steps ({len(workflow.steps)}):")
            for i, step in enumerate(workflow.steps, 1):
                print(f"  {i}. {step.name}")
                print(f"     Type: {step.type}")
                print(f"     Command: {step.command}")
                if step.args:
                    print(f"     Args: {step.args}")
                if step.env:
                    print(f"     Environment: {step.env}")
                if step.ignore_errors:
                    print(f"     Ignore Errors: {step.ignore_errors}")
                if step.condition:
                    print(f"     Condition: {step.condition}")
                print()
        
        elif args.vars is not None:
            # Show workflow variables
            if args.vars:
                # Show variables for specific workflow
                print(f"Variables for workflow '{args.vars}':")
                print()
                
                final_vars = workflow_engine.preview_workflow_variables(args.vars)
                
                # Group variables by source
                config_vars = workflow_engine.get_available_variables()
                workflow_obj = workflow_engine.load_workflow(args.vars)
                workflow_vars = workflow_obj.variables or {}
                
                print("From config.yaml:")
                for key, value in sorted(config_vars.items()):
                    if key not in workflow_vars:
                        print(f"  {key}: {value}")
                
                if workflow_vars:
                    print("\nFrom workflow definition:")
                    for key, value in sorted(workflow_vars.items()):
                        print(f"  {key}: {value}")
                
                print(f"\nFinal merged variables ({len(final_vars)}):")
                for key, value in sorted(final_vars.items()):
                    print(f"  {key}: {value}")
            else:
                # Show all available config variables
                workflow_engine.show_available_variables()
        
        elif args.name:
            if not args.exec:
                print("Error: --name requires --exec to execute the workflow")
                return 1
            # Execute workflow
            # Parse runtime variables
            runtime_vars = {}
            if args.var:
                for var_def in args.var:
                    if '=' not in var_def:
                        print(f"Error: Invalid variable format '{var_def}'. Use KEY=VALUE")
                        return 1
                    key, value = var_def.split('=', 1)
                    runtime_vars[key] = value
            
            if args.verbose:
                print(f"Running workflow: {args.name}")
                if runtime_vars:
                    print("Runtime variables:")
                    for key, value in runtime_vars.items():
                        print(f"  {key}: {value}")
                print()
            
            # Execute the workflow
            success = workflow_engine.execute_workflow(args.name, runtime_vars)
            
            if success:
                print(f"\n✓ Workflow '{args.name}' completed successfully!")
                return 0
            else:
                print(f"\n✗ Workflow '{args.name}' failed!")
                return 1
        
        else:
            print("Error: Must specify one of --list, --show, --vars, or --name with --exec")
            return 1
        
    except FileNotFoundError as e:
        print(f"Error: Workflow not found: {e}")
        return 1
    except Exception as e:
        print(f"Error in workflow operation: {e}")
        return 1

def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description='OpenDataHub Gateway API Migration Tool',
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
        %(prog)s build-operator
        %(prog)s build-operator --manifests-only
        %(prog)s build-operator --local
        %(prog)s build-operator --image
        %(prog)s build-operator --image --custom-registry
        %(prog)s build-operator --use-branch --manifests-only
        %(prog)s build-operator --local --use-branch
        %(prog)s build-operator --image --local --use-branch --custom-registry
  %(prog)s build-and-push
  %(prog)s build-and-push --local
  %(prog)s build-and-push --use-branch
  %(prog)s build-and-push --custom-registry
  %(prog)s build-and-push --local --use-branch --custom-registry
  %(prog)s image-push
  %(prog)s image-push --custom-registry
  %(prog)s workflow --list
  %(prog)s workflow --show build-push-deploy
  %(prog)s workflow --name build --exec
  %(prog)s workflow --name build-push-deploy --exec --var REGISTRY_TAG=dev
  %(prog)s workflow --name deploy --exec --var NAMESPACE=test
  %(prog)s workflow --vars
  %(prog)s workflow --vars build-push-deploy
  %(prog)s list-repos opendatahub-io
  %(prog)s fork-repo opendatahub-io/odh-dashboard --clone
  %(prog)s fork-all --clone
  %(prog)s clone-repo opendatahub-io/odh-dashboard

Note: This tool can be run from anywhere within the project directory tree.
      It will automatically find config.yaml and .github_token files in the project root.
        """
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    # Create subparsers for different commands
    subparsers = parser.add_subparsers(
        dest='command',
        help='Available commands',
        required=True
    )
    
    # whoami subcommand
    whoami_parser = subparsers.add_parser(
        'whoami',
        help='Check GitHub authentication status'
    )
    whoami_parser.set_defaults(func=cmd_whoami)
    
    # show-config subcommand
    config_parser = subparsers.add_parser(
        'show-config',
        help='Display current configuration settings'
    )
    config_parser.set_defaults(func=cmd_show_config)
    
    # list-repos subcommand
    list_repos_parser = subparsers.add_parser(
        'list-repos',
        help='List repositories for a user or organization'
    )
    list_repos_parser.add_argument(
        'owner',
        help='GitHub username or organization name'
    )
    list_repos_parser.add_argument(
        '--limit',
        type=int,
        default=30,
        help='Maximum number of repositories to list (default: 30)'
    )
    list_repos_parser.set_defaults(func=cmd_list_repos)
    
    # fork-repo subcommand
    fork_repo_parser = subparsers.add_parser(
        'fork-repo',
        help='Fork a repository'
    )
    fork_repo_parser.add_argument(
        'repository',
        help='Repository to fork (e.g., opendatahub-io/odh-dashboard)'
    )
    fork_repo_parser.add_argument(
        '--clone',
        action='store_true',
        help='Clone the fork after creating it'
    )
    fork_repo_parser.set_defaults(func=cmd_fork_repo)
    
    # clone-repo subcommand
    clone_repo_parser = subparsers.add_parser(
        'clone-repo',
        help='Clone a repository'
    )
    clone_repo_parser.add_argument(
        'repository',
        help='Repository to clone (e.g., opendatahub-io/odh-dashboard)'
    )
    clone_repo_parser.set_defaults(func=cmd_clone_repo)
    
    # fork-all subcommand
    fork_all_parser = subparsers.add_parser(
        'fork-all',
        help='Fork all target repositories from configuration'
    )
    fork_all_parser.add_argument(
        '--clone',
        action='store_true',
        help='Clone repositories after forking'
    )
    fork_all_parser.set_defaults(func=cmd_fork_all)
    
    # setup-operator subcommand
    setup_operator_parser = subparsers.add_parser(
        'setup-operator',
        help='Set up OpenDataHub operator fork, clone, and feature branch'
    )
    setup_operator_parser.add_argument(
        '--force',
        action='store_true',
        help='Force setup even if local checkout exists'
    )
    setup_operator_parser.set_defaults(func=cmd_setup_operator)
    
    # setup-forks subcommand (alias for setup-manifests)
    setup_forks_parser = subparsers.add_parser(
        'setup-forks',
        help='Set up all required manifest repository forks'
    )
    setup_forks_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without making changes'
    )
    setup_forks_parser.add_argument(
        '--skip-existing',
        action='store_true',
        help='Skip repositories that already have local checkouts'
    )
    setup_forks_parser.set_defaults(func=cmd_setup_manifests)
    
    # build-operator subcommand
    build_operator_parser = subparsers.add_parser(
        'build-operator',
        help='Build opendatahub-operator using fork repositories and/or local checkouts (defaults configurable via config.yaml)'
    )
    build_operator_parser.add_argument(
        '--local',
        action='store_true',
        help='Use local checkouts for manifest sources instead of cloning'
    )
    build_operator_parser.add_argument(
        '--manifests-only',
        action='store_true',
        help='Only fetch manifests, do not build binary or image'
    )
    build_operator_parser.add_argument(
        '--image',
        action='store_true',
        help='Build container image instead of binary'
    )
    build_operator_parser.add_argument(
        '--use-branch',
        action='store_true',
        help='Use feature branch from config.yaml instead of main branch'
    )
    build_operator_parser.add_argument(
        '--custom-registry',
        action='store_true',
        help='Use custom registry settings from config.yaml'
    )
    build_operator_parser.set_defaults(func=cmd_build_operator)
    
    # build-and-push subcommand
    build_and_push_parser = subparsers.add_parser(
        'build-and-push',
        help='Build and push container image in one operation (combines build-operator --image + image-push)'
    )
    build_and_push_parser.add_argument(
        '--local',
        action='store_true',
        help='Use local checkouts for manifest sources instead of cloning'
    )
    build_and_push_parser.add_argument(
        '--use-branch',
        action='store_true',
        help='Use feature branch from config.yaml instead of main branch'
    )
    build_and_push_parser.add_argument(
        '--custom-registry',
        action='store_true',
        help='Use custom registry settings from config.yaml for build and push'
    )
    build_and_push_parser.set_defaults(func=cmd_build_and_push)
    
    # image-push subcommand
    image_push_parser = subparsers.add_parser(
        'image-push',
        help='Push built container image to registry'
    )
    image_push_parser.add_argument(
        '--custom-registry',
        action='store_true',
        help='Push to custom registry settings from config.yaml'
    )
    image_push_parser.set_defaults(func=cmd_image_push)
    
    # forks-status subcommand
    forks_status_parser = subparsers.add_parser(
        'forks-status',
        help='Show status of all local repository forks'
    )
    forks_status_parser.add_argument(
        '--dirty',
        action='store_true',
        help='Show only repositories with uncommitted changes'
    )
    forks_status_parser.add_argument(
        '--show-files',
        action='store_true',
        help='Show detailed file changes for dirty repositories'
    )
    forks_status_parser.set_defaults(func=cmd_forks_status)
    
    # forks-commit subcommand
    forks_commit_parser = subparsers.add_parser(
        'forks-commit',
        help='Commit and push changes across all local repositories'
    )
    forks_commit_parser.add_argument(
        '-m', '--message',
        help='Commit message (default: "Gateway API migration changes")'
    )
    forks_commit_parser.set_defaults(func=cmd_forks_commit)
    
    # Workflow subcommand with multiple operations
    workflow_parser = subparsers.add_parser(
        'workflow',
        help='Workflow management operations'
    )
    
    # Create mutually exclusive group for main operations
    workflow_group = workflow_parser.add_mutually_exclusive_group(required=True)
    
    workflow_group.add_argument(
        '--list',
        action='store_true',
        help='List all available workflows'
    )
    
    workflow_group.add_argument(
        '--show',
        metavar='NAME',
        help='Show details of a specific workflow'
    )
    
    workflow_group.add_argument(
        '--vars',
        nargs='?',
        const='',
        metavar='NAME',
        help='Show workflow variables (all config vars if no name specified)'
    )
    
    workflow_group.add_argument(
        '--name',
        metavar='NAME',
        help='Specify workflow name for execution (requires --exec)'
    )
    
    # Additional flags for workflow execution
    workflow_parser.add_argument(
        '--exec',
        action='store_true',
        help='Execute the workflow specified by --name'
    )
    
    workflow_parser.add_argument(
        '--var',
        action='append',
        metavar='KEY=VALUE',
        help='Set workflow variables (format: KEY=VALUE). Can be used multiple times.'
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