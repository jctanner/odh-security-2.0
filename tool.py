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
from dataclasses import dataclass


@dataclass
class RepoInfo:
    """Data class for repository information"""
    owner: str
    name: str
    url: str
    fork_owner: Optional[str] = None


class GitHubWrapper:
    """
    Object-oriented wrapper for GitHub CLI operations
    
    This class provides methods for common GitHub operations needed for the
    OpenDataHub Gateway API migration project, including repository forking,
    cloning, and branch management.
    """
    
    def __init__(self, token_file: str = ".github_token", src_dir: str = "src", config_file: str = "config.yaml"):
        """
        Initialize the GitHub wrapper
        
        Args:
            token_file (str): Path to file containing GitHub token
            src_dir (str): Directory for repository checkouts
            config_file (str): Path to YAML configuration file
        """
        self.token_file = Path(token_file)
        self.config_file = Path(config_file)
        self.logger = self._setup_logging()
        
        # Find and store config file path
        self.config_file_path = self._find_config_file()
        project_root = self.config_file_path.parent
        
        # Set src_dir relative to project root (where config file is found)
        self.src_dir = project_root / src_dir
        
        # Ensure src directory exists
        self.src_dir.mkdir(exist_ok=True)
        
        # Load configuration
        self.config = self._load_config()
        
        # Load and set GitHub token
        self._load_github_token()
    
    def _setup_logging(self) -> logging.Logger:
        """Setup logging configuration"""
        logger = logging.getLogger("github_wrapper")
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    def _load_config(self) -> Dict[str, Any]:
        """
        Load configuration from YAML file
        
        Returns:
            Dict containing configuration settings
            
        Raises:
            FileNotFoundError: If config file doesn't exist
            yaml.YAMLError: If config file has invalid YAML
        """
        try:
            with open(self.config_file_path, 'r') as f:
                config = yaml.safe_load(f)
            
            self.logger.info(f"Configuration loaded from {self.config_file_path}")
            return config
            
        except yaml.YAMLError as e:
            self.logger.error(f"Invalid YAML in config file: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Failed to load configuration: {e}")
            raise
    
    def _find_config_file(self) -> Path:
        """
        Find the config file by searching up the directory tree
        
        Returns:
            Path to config file
            
        Raises:
            FileNotFoundError: If config file is not found
        """
        current_dir = Path.cwd()
        config_name = self.config_file.name
        
        # First, try the explicitly specified path
        if self.config_file.exists():
            return self.config_file
        
        # If not found, search up the directory tree
        search_dir = current_dir
        while search_dir != search_dir.parent:
            candidate = search_dir / config_name
            if candidate.exists():
                self.logger.info(f"Found config file: {candidate}")
                return candidate
            search_dir = search_dir.parent
        
        # Try root directory
        root_candidate = search_dir / config_name
        if root_candidate.exists():
            self.logger.info(f"Found config file: {root_candidate}")
            return root_candidate
        
        raise FileNotFoundError(f"Configuration file '{config_name}' not found in current directory or any parent directory")
    
    def _load_github_token(self) -> None:
        """
        Load GitHub token from file and set environment variable
        
        Raises:
            FileNotFoundError: If token file doesn't exist
            ValueError: If token file is empty
        """
        token_file = self._find_token_file()
        
        try:
            with open(token_file, 'r') as f:
                token = f.read().strip()
            
            if not token or token.startswith('#'):
                raise ValueError("Token file is empty or contains only comments")
            
            # Set environment variable for gh CLI
            os.environ['GITHUB_TOKEN'] = token
            self.logger.info("GitHub token loaded successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to load GitHub token: {e}")
            raise
    
    def _find_token_file(self) -> Path:
        """
        Find the token file by searching up the directory tree
        
        Returns:
            Path to token file
            
        Raises:
            FileNotFoundError: If token file is not found
        """
        current_dir = Path.cwd()
        token_name = self.token_file.name
        
        # First, try the explicitly specified path
        if self.token_file.exists():
            return self.token_file
        
        # If not found, search up the directory tree
        search_dir = current_dir
        while search_dir != search_dir.parent:
            candidate = search_dir / token_name
            if candidate.exists():
                self.logger.info(f"Found token file: {candidate}")
                return candidate
            search_dir = search_dir.parent
        
        # Try root directory
        root_candidate = search_dir / token_name
        if root_candidate.exists():
            self.logger.info(f"Found token file: {root_candidate}")
            return root_candidate
        
        raise FileNotFoundError(f"Token file '{token_name}' not found in current directory or any parent directory")
    
    def _run_command(self, command: List[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
        """
        Execute a command with proper error handling
        
        Args:
            command: List of command arguments
            cwd: Working directory for command execution
            
        Returns:
            CompletedProcess: Result of command execution
            
        Raises:
            subprocess.CalledProcessError: If command fails
        """
        cwd = cwd or Path.cwd()
        
        self.logger.info(f"Executing: {' '.join(command)} (cwd: {cwd})")
        
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                check=True
            )
            
            if result.stdout:
                self.logger.debug(f"Command output: {result.stdout}")
            
            return result
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Command failed: {e}")
            self.logger.error(f"Error output: {e.stderr}")
            raise
    
    def fork_repository(self, repo_url: str, clone_after_fork: bool = True) -> RepoInfo:
        """
        Fork a repository using GitHub CLI, creating fork under configured organization
        
        Args:
            repo_url: GitHub repository URL (e.g., "opendatahub-io/odh-dashboard" or just "odh-dashboard")
            clone_after_fork: Whether to clone the fork after creating it
            
        Returns:
            RepoInfo: Information about the forked repository
        """
        self.logger.info(f"Forking repository: {repo_url}")
        
        # Parse repository owner and name
        if repo_url.startswith("https://github.com/"):
            repo_path = repo_url.replace("https://github.com/", "").rstrip("/")
        else:
            repo_path = repo_url
        
        # Handle case where only repository name is provided
        if "/" not in repo_path:
            repo_path = f"opendatahub-io/{repo_path}"
        
        owner, name = repo_path.split("/")
        
        # Get the configured fork organization
        fork_org = self.get_fork_org()
        
        # Fork the repository to the specified organization
        fork_command = ["gh", "repo", "fork", repo_path, "--org", fork_org]
        if clone_after_fork:
            fork_command.append("--clone")
        
        self._run_command(fork_command, cwd=self.src_dir)
        
        repo_info = RepoInfo(
            owner=owner,
            name=name,
            url=f"https://github.com/{repo_path}",
            fork_owner=fork_org
        )
        
        self.logger.info(f"Successfully forked {repo_path} as {fork_org}/{name}")
        return repo_info
    
    def clone_repository(self, repo_url: str, directory_name: Optional[str] = None) -> Path:
        """
        Clone a repository to the src directory using SSH origin
        
        Args:
            repo_url: GitHub repository URL (owner/repo format)
            directory_name: Custom directory name (defaults to repo name)
            
        Returns:
            Path: Path to cloned repository
        """
        self.logger.info(f"Cloning repository: {repo_url}")
        
        # Parse repository path
        if repo_url.startswith("https://github.com/"):
            repo_path = repo_url.replace("https://github.com/", "").rstrip("/")
        else:
            repo_path = repo_url
        
        # Determine directory name
        if not directory_name:
            directory_name = repo_path.split("/")[-1].replace(".git", "")
        
        clone_path = self.src_dir / directory_name
        
        # Convert to SSH URL for origin
        ssh_url = f"git@github.com:{repo_path}.git"
        
        # Clone the repository using SSH
        clone_command = ["git", "clone", ssh_url, str(directory_name)]
        self._run_command(clone_command, cwd=self.src_dir)
        
        self.logger.info(f"Repository cloned to: {clone_path}")
        return clone_path
    
    def create_branch(self, repo_path: Path, branch_name: str, base_branch: str = "main") -> None:
        """
        Create a new branch in a repository
        
        Args:
            repo_path: Path to local repository
            branch_name: Name of new branch
            base_branch: Base branch to create from
        """
        self.logger.info(f"Creating branch '{branch_name}' in {repo_path}")
        
        # Ensure we're on the base branch and it's up to date
        # Use origin/base_branch to avoid ambiguity when both origin and upstream have the same branch
        self._run_command(["git", "checkout", "-B", base_branch, f"origin/{base_branch}"], cwd=repo_path)
        self._run_command(["git", "pull", "origin", base_branch], cwd=repo_path)
        
        # Create and checkout new branch
        self._run_command(["git", "checkout", "-b", branch_name], cwd=repo_path)
        
        self.logger.info(f"Branch '{branch_name}' created successfully")
    
    def setup_upstream(self, repo_path: Path, upstream_url: str) -> None:
        """
        Setup upstream remote for a forked repository
        
        Args:
            repo_path: Path to local repository
            upstream_url: URL of upstream repository
        """
        self.logger.info(f"Setting up upstream remote: {upstream_url}")
        
        # Add upstream remote
        self._run_command(["git", "remote", "add", "upstream", upstream_url], cwd=repo_path)
        
        # Fetch upstream
        self._run_command(["git", "fetch", "upstream"], cwd=repo_path)
        
        self.logger.info("Upstream remote configured successfully")
    
    def get_repository_info(self, repo_path: str) -> Dict[str, Any]:
        """
        Get information about a repository using GitHub CLI
        
        Args:
            repo_path: Repository path (owner/name)
            
        Returns:
            Dict containing repository information
        """
        self.logger.info(f"Getting repository info: {repo_path}")
        
        result = self._run_command(["gh", "repo", "view", repo_path, "--json", "name,owner,url,defaultBranch,isPrivate"])
        
        import json
        return json.loads(result.stdout)
    
    def list_repositories(self, owner: str, limit: int = 30) -> List[Dict[str, Any]]:
        """
        List repositories for a given owner
        
        Args:
            owner: GitHub username or organization
            limit: Maximum number of repositories to return
            
        Returns:
            List of repository information dictionaries
        """
        self.logger.info(f"Listing repositories for: {owner}")
        
        result = self._run_command([
            "gh", "repo", "list", owner, 
            "--limit", str(limit),
            "--json", "name,owner,url,defaultBranch,isPrivate"
        ])
        
        import json
        return json.loads(result.stdout)
    
    def whoami(self) -> Dict[str, Any]:
        """
        Check authentication status and get current user information
        
        Returns:
            Dict containing current user information
            
        Raises:
            subprocess.CalledProcessError: If authentication fails
        """
        self.logger.info("Checking authentication status")
        
        result = self._run_command(["gh", "api", "user"])
        
        import json
        user_data = json.loads(result.stdout)
        
        self.logger.info(f"Authenticated as: {user_data['login']} ({user_data['name']})")
        return user_data
    
    def get_fork_org(self) -> str:
        """Get the fork organization from configuration"""
        return self.config.get('github', {}).get('fork_org', 'jctanner')
    
    def get_branch_name(self) -> str:
        """Get the migration branch name from configuration"""
        return self.config.get('github', {}).get('branch_name', 'gateway-api-migration')
    
    def get_base_branch(self) -> str:
        """Get the base branch name from configuration"""
        return self.config.get('github', {}).get('base_branch', 'main')
    
    def get_target_repositories(self) -> List[str]:
        """Get the list of target repositories from configuration"""
        return self.config.get('target_repositories', [])
    
    def should_auto_create_branch(self) -> bool:
        """Check if branches should be automatically created after forking"""
        return self.config.get('migration', {}).get('auto_create_branch', True)
    
    def should_setup_upstream(self) -> bool:
        """Check if upstream remotes should be automatically set up"""
        return self.config.get('migration', {}).get('setup_upstream', True)

    def get_registry_url(self) -> str:
        """Get the container registry URL from configuration"""
        return self.config.get('registry', {}).get('url', 'quay.io')

    def get_registry_namespace(self) -> str:
        """Get the registry namespace/organization from configuration"""
        return self.config.get('registry', {}).get('namespace', 'opendatahub')

    def get_registry_tag(self) -> str:
        """Get the default image tag from configuration"""
        return self.config.get('registry', {}).get('tag', 'latest')

    def get_full_image_name(self, image_name: str) -> str:
        """Get full image name with registry, namespace, and tag"""
        registry_url = self.get_registry_url()
        namespace = self.get_registry_namespace()
        tag = self.get_registry_tag()
        
        # Remove any existing registry prefix from image_name
        if "/" in image_name:
            image_name = image_name.split("/")[-1]
        
        return f"{registry_url}/{namespace}/{image_name}:{tag}"

    def get_build_defaults(self) -> Dict[str, bool]:
        """Get build configuration defaults"""
        build_config = self.config.get("build", {})
        return {
            "local": build_config.get("local", False),
            "use_branch": build_config.get("use_branch", False),
            "image": build_config.get("image", False),
            "custom_registry": build_config.get("custom_registry", False),
            "manifests_only": build_config.get("manifests_only", False),
        }

    def get_build_local_default(self) -> bool:
        """Get default value for --local flag"""
        return self.config.get("build", {}).get("local", False)

    def get_build_use_branch_default(self) -> bool:
        """Get default value for --use-branch flag"""
        return self.config.get("build", {}).get("use_branch", False)

    def get_build_image_default(self) -> bool:
        """Get default value for --image flag"""
        return self.config.get("build", {}).get("image", False)

    def get_build_custom_registry_default(self) -> bool:
        """Get default value for --custom-registry flag"""
        return self.config.get("build", {}).get("custom_registry", False)

    def get_build_manifests_only_default(self) -> bool:
        """Get default value for --manifests-only flag"""
        return self.config.get("build", {}).get("manifests_only", False)

    def fork_exists(self, repo_path: str) -> bool:
        """
        Check if a fork exists for the given repository
        
        Args:
            repo_path: Repository path (e.g., "opendatahub-io/opendatahub-operator")
            
        Returns:
            bool: True if fork exists, False otherwise
        """
        try:
            fork_org = self.get_fork_org()
            owner, name = repo_path.split("/")
            fork_path = f"{fork_org}/{name}"
            
            self.logger.info(f"Checking if fork exists: {fork_path}")
            
            # Try to get repository info - if it fails, fork doesn't exist
            self._run_command(["gh", "repo", "view", fork_path, "--json", "name"])
            
            self.logger.info(f"Fork exists: {fork_path}")
            return True
            
        except subprocess.CalledProcessError:
            self.logger.info(f"Fork does not exist: {fork_path}")
            return False
    
    def local_checkout_exists(self, repo_name: str) -> bool:
        """
        Check if a local checkout exists in the src directory
        
        Args:
            repo_name: Repository name (e.g., "opendatahub-operator")
            
        Returns:
            bool: True if local checkout exists, False otherwise
        """
        checkout_path = self.src_dir / repo_name
        exists = checkout_path.exists() and checkout_path.is_dir()
        
        self.logger.info(f"Local checkout {'exists' if exists else 'does not exist'}: {checkout_path}")
        return exists
    
    def rebase_from_upstream(self, repo_path: Path, base_branch: str = None) -> None:
        """
        Rebase the local repository from upstream
        
        Args:
            repo_path: Path to local repository
            base_branch: Base branch to rebase from (defaults to configured base branch)
        """
        if base_branch is None:
            base_branch = self.get_base_branch()
        
        self.logger.info(f"Rebasing {repo_path} from upstream/{base_branch}")
        
        # Fetch upstream
        self._run_command(["git", "fetch", "upstream"], cwd=repo_path)
        
        # Checkout base branch using explicit origin reference to avoid ambiguity
        self._run_command(["git", "checkout", "-B", base_branch, f"origin/{base_branch}"], cwd=repo_path)
        
        # Rebase from upstream
        self._run_command(["git", "rebase", f"upstream/{base_branch}"], cwd=repo_path)
        
        # Push the updated base branch to origin
        self._run_command(["git", "push", "origin", base_branch], cwd=repo_path)
        
        self.logger.info(f"Successfully rebased from upstream/{base_branch}")
    
    def branch_exists(self, repo_path: Path, branch_name: str) -> bool:
        """
        Check if a branch exists in the repository
        
        Args:
            repo_path: Path to local repository
            branch_name: Name of branch to check
            
        Returns:
            bool: True if branch exists, False otherwise
        """
        try:
            result = self._run_command(["git", "branch", "--list", branch_name], cwd=repo_path)
            exists = bool(result.stdout.strip())
            
            self.logger.info(f"Branch '{branch_name}' {'exists' if exists else 'does not exist'} in {repo_path}")
            return exists
            
        except subprocess.CalledProcessError:
            return False
    
    def _update_manifest_sources(self, operator_path: Path, fork_org: str) -> None:
        """
        Update get_all_manifests.sh to use fork organization instead of opendatahub-io
        
        Args:
            operator_path: Path to opendatahub-operator directory
            fork_org: Fork organization name to use
        """
        manifest_script = operator_path / "get_all_manifests.sh"
        
        if not manifest_script.exists():
            self.logger.warning(f"get_all_manifests.sh not found at {manifest_script}")
            return
        
        self.logger.info(f"Updating manifest sources to use fork org: {fork_org}")
        
        # Read the current script
        with open(manifest_script, 'r') as f:
            content = f.read()
        
        # Create a backup
        backup_script = operator_path / "get_all_manifests.sh.backup"
        with open(backup_script, 'w') as f:
            f.write(content)
        
        # Replace opendatahub-io with fork organization in the COMPONENT_MANIFESTS array
        import re
        
        # Pattern to match lines like: ["component"]="opendatahub-io:repo:ref:path"
        pattern = r'(\["[^"]+"\]=")(opendatahub-io)(:)'
        replacement = rf'\1{fork_org}\3'
        
        updated_content = re.sub(pattern, replacement, content)
        
        # Write the updated script
        with open(manifest_script, 'w') as f:
            f.write(updated_content)
        
        self.logger.info(f"Updated {manifest_script} to use {fork_org} organization")
        self.logger.info(f"Backup saved as {backup_script}")
    
    def _restore_manifest_sources(self, operator_path: Path) -> None:
        """
        Restore get_all_manifests.sh from backup
        
        Args:
            operator_path: Path to opendatahub-operator directory
        """
        manifest_script = operator_path / "get_all_manifests.sh"
        backup_script = operator_path / "get_all_manifests.sh.backup"
        
        if backup_script.exists():
            import shutil
            shutil.copy2(backup_script, manifest_script)
            self.logger.info(f"Restored {manifest_script} from backup")
        else:
            self.logger.warning(f"No backup found at {backup_script}")
    
    def parse_manifest_repositories(self) -> Dict[str, str]:
        """
        Parse get_all_manifests.sh to extract required repository names and their base branches
        
        Returns:
            Dict mapping repository names to their base branches as defined in get_all_manifests.sh
        """
        operator_path = self.src_dir / "opendatahub-operator"
        manifest_script = operator_path / "get_all_manifests.sh"
        
        if not manifest_script.exists():
            raise FileNotFoundError(f"get_all_manifests.sh not found at {manifest_script}")
        
        repo_branches = {}
        
        with open(manifest_script, 'r') as f:
            content = f.read()
        
        # Look for COMPONENT_MANIFESTS array entries
        # Format: ["key"]="repo-org:repo-name:ref-name:source-folder"
        import re
        
        # Extract only the COMPONENT_MANIFESTS array block
        array_start = content.find('declare -A COMPONENT_MANIFESTS=(')
        if array_start == -1:
            raise ValueError("COMPONENT_MANIFESTS array not found in get_all_manifests.sh")
        
        array_end = content.find(')', array_start)
        if array_end == -1:
            raise ValueError("COMPONENT_MANIFESTS array closing parenthesis not found")
        
        array_content = content[array_start:array_end + 1]
        
        # Extract repository names and branches from the array content only
        pattern = r'\["[^"]+"\]="opendatahub-io:([^:]+):([^:]+):[^"]+"'
        matches = re.findall(pattern, array_content)
        
        for repo_name, branch_name in matches:
            repo_branches[repo_name] = branch_name
        
        self.logger.info(f"Found {len(repo_branches)} repositories with branches in get_all_manifests.sh")
        return repo_branches
    
    def setup_manifest_repository(self, repo_name: str, base_branch: str = None) -> bool:
        """
        Ensure a manifest repository is forked, cloned, and has feature branch
        
        Args:
            repo_name: Repository name (e.g., "odh-dashboard")
            base_branch: Base branch to use (from get_all_manifests.sh) 
            
        Returns:
            bool: True if setup successful, False if errors occurred
        """
        try:
            original_repo = f"opendatahub-io/{repo_name}"
            fork_org = self.get_fork_org()
            branch_name = self.get_branch_name()
            
            # Use provided base_branch or fall back to config default
            if base_branch is None:
                base_branch = self.get_base_branch()
            
            self.logger.info(f"Setting up manifest repository: {repo_name} (base branch: {base_branch})")
            
            # Check if fork exists
            fork_created = False
            if not self.fork_exists(original_repo):
                self.logger.info(f"Fork doesn't exist, creating fork for {original_repo}")
                try:
                    self.fork_repository(original_repo, clone_after_fork=False)
                    fork_created = True
                except Exception as e:
                    self.logger.error(f"Failed to fork {original_repo}: {e}")
                    return False
            else:
                self.logger.info(f"Fork already exists for {original_repo}")
            
            # Check if local checkout exists
            if not self.local_checkout_exists(repo_name):
                self.logger.info(f"Local checkout doesn't exist, cloning {repo_name}")
                try:
                    # Add delay if we just created the fork to avoid race condition
                    if fork_created:
                        self.logger.info("Waiting 3 seconds for fork to be ready...")
                        time.sleep(3)
                    
                    fork_repo = f"{fork_org}/{repo_name}"
                    clone_path = self.clone_repository(fork_repo, repo_name)
                    
                    # Set up upstream remote
                    upstream_url = f"https://github.com/{original_repo}"
                    self.setup_upstream(clone_path, upstream_url)
                    
                except Exception as e:
                    self.logger.error(f"Failed to clone {repo_name}: {e}")
                    return False
            else:
                self.logger.info(f"Local checkout already exists for {repo_name}")
            
            # Ensure feature branch exists
            repo_path = self.src_dir / repo_name
            if not self.branch_exists(repo_path, branch_name):
                self.logger.info(f"Creating feature branch {branch_name} in {repo_name}")
                try:
                    # Rebase from upstream first
                    self.rebase_from_upstream(repo_path, base_branch)
                    
                    # Create feature branch
                    self.create_branch(repo_path, branch_name, base_branch)
                    
                except Exception as e:
                    self.logger.error(f"Failed to create branch {branch_name} in {repo_name}: {e}")
                    return False
            else:
                self.logger.info(f"Feature branch {branch_name} already exists in {repo_name}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error setting up {repo_name}: {e}")
            return False

    def get_repository_status(self, repo_path: Path) -> Dict[str, Any]:
        """
        Get git status information for a repository
        
        Args:
            repo_path: Path to repository
            
        Returns:
            Dict containing status information
        """
        try:
            result = self._run_command(["git", "status", "--porcelain"], cwd=repo_path)
            dirty_files = result.stdout.strip().split('\n') if result.stdout.strip() else []
            
            # Get current branch
            branch_result = self._run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path)
            current_branch = branch_result.stdout.strip()
            
            # Get commit info
            commit_result = self._run_command(["git", "log", "-1", "--format=%H %s"], cwd=repo_path)
            commit_info = commit_result.stdout.strip()
            
            # Get remote URLs
            remotes = self.get_remote_urls(repo_path)
            
            # Count different types of changes
            untracked = [f for f in dirty_files if f.startswith('??')]
            modified = [f for f in dirty_files if f.startswith(' M')]
            added = [f for f in dirty_files if f.startswith('A ')]
            deleted = [f for f in dirty_files if f.startswith(' D')]
            
            return {
                'clean': len(dirty_files) == 0,
                'current_branch': current_branch,
                'commit_info': commit_info,
                'total_changes': len(dirty_files),
                'untracked': len(untracked),
                'modified': len(modified),
                'added': len(added),
                'deleted': len(deleted),
                'dirty_files': dirty_files,
                'remotes': remotes
            }
            
        except Exception as e:
            self.logger.error(f"Error getting repository status for {repo_path}: {e}")
            return {
                'clean': False,
                'current_branch': 'unknown',
                'commit_info': 'unknown',
                'total_changes': 0,
                'untracked': 0,
                'modified': 0,
                'added': 0,
                'deleted': 0,
                'dirty_files': [],
                'remotes': {},
                'error': str(e)
            }

    def get_remote_urls(self, repo_path: Path) -> Dict[str, str]:
        """
        Get remote URLs for a repository
        
        Args:
            repo_path: Path to repository
            
        Returns:
            Dict mapping remote names to URLs
        """
        try:
            result = self._run_command(["git", "remote", "-v"], cwd=repo_path)
            remotes = {}
            
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        remote_name = parts[0]
                        remote_url = parts[1]
                        # Only capture fetch URLs (skip push URLs which are duplicates)
                        if len(parts) == 2 or parts[2] == '(fetch)':
                            remotes[remote_name] = remote_url
            
            return remotes
            
        except Exception as e:
            self.logger.error(f"Error getting remote URLs for {repo_path}: {e}")
            return {}

    def get_all_local_repositories(self) -> List[str]:
        """
        Get list of all local repository checkouts
        
        Returns:
            List of repository names
        """
        if not self.src_dir.exists():
            return []
        
        repos = []
        for item in self.src_dir.iterdir():
            if item.is_dir() and (item / ".git").exists():
                repos.append(item.name)
        
        return sorted(repos)

    def commit_and_push_repository(self, repo_path: Path, message: str) -> bool:
        """
        Commit all changes and push to origin
        
        Args:
            repo_path: Path to repository
            message: Commit message
            
        Returns:
            bool: True if successful, False if errors occurred
        """
        try:
            # Get current branch
            branch_result = self._run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path)
            current_branch = branch_result.stdout.strip()
            
            # Add all changes
            self._run_command(["git", "add", "."], cwd=repo_path)
            
            # Check if there are any staged changes
            diff_result = self._run_command(["git", "diff", "--cached", "--name-only"], cwd=repo_path)
            if not diff_result.stdout.strip():
                self.logger.info(f"No changes to commit in {repo_path.name}")
                return True
            
            # Commit changes
            self._run_command(["git", "commit", "-m", message], cwd=repo_path)
            
            # Push to origin
            self._run_command(["git", "push", "origin", current_branch], cwd=repo_path)
            
            self.logger.info(f"Successfully committed and pushed changes in {repo_path.name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error committing and pushing in {repo_path}: {e}")
            return False


