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
- Batch operations across multiple target repositories
- Configuration-driven development environment management
- YAML-based workflow execution for build/deploy operations

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
        
        # Fork the repository
        print(f"🔄 Forking {args.repository}...")
        fork_result = gh.fork_repository(args.repository)
        
        if fork_result['created']:
            print(f"✅ Fork created: {fork_result['fork_url']}")
        else:
            print(f"ℹ️  Fork already exists: {fork_result['fork_url']}")
        
        # Clone if requested
        if args.clone:
            print(f"🔄 Cloning fork...")
            clone_result = gh.clone_repository(args.repository)
            
            if clone_result['cloned']:
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
        
        if result['cloned']:
            print(f"✅ Repository cloned to: {result['local_path']}")
        else:
            print(f"ℹ️  Repository already exists at: {result['local_path']}")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error cloning repository: {e}")
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
        github_config = config.get('github', {})
        print(f"  Fork Organization: {github_config.get('fork_org', 'N/A')}")
        print(f"  Feature Branch: {github_config.get('feature_branch', 'N/A')}")
        print()
        
        print("🎯 Target Repositories:")
        repos = config.get('repositories', {})
        for category, repo_list in repos.items():
            print(f"  {category}:")
            for repo in repo_list:
                if isinstance(repo, dict):
                    print(f"    • {repo.get('name', 'N/A')}")
                else:
                    print(f"    • {repo}")
        print()
        
        print("🐳 Registry Settings:")
        registry_config = config.get('registry', {})
        print(f"  URL: {registry_config.get('url', 'N/A')}")
        print(f"  Namespace: {registry_config.get('namespace', 'N/A')}")
        print(f"  Tag: {registry_config.get('tag', 'N/A')}")
        print()
        
        print("🏗️ Build Settings:")
        build_config = config.get('build', {})
        print(f"  Local Mode: {build_config.get('local', 'N/A')}")
        print(f"  Use Branch: {build_config.get('use_branch', 'N/A')}")
        print(f"  Build Image: {build_config.get('image', 'N/A')}")
        print(f"  Custom Registry: {build_config.get('custom_registry', 'N/A')}")
        print(f"  Manifests Only: {build_config.get('manifests_only', 'N/A')}")
        print()
        
        print("🔄 Migration Settings:")
        migration_config = config.get('migration', {})
        print(f"  Target API: {migration_config.get('target_api', 'N/A')}")
        print(f"  Source Path: {migration_config.get('source_path', 'N/A')}")
        print(f"  Pattern: {migration_config.get('pattern', 'N/A')}")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error loading configuration: {e}")
        return 1