def cmd_whoami(args):
    """Handle whoami subcommand"""
    try:
        gh = GitHubWrapper()
        user_data = gh.whoami()
        
        print(f"Authenticated as: {user_data['login']}")
        print(f"Name: {user_data['name']}")
        print(f"Email: {user_data.get('email', 'Not public')}")
        print(f"Company: {user_data.get('company', 'Not specified')}")
        print(f"Public repos: {user_data['public_repos']}")
        print(f"Private repos: {user_data['owned_private_repos']}")
        print(f"Profile URL: {user_data['html_url']}")
        
        return 0
        
    except Exception as e:
        print(f"Authentication failed: {e}")
        return 1


def cmd_list_repos(args):
    """Handle list-repos subcommand"""
    try:
        gh = GitHubWrapper()
        repos = gh.list_repositories(args.owner, limit=args.limit)
        
        print(f"Found {len(repos)} repositories for {args.owner}:")
        for repo in repos:
            private_marker = " (private)" if repo['isPrivate'] else ""
            print(f"  - {repo['name']}{private_marker}")
            print(f"    URL: {repo['url']}")
            print(f"    Default branch: {repo['defaultBranch']}")
            print()
        
        return 0
        
    except Exception as e:
        print(f"Error listing repositories: {e}")
        return 1