def cmd_fork_all(args):
    """Handle fork-all subcommand"""
    try:
        gh = GitHubWrapper()
        
        print("🔄 Forking all target repositories...")
        results = []
        
        # Get all repository names from config
        repos = config.get('repositories', {})
        
        for category, repo_list in repos.items():
            print(f"\n📂 Processing {category} repositories:")
            
            for repo in repo_list:
                if isinstance(repo, dict):
                    repo_name = repo.get('name', '')
                else:
                    repo_name = repo
                
                if not repo_name:
                    continue
                
                try:
                    print(f"  🔄 Forking {repo_name}...")
                    fork_result = gh.fork_repository(repo_name)
                    
                    if fork_result['created']:
                        print(f"    ✅ Fork created: {fork_result['fork_url']}")
                    else:
                        print(f"    ℹ️  Fork already exists: {fork_result['fork_url']}")
                    
                    # Clone if requested
                    if args.clone:
                        print(f"    🔄 Cloning fork...")
                        clone_result = gh.clone_repository(repo_name)
                        
                        if clone_result['cloned']:
                            print(f"    ✅ Repository cloned to: {clone_result['local_path']}")
                        else:
                            print(f"    ℹ️  Repository already exists at: {clone_result['local_path']}")
                    
                    results.append({'repo': repo_name, 'success': True})
                    
                except Exception as e:
                    print(f"    ❌ Error processing {repo_name}: {e}")
                    results.append({'repo': repo_name, 'success': False, 'error': str(e)})
        
        # Summary
        successful = sum(1 for r in results if r['success'])
        failed = len(results) - successful
        
        print(f"\n📊 Summary:")
        print(f"  ✅ Successful: {successful}")
        print(f"  ❌ Failed: {failed}")
        
        if failed > 0:
            print("\n❌ Failed repositories:")
            for r in results:
                if not r['success']:
                    print(f"  • {r['repo']}: {r.get('error', 'Unknown error')}")
        
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
        repo_name = operator_repo.split('/')[-1]
        local_path = gh.project_root / "src" / repo_name
        
        if local_path.exists() and not args.force:
            print(f"ℹ️  Local checkout already exists at: {local_path}")
            print("   Use --force to recreate or proceed with existing checkout")
            return 0
        
        # Step 1: Fork repository
        print("📋 Step 1: Forking repository...")
        fork_result = gh.fork_repository(operator_repo)
        
        if fork_result['created']:
            print(f"✅ Fork created: {fork_result['fork_url']}")
        else:
            print(f"ℹ️  Fork already exists: {fork_result['fork_url']}")
        
        # Step 2: Clone fork
        print("📋 Step 2: Cloning fork...")
        clone_result = gh.clone_repository(operator_repo)
        
        if clone_result['cloned']:
            print(f"✅ Repository cloned to: {clone_result['local_path']}")
        else:
            print(f"ℹ️  Repository already exists at: {clone_result['local_path']}")
        
        # Step 3: Setup upstream and rebase
        print("📋 Step 3: Setting up upstream and rebasing...")
        gh.setup_upstream(operator_repo)
        
        # Step 4: Create feature branch
        print("📋 Step 4: Creating feature branch...")
        feature_branch = gh.config['github']['feature_branch']
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
            local_path = gh.project_root / "src" / repo_name.split('/')[-1]
            
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
                
                if fork_result['created']:
                    print(f"    ✅ Fork created: {fork_result['fork_url']}")
                    # Add delay after fork creation to prevent race conditions
                    time.sleep(3)
                else:
                    print(f"    ℹ️  Fork already exists: {fork_result['fork_url']}")
                
                # Step 2: Clone fork
                print(f"  🔄 Cloning fork...")
                clone_result = gh.clone_repository(repo_name)
                
                if clone_result['cloned']:
                    print(f"    ✅ Repository cloned to: {clone_result['local_path']}")
                else:
                    print(f"    ℹ️  Repository already exists at: {clone_result['local_path']}")
                
                # Step 3: Setup upstream and rebase
                print(f"  🔄 Setting up upstream and rebasing...")
                gh.setup_upstream(repo_name, repo_info.base_branch)
                
                # Step 4: Create feature branch
                print(f"  🔄 Creating feature branch...")
                feature_branch = gh.config['github']['feature_branch']
                gh.create_branch(repo_name, feature_branch, repo_info.base_branch)
                
                print(f"    ✅ Setup complete for {repo_name}")
                results.append({'repo': repo_name, 'success': True})
                
            except Exception as e:
                print(f"    ❌ Error processing {repo_name}: {e}")
                results.append({'repo': repo_name, 'success': False, 'error': str(e)})
        
        # Summary
        successful = sum(1 for r in results if r['success'])
        failed = len(results) - successful
        
        print(f"\n📊 Summary:")
        print(f"  📂 Processed: {processed}")
        print(f"  ⏭️  Skipped: {skipped}")
        print(f"  ✅ Successful: {successful}")
        print(f"  ❌ Failed: {failed}")
        
        if failed > 0:
            print("\n❌ Failed repositories:")
            for r in results:
                if not r['success']:
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
                    check=True
                )
                current_branch = result.stdout.strip()
                
                # Get status
                result = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=repo_dir,
                    capture_output=True,
                    text=True,
                    check=True
                )
                status_lines = result.stdout.strip().split('\n') if result.stdout.strip() else []
                
                # Count changes by type
                modified = len([line for line in status_lines if line.startswith(' M')])
                added = len([line for line in status_lines if line.startswith('A')])
                deleted = len([line for line in status_lines if line.startswith(' D')])
                untracked = len([line for line in status_lines if line.startswith('??')])
                
                is_dirty = len(status_lines) > 0
                
                # Get remote URLs
                try:
                    result = subprocess.run(
                        ["git", "remote", "-v"],
                        cwd=repo_dir,
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    remotes = result.stdout.strip()
                    
                    origin_url = "N/A"
                    upstream_url = "N/A"
                    
                    for line in remotes.split('\n'):
                        if line.startswith('origin') and '(fetch)' in line:
                            origin_url = line.split()[1]
                        elif line.startswith('upstream') and '(fetch)' in line:
                            upstream_url = line.split()[1]
                
                except:
                    origin_url = upstream_url = "N/A"
                
                # Get fork org from origin URL
                fork_org = "N/A"
                if 'github.com' in origin_url:
                    try:
                        if origin_url.startswith('git@'):
                            # SSH format: git@github.com:org/repo.git
                            fork_org = origin_url.split(':')[1].split('/')[0]
                        else:
                            # HTTPS format: https://github.com/org/repo.git
                            fork_org = origin_url.split('/')[-2]
                    except:
                        pass
                
                repo_info = {
                    'name': repo_name,
                    'branch': current_branch,
                    'is_dirty': is_dirty,
                    'modified': modified,
                    'added': added,
                    'deleted': deleted,
                    'untracked': untracked,
                    'origin_url': origin_url,
                    'upstream_url': upstream_url,
                    'fork_org': fork_org,
                    'status_lines': status_lines
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
            status_icon = "🔄" if repo_info['is_dirty'] else "✅"
            changes = []
            
            if repo_info['modified'] > 0:
                changes.append(f"{repo_info['modified']}M")
            if repo_info['added'] > 0:
                changes.append(f"{repo_info['added']}A")
            if repo_info['deleted'] > 0:
                changes.append(f"{repo_info['deleted']}D")
            if repo_info['untracked'] > 0:
                changes.append(f"{repo_info['untracked']}U")
            
            change_summary = f" ({', '.join(changes)})" if changes else ""
            
            print(f"{status_icon} {repo_info['fork_org']}/{repo_info['name']}:{repo_info['branch']}{change_summary}")
            
            # Show detailed file changes if requested
            if args.show_files and repo_info['is_dirty']:
                for line in repo_info['status_lines']:
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
            print(f"📊 Summary: {total} repositories ({clean_count} clean, {dirty_count} dirty)")
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
                    check=True
                )
                
                if not result.stdout.strip():
                    print(f"    ℹ️  No changes to commit")
                    results.append({'repo': repo_name, 'status': 'no_changes'})
                    continue
                
                # Add all changes
                print(f"    📋 Adding changes...")
                subprocess.run(
                    ["git", "add", "."],
                    cwd=repo_dir,
                    check=True
                )
                
                # Commit changes
                print(f"    💾 Committing changes...")
                subprocess.run(
                    ["git", "commit", "-m", commit_message],
                    cwd=repo_dir,
                    check=True
                )
                
                # Push changes
                print(f"    🚀 Pushing changes...")
                subprocess.run(
                    ["git", "push", "origin"],
                    cwd=repo_dir,
                    check=True
                )
                
                print(f"    ✅ Successfully committed and pushed changes")
                results.append({'repo': repo_name, 'status': 'success'})
                
            except subprocess.CalledProcessError as e:
                print(f"    ❌ Error committing {repo_name}: {e}")
                results.append({'repo': repo_name, 'status': 'error', 'error': str(e)})
            except Exception as e:
                print(f"    ❌ Unexpected error with {repo_name}: {e}")
                results.append({'repo': repo_name, 'status': 'error', 'error': str(e)})
        
        # Summary
        successful = sum(1 for r in results if r['status'] == 'success')
        no_changes = sum(1 for r in results if r['status'] == 'no_changes')
        failed = sum(1 for r in results if r['status'] == 'error')
        
        print(f"\n📊 Summary:")
        print(f"  ✅ Successful: {successful}")
        print(f"  ℹ️  No changes: {no_changes}")
        print(f"  ❌ Failed: {failed}")
        
        if failed > 0:
            print("\n❌ Failed repositories:")
            for r in results:
                if r['status'] == 'error':
                    print(f"  • {r['repo']}: {r.get('error', 'Unknown error')}")
        
        return 0 if failed == 0 else 1
        
    except Exception as e:
        print(f"❌ Error in forks-commit operation: {e}")
        return 1


def cmd_workflow(args):
    """Handle workflow subcommand with multiple operations"""
    try:
        engine = WorkflowEngine()
        
        # Handle --list operation
        if args.list:
            workflow_names = engine.list_workflows()
            if not workflow_names:
                print("No workflows found in workflows/ directory")
                return 0
            
            print("Available workflows:")
            for workflow_name in workflow_names:
                try:
                    workflow = engine.load_workflow(workflow_name)
                    print(f"  • {workflow.name} - {workflow.description}")
                    if workflow.includes:
                        print(f"    Includes: {', '.join(workflow.includes)}")
                    print(f"    Steps: {len(workflow.steps)}")
                    print()
                except Exception as e:
                    print(f"  • {workflow_name} - Error loading workflow: {e}")
                    print()
            return 0
        
        # Handle --vars operation
        if args.vars is not None:
            if args.vars == '':
                # Show all config variables
                engine.show_available_variables()
            else:
                # Show specific workflow variables
                try:
                    variables = engine.preview_workflow_variables(args.vars)
                    print(f"Variables for workflow '{args.vars}':")
                    for key, value in variables.items():
                        print(f"  {key}: {value}")
                except Exception as e:
                    print(f"❌ Error loading workflow '{args.vars}': {e}")
                    return 1
            return 0
        
        # Handle --show operation
        if args.show:
            try:
                workflow = engine.load_workflow(args.show)
                print(f"Workflow: {workflow.name}")
                print(f"Description: {workflow.description}")
                
                if workflow.includes:
                    print(f"Includes: {', '.join(workflow.includes)}")
                
                if workflow.variables:
                    print("\nWorkflow Variables:")
                    for key, value in workflow.variables.items():
                        print(f"  {key}: {value}")
                
                print(f"\nSteps ({len(workflow.steps)}):")
                for i, step in enumerate(workflow.steps, 1):
                    print(f"  {i}. {step.name}")
                    print(f"     Type: {step.type}")
                    if step.type == 'kubectl':
                        print(f"     Command: kubectl {step.command} {' '.join(step.args)}")
                    elif step.type == 'tool':
                        print(f"     Command: ./tool.py {step.command} {' '.join(step.args)}")
                    elif step.type == 'shell':
                        print(f"     Command: {step.command} {' '.join(step.args)}")
                    elif step.type == 'workflow':
                        print(f"     Workflow: {step.workflow_name}")
                    
                    if step.env:
                        print(f"     Environment: {step.env}")
                    if step.ignore_errors:
                        print(f"     Ignore errors: True")
                    print()
                
                return 0
            except Exception as e:
                print(f"❌ Error loading workflow '{args.show}': {e}")
                return 1
        
        # Handle --name operation (requires --exec)
        if args.name:
            if not args.exec:
                print("❌ --name requires --exec flag to execute the workflow")
                return 1
            
            # Parse runtime variables
            runtime_vars = {}
            if args.var:
                for var_assignment in args.var:
                    if '=' not in var_assignment:
                        print(f"❌ Invalid variable format: {var_assignment} (expected KEY=VALUE)")
                        return 1
                    key, value = var_assignment.split('=', 1)
                    runtime_vars[key] = value
            
            # Execute workflow
            try:
                print(f"🔄 Executing workflow: {args.name}")
                if runtime_vars:
                    print(f"📋 Runtime variables: {runtime_vars}")
                print()
                
                success = engine.execute_workflow(args.name, runtime_vars)
                
                if success:
                    print(f"\n✅ Workflow '{args.name}' completed successfully")
                    return 0
                else:
                    print(f"\n❌ Workflow '{args.name}' failed")
                    return 1
                    
            except Exception as e:
                print(f"❌ Error executing workflow '{args.name}': {e}")
                return 1
        
        # If we get here, no valid operation was specified
        print("❌ No operation specified. Use --list, --show, --vars, or --name with --exec")
        return 1
        
    except Exception as e:
        print(f"❌ Error in workflow operation: {e}")
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
        
For build and deployment operations, use the workflow system:
  %(prog)s workflow --name build --exec                    # Build operator
  %(prog)s workflow --name build-push --exec               # Build and push
  %(prog)s workflow --name push --exec                     # Push image
  %(prog)s workflow --name deploy --exec                   # Deploy to cluster
  %(prog)s workflow --name build-push-deploy --exec        # Full pipeline
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