def cmd_fork_repo(args):
    """Handle fork-repo subcommand"""
    try:
        gh = GitHubWrapper()
        repo_info = gh.fork_repository(args.repository, clone_after_fork=args.clone)
        
        print(f"Successfully forked {args.repository}")
        print(f"Fork URL: https://github.com/{repo_info.fork_owner}/{repo_info.name}")
        
        if args.clone:
            print(f"Repository cloned to: src/{repo_info.name}")
        
        return 0
        
    except Exception as e:
        print(f"Error forking repository: {e}")
        return 1


def cmd_clone_repo(args):
    """Handle clone-repo subcommand"""
    try:
        gh = GitHubWrapper()
        clone_path = gh.clone_repository(args.repository, args.directory)
        
        print(f"Successfully cloned {args.repository}")
        print(f"Clone path: {clone_path}")
        
        return 0
        
    except Exception as e:
        print(f"Error cloning repository: {e}")
        return 1


def cmd_show_config(args):
    """Handle show-config subcommand"""
    try:
        gh = GitHubWrapper()
        config = gh.config
        
        print("📋 OpenDataHub Gateway API Migration Configuration")
        print("=" * 50)
        
        # GitHub Configuration
        print("\n🐙 GitHub Configuration:")
        github_config = config.get("github", {})
        print(f"   Fork Organization: {github_config.get('fork_org', 'Not set')}")
        print(f"   Branch Name: {github_config.get('branch_name', 'Not set')}")
        print(f"   Base Branch: {github_config.get('base_branch', 'Not set')}")
        
        # Build Configuration
        print("\n🔧 Build Configuration:")
        build_config = config.get("build", {})
        print(f"   Local Mode: {build_config.get('local', False)}")
        print(f"   Use Branch: {build_config.get('use_branch', False)}")
        print(f"   Build Image: {build_config.get('image', False)}")
        print(f"   Custom Registry: {build_config.get('custom_registry', False)}")
        print(f"   Manifests Only: {build_config.get('manifests_only', False)}")
        
        # Registry Configuration
        print("\n🐳 Registry Configuration:")
        registry_config = config.get("registry", {})
        print(f"   URL: {registry_config.get('url', 'Not set')}")
        print(f"   Namespace: {registry_config.get('namespace', 'Not set')}")
        print(f"   Tag: {registry_config.get('tag', 'Not set')}")
        
        # Target Repositories
        print("\n📦 Target Repositories:")
        target_repos = config.get("target_repositories", [])
        if target_repos:
            for repo in target_repos:
                print(f"   - {repo}")
        else:
            print("   None configured")
        
        # Migration Settings
        print("\n🔄 Migration Settings:")
        migration_config = config.get("migration", {})
        print(f"   Auto Create Branch: {migration_config.get('auto_create_branch', False)}")
        print(f"   Setup Upstream: {migration_config.get('setup_upstream', False)}")
        print(f"   Commit Message Template: {migration_config.get('commit_message_template', 'Not set')}")
        print(f"   PR Title Template: {migration_config.get('pr_title_template', 'Not set')}")
        
        # Project Metadata
        print("\n📋 Project Metadata:")
        project_config = config.get("project", {})
        print(f"   Name: {project_config.get('name', 'Not set')}")
        print(f"   Version: {project_config.get('version', 'Not set')}")
        print(f"   Description: {project_config.get('description', 'Not set')}")
        
        # File locations
        print("\n📁 File Locations:")
        print(f"   Config File: {gh.config_file}")
        print(f"   Source Directory: {gh.src_dir}")
        print(f"   GitHub Token: {gh.token_file}")
        
        # Derived values
        print("\n🔍 Derived Values:")
        print(f"   Full Registry URL: {gh.get_registry_url()}")
        print(f"   Full Image Name (example): {gh.get_full_image_name('odh-operator')}")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error showing configuration: {e}")
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
        
        success_count = 0
        for repo in target_repos:
            try:
                print(f"\nProcessing: {repo}")
                repo_info = gh.fork_repository(repo, clone_after_fork=args.clone)
                
                if args.clone:
                    repo_path = gh.src_dir / repo_info.name
                    
                    if gh.should_auto_create_branch():
                        print(f"Creating branch: {gh.get_branch_name()}")
                        gh.create_branch(repo_path, gh.get_branch_name(), gh.get_base_branch())
                    
                    if gh.should_setup_upstream():
                        print(f"Setting up upstream remote")
                        gh.setup_upstream(repo_path, f"https://github.com/{repo}")
                
                print(f"✓ Successfully processed {repo}")
                success_count += 1
                
            except Exception as e:
                print(f"✗ Failed to process {repo}: {e}")
                continue
        
        print(f"\nCompleted: {success_count}/{len(target_repos)} repositories processed successfully")
        
        return 0 if success_count == len(target_repos) else 1
        
    except Exception as e:
        print(f"Error in fork-all operation: {e}")
        return 1


def cmd_setup_operator(args):
    """Handle setup-operator subcommand"""
    try:
        gh = GitHubWrapper()
        repo_path = "opendatahub-io/opendatahub-operator"
        repo_name = "opendatahub-operator"
        
        # Check if local checkout already exists
        if gh.local_checkout_exists(repo_name):
            print(f"Local checkout already exists at src/{repo_name}")
            if not args.force:
                print("Use --force to recreate the setup")
                return 0
            else:
                print("--force specified, continuing with setup...")
        
        # Step 1: Check if fork exists, create if not
        print(f"Checking if fork exists for {repo_path}...")
        if not gh.fork_exists(repo_path):
            print(f"Fork does not exist, creating fork...")
            repo_info = gh.fork_repository(repo_path, clone_after_fork=False)
            print(f"✓ Fork created: {repo_info.fork_owner}/{repo_info.name}")
        else:
            print("✓ Fork already exists")
        
        # Step 2: Clone if local checkout doesn't exist
        local_repo_path = gh.src_dir / repo_name
        if not gh.local_checkout_exists(repo_name) or args.force:
            if args.force and local_repo_path.exists():
                print(f"Removing existing checkout at {local_repo_path}")
                import shutil
                shutil.rmtree(local_repo_path)
            
            print(f"Cloning repository...")
            fork_org = gh.get_fork_org()
            fork_url = f"https://github.com/{fork_org}/{repo_name}"
            clone_path = gh.clone_repository(fork_url, repo_name)
            print(f"✓ Repository cloned to {clone_path}")
        else:
            print("✓ Local checkout already exists")
        
        # Step 3: Set up upstream remote
        print("Setting up upstream remote...")
        try:
            gh.setup_upstream(local_repo_path, f"https://github.com/{repo_path}")
            print("✓ Upstream remote configured")
        except subprocess.CalledProcessError as e:
            if "already exists" in str(e.stderr):
                print("✓ Upstream remote already exists")
            else:
                raise
        
        # Step 4: Rebase from upstream
        print("Rebasing from upstream...")
        gh.rebase_from_upstream(local_repo_path)
        print("✓ Rebased from upstream")
        
        # Step 5: Create feature branch if it doesn't exist
        branch_name = gh.get_branch_name()
        if not gh.branch_exists(local_repo_path, branch_name):
            print(f"Creating feature branch: {branch_name}")
            gh.create_branch(local_repo_path, branch_name, gh.get_base_branch())
            print(f"✓ Feature branch '{branch_name}' created")
        else:
            print(f"✓ Feature branch '{branch_name}' already exists")
        
        print(f"\n🎉 Setup complete for {repo_name}!")
        print(f"Repository: src/{repo_name}")
        print(f"Branch: {branch_name}")
        print(f"Ready for Gateway API migration development")
        
        return 0
        
    except Exception as e:
        print(f"Error setting up operator: {e}")
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
        # Note: argparse sets default values for flags, so we need to check if they were actually provided
        # We'll assume that if the argument has the default value, it wasn't provided
        
        # Get build defaults from config
        build_defaults = gh.get_build_defaults()
        
        # Apply defaults only if the flag wasn't explicitly provided
        # Since argparse sets default values, we check if the value is the default
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
            print(f"\n📦 Processing {repo_name}...")
            
            # Skip if --skip-existing and already exists
            if hasattr(args, 'skip_existing') and args.skip_existing:
                if gh.local_checkout_exists(repo_name):
                    print(f"   ⏭️  Skipping {repo_name} (already exists)")
                    skipped.append(repo_name)
                    continue
            
            # Handle dry-run mode
            if hasattr(args, 'dry_run') and args.dry_run:
                print(f"   🔍 [DRY RUN] Would setup {repo_name}:")
                original_repo = f"opendatahub-io/{repo_name}"
                fork_org = gh.get_fork_org()
                
                # Check only local existence (fast check)
                local_exists = gh.local_checkout_exists(repo_name)
                
                print(f"      - Local checkout: {'✅' if local_exists else '❌'}")
                print(f"      - Would fork: {original_repo} → {fork_org}/{repo_name}")
                
                if not local_exists:
                    print(f"      - Would clone: {fork_org}/{repo_name}")
                    print(f"      - Would setup upstream: {original_repo}")
                    print(f"      - Would create branch: {gh.get_branch_name()}")
                else:
                    print(f"      - Would ensure branch: {gh.get_branch_name()}")
                
                successful.append(repo_name)  # Count as successful for dry-run
                continue
            
            if gh.setup_manifest_repository(repo_name, base_branch):
                print(f"   ✅ {repo_name} setup complete")
                successful.append(repo_name)
            else:
                print(f"   ❌ {repo_name} setup failed")
                failed.append(repo_name)
        
        # Print summary
        print(f"\n{'='*60}")
        print(f"📊 Setup Summary:")
        print(f"   ✅ Successful: {len(successful)}")
        print(f"   ❌ Failed: {len(failed)}")
        print(f"   ⏭️  Skipped: {len(skipped)}")
        
        if successful:
            print(f"\n✅ Successfully set up:")
            for repo in successful:
                print(f"   - {repo}")
        
        if failed:
            print(f"\n❌ Failed to set up:")
            for repo in failed:
                print(f"   - {repo}")
            print(f"\n💡 You may need to check:")
            print(f"   - GitHub authentication and permissions")
            print(f"   - Repository access rights")
            print(f"   - Network connectivity")
        
        if skipped:
            print(f"\n⏭️  Skipped (already exists):")
            for repo in skipped:
                print(f"   - {repo}")
        
        print(f"{'='*60}")
        
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
        
        print("📤 Pushing container image...")
        
        # Determine push command based on arguments
        if hasattr(args, 'custom_registry') and args.custom_registry:
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


def cmd_forks_status(args):
    """Handle forks-status subcommand"""
    try:
        gh = GitHubWrapper()
        
        # Suppress logging unless verbose mode is enabled
        original_level = gh.logger.level
        if not (hasattr(args, 'verbose') and args.verbose):
            gh.logger.setLevel(logging.ERROR)
        
        try:
            repos = gh.get_all_local_repositories()
            
            if not repos:
                print("No local repositories found in src/ directory")
                return 0
            
            # Check if filtering for dirty repos only
            dirty_only = hasattr(args, 'dirty') and args.dirty
            filter_text = " (dirty only)" if dirty_only else ""
            
            print(f"📊 Status of {len(repos)} local repositories{filter_text}:")
            print(f"{'='*80}")
            
            clean_count = 0
            dirty_count = 0
            shown_count = 0
            
            for repo_name in repos:
                repo_path = gh.src_dir / repo_name
                status = gh.get_repository_status(repo_path)
                
                # Repository header with org/repo:branch format
                fork_org = gh.get_fork_org()
                header = f"📦 {fork_org}/{repo_name}:{status['current_branch']}"
                
                if 'error' in status:
                    print(f"\n{header}")
                    print(f"   ❌ Error: {status['error']}")
                    shown_count += 1
                    continue
                
                # Skip clean repositories if --dirty filter is active
                if dirty_only and status['clean']:
                    clean_count += 1
                    continue
                
                # Show commit info (truncated)
                commit_info = status['commit_info']
                if len(commit_info) > 70:
                    commit_info = commit_info[:67] + "..."
                
                # Show status on same line as header when clean
                if status['clean']:
                    print(f"\n{header} ✅ Clean")
                else:
                    # Build change summary
                    change_parts = []
                    if status['untracked'] > 0:
                        change_parts.append(f"{status['untracked']}U")
                    if status['modified'] > 0:
                        change_parts.append(f"{status['modified']}M")
                    if status['added'] > 0:
                        change_parts.append(f"{status['added']}A")
                    if status['deleted'] > 0:
                        change_parts.append(f"{status['deleted']}D")
                    
                    change_summary = " ".join(change_parts)
                    print(f"\n{header} 📝 {status['total_changes']} files ({change_summary})")
                
                # Show remote URLs right after header
                remotes = status.get('remotes', {})
                if remotes:
                    origin_url = remotes.get('origin', 'N/A')
                    upstream_url = remotes.get('upstream', 'N/A')
                    print(f"   Origin: {origin_url}")
                    print(f"   Upstream: {upstream_url}")
                
                # Show commit info
                print(f"   {commit_info}")
                
                if status['clean']:
                    clean_count += 1
                    shown_count += 1
                else:
                    dirty_count += 1
                    shown_count += 1
                    
                    # Show details if requested
                    if hasattr(args, 'show_files') and args.show_files:
                        print(f"   Files:")
                        for file in status['dirty_files']:
                            print(f"     {file}")
            
            # Summary
            print(f"\n{'='*80}")
            print(f"📊 Summary:")
            if dirty_only:
                print(f"   📝 Repositories with changes (shown): {dirty_count}")
                print(f"   ✅ Clean repositories (hidden): {clean_count}")
                print(f"   📋 Total repositories: {len(repos)}")
            else:
                print(f"   ✅ Clean repositories: {clean_count}")
                print(f"   📝 Repositories with changes: {dirty_count}")
            
            if dirty_count > 0:
                print(f"\n💡 To commit all changes, run:")
                print(f"   python tool.py forks-commit")
            
            return 0
            
        finally:
            # Restore original logging level
            gh.logger.setLevel(original_level)
        
    except Exception as e:
        print(f"❌ Error getting repository status: {e}")
        return 1


def cmd_forks_commit(args):
    """Handle forks-commit subcommand"""
    try:
        gh = GitHubWrapper()
        
        # Suppress logging unless verbose mode is enabled
        original_level = gh.logger.level
        if not (hasattr(args, 'verbose') and args.verbose):
            gh.logger.setLevel(logging.ERROR)
        
        try:
            repos = gh.get_all_local_repositories()
            
            if not repos:
                print("No local repositories found in src/ directory")
                return 0
            
            # Get commit message
            message = args.message if hasattr(args, 'message') and args.message else "Gateway API migration changes"
            
            print(f"🚀 Committing changes across {len(repos)} repositories...")
            print(f"   Commit message: {message}")
            print(f"{'='*80}")
            
            successful = []
            failed = []
            skipped = []
            
            for repo_name in repos:
                repo_path = gh.src_dir / repo_name
                print(f"\n📦 Processing {repo_name}...")
                
                # Get status first
                status = gh.get_repository_status(repo_path)
                
                if 'error' in status:
                    print(f"   ❌ Error getting status: {status['error']}")
                    failed.append(repo_name)
                    continue
                
                if status['clean']:
                    print(f"   ⏭️  No changes to commit")
                    skipped.append(repo_name)
                    continue
                
                # Show what will be committed
                print(f"   📝 {status['total_changes']} files to commit")
                if status['untracked'] > 0:
                    print(f"      - Untracked: {status['untracked']}")
                if status['modified'] > 0:
                    print(f"      - Modified: {status['modified']}")
                if status['added'] > 0:
                    print(f"      - Added: {status['added']}")
                if status['deleted'] > 0:
                    print(f"      - Deleted: {status['deleted']}")
                
                # Commit and push
                if gh.commit_and_push_repository(repo_path, message):
                    print(f"   ✅ Successfully committed and pushed")
                    successful.append(repo_name)
                else:
                    print(f"   ❌ Failed to commit and push")
                    failed.append(repo_name)
            
            # Summary
            print(f"\n{'='*80}")
            print(f"📊 Commit Summary:")
            print(f"   ✅ Successfully committed: {len(successful)}")
            print(f"   ❌ Failed to commit: {len(failed)}")
            print(f"   ⏭️  Skipped (no changes): {len(skipped)}")
            
            if successful:
                print(f"\n✅ Successfully committed and pushed:")
                for repo in successful:
                    print(f"   - {repo}")
            
            if failed:
                print(f"\n❌ Failed to commit:")
                for repo in failed:
                    print(f"   - {repo}")
            
            if skipped:
                print(f"\n⏭️  Skipped (no changes):")
                for repo in skipped:
                    print(f"   - {repo}")
            
            return 1 if failed else 0
            
        finally:
            # Restore original logging level
            gh.logger.setLevel(original_level)
        
    except Exception as e:
        print(f"❌ Error committing repositories: {e}")
        return 1


def main():
    """Main entry point with argparse subcommands"""
    parser = argparse.ArgumentParser(
        description="OpenDataHub Gateway API migration project management tool",
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
  %(prog)s image-push
  %(prog)s image-push --custom-registry
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
    
    # fork-all subcommand
    fork_all_parser = subparsers.add_parser(
        'fork-all',
        help='Fork all target repositories from configuration'
    )
    fork_all_parser.add_argument(
        '--clone',
        action='store_true',
        help='Clone all forks after creating them'
    )
    fork_all_parser.set_defaults(func=cmd_fork_all)
    
    # setup-operator subcommand
    setup_operator_parser = subparsers.add_parser(
        'setup-operator',
        help='Complete setup for opendatahub-operator: fork, clone, rebase, and create feature branch'
    )
    setup_operator_parser.add_argument(
        '--force',
        action='store_true',
        help='Force recreation of setup even if local checkout exists'
    )
    setup_operator_parser.set_defaults(func=cmd_setup_operator)
    
    # setup-forks subcommand (primary name)
    setup_forks_parser = subparsers.add_parser(
        'setup-forks',
        help='Setup all fork repositories required for local development: fork, clone, and create feature branches'
    )
    setup_forks_parser.add_argument(
        '--skip-existing',
        action='store_true',
        help='Skip repositories that already have local checkouts'
    )
    setup_forks_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without actually doing it'
    )
    setup_forks_parser.set_defaults(func=cmd_setup_manifests)
    
    # setup-manifests subcommand (alias for backward compatibility)
    setup_manifests_parser = subparsers.add_parser(
        'setup-manifests',
        help='(Alias for setup-forks) Setup all fork repositories required for local development'
    )
    setup_manifests_parser.add_argument(
        '--skip-existing',
        action='store_true',
        help='Skip repositories that already have local checkouts'
    )
    setup_manifests_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without actually doing it'
    )
    setup_manifests_parser.set_defaults(func=cmd_setup_manifests)
    
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
    
    # clone-repo subcommand
    clone_repo_parser = subparsers.add_parser(
        'clone-repo',
        help='Clone a repository'
    )
    clone_repo_parser.add_argument(
        'repository',
        help='Repository to clone (e.g., opendatahub-io/odh-dashboard)'
    )
    clone_repo_parser.add_argument(
        '--directory',
        help='Custom directory name for the clone'
    )
    clone_repo_parser.set_defaults(func=cmd_clone_repo)
    
    # forks-status subcommand
    forks_status_parser = subparsers.add_parser(
        'forks-status',
        help='Show status of all local fork repositories'
    )
    forks_status_parser.add_argument(
        '--show-files',
        action='store_true',
        help='Show individual files that have changed'
    )
    forks_status_parser.add_argument(
        '--dirty',
        action='store_true',
        help='Only show repositories with uncommitted changes'
    )
    forks_status_parser.set_defaults(func=cmd_forks_status)
    
    # forks-commit subcommand
    forks_commit_parser = subparsers.add_parser(
        'forks-commit',
        help='Commit and push changes across all fork repositories'
    )
    forks_commit_parser.add_argument(
        '-m', '--message',
        default='Gateway API migration changes',
        help='Commit message (default: "Gateway API migration changes")'
    )
    forks_commit_parser.set_defaults(func=cmd_forks_commit)
    
    # Parse arguments
    args = parser.parse_args()
    
    # Set up logging level based on verbose flag
    if args.verbose:
        logging.getLogger("github_wrapper").setLevel(logging.DEBUG)
    
    # Execute the selected command
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main()) 