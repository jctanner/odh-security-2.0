"""
GitHub Repository and Configuration Management

This module provides the GitHubWrapper class for managing GitHub operations
and configuration for the OpenDataHub Gateway API migration project.
"""

import os
import subprocess
import logging
import time
import yaml
import json
import re
import shutil
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

    def __init__(
        self,
        token_file: str = ".github_token",
        src_dir: str = "src",
        config_file: str = "config.yaml",
    ):
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
        self.project_root = self.config_file_path.parent

        # Set src_dir relative to project root (where config file is found)
        self.src_dir = self.project_root / src_dir

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
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
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
            with open(self.config_file_path, "r") as f:
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

        raise FileNotFoundError(
            f"Configuration file '{config_name}' not found in current directory or any parent directory"
        )

    def _load_github_token(self) -> None:
        """
        Load GitHub token from file and set environment variable

        Raises:
            FileNotFoundError: If token file doesn't exist
            ValueError: If token file is empty
        """
        token_file = self._find_token_file()

        try:
            with open(token_file, "r") as f:
                token = f.read().strip()

            if not token or token.startswith("#"):
                raise ValueError("Token file is empty or contains only comments")

            # Set environment variable for gh CLI
            os.environ["GITHUB_TOKEN"] = token
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

        raise FileNotFoundError(
            f"Token file '{token_name}' not found in current directory or any parent directory"
        )

    def _run_command(
        self, command: List[str], cwd: Optional[Path] = None
    ) -> subprocess.CompletedProcess:
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
                command, cwd=cwd, capture_output=True, text=True, check=True
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
            fork_owner=fork_org,
        )

        self.logger.info(f"Successfully forked {repo_path} as {fork_org}/{name}")
        return repo_info

    def clone_repository(
        self, repo_url: str, directory_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Clone a repository to the src directory using SSH origin

        Args:
            repo_url: GitHub repository URL (owner/repo format)
            directory_name: Custom directory name (defaults to repo name)

        Returns:
            Dict: Dictionary with 'cloned' (bool) and 'local_path' (str) keys
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

        # Check if repository already exists
        if clone_path.exists() and (clone_path / ".git").exists():
            self.logger.info(f"Repository already exists at: {clone_path}")
            return {
                "cloned": False,
                "local_path": str(clone_path)
            }

        # Convert to SSH URL for origin
        ssh_url = f"git@github.com:{repo_path}.git"

        # Clone the repository using SSH
        clone_command = ["git", "clone", ssh_url, str(directory_name)]
        self._run_command(clone_command, cwd=self.src_dir)

        self.logger.info(f"Repository cloned to: {clone_path}")
        return {
            "cloned": True,
            "local_path": str(clone_path)
        }

    def create_branch(
        self, repo_path: Path, branch_name: str, base_branch: str = "main"
    ) -> None:
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
        self._run_command(
            ["git", "checkout", "-B", base_branch, f"origin/{base_branch}"],
            cwd=repo_path,
        )
        self._run_command(["git", "pull", "origin", base_branch], cwd=repo_path)

        # Create and checkout new branch (use -B to allow recreating existing branch)
        self._run_command(["git", "checkout", "-B", branch_name], cwd=repo_path)

        self.logger.info(f"Branch '{branch_name}' created successfully")

    def setup_upstream(self, repo_path: Path, upstream_url: str) -> None:
        """
        Setup upstream remote for a forked repository

        Args:
            repo_path: Path to local repository
            upstream_url: URL of upstream repository
        """
        self.logger.info(f"Setting up upstream remote: {upstream_url}")

        # Check if upstream remote already exists
        try:
            result = self._run_command(["git", "remote"], cwd=repo_path)
            existing_remotes = result.stdout.strip().split('\n')
            
            if "upstream" not in existing_remotes:
                # Add upstream remote
                self._run_command(
                    ["git", "remote", "add", "upstream", upstream_url], cwd=repo_path
                )
                self.logger.info("Upstream remote added")
            else:
                self.logger.info("Upstream remote already exists")
                # Update the upstream URL in case it changed
                self._run_command(
                    ["git", "remote", "set-url", "upstream", upstream_url], cwd=repo_path
                )
                self.logger.info("Upstream remote URL updated")
        
        except Exception as e:
            self.logger.error(f"Failed to check/setup upstream remote: {e}")
            raise

        # Fetch upstream (always do this to get latest changes)
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

        result = self._run_command(
            [
                "gh",
                "repo",
                "view",
                repo_path,
                "--json",
                "name,owner,url,defaultBranch,isPrivate",
            ]
        )

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

        result = self._run_command(
            [
                "gh",
                "repo",
                "list",
                owner,
                "--limit",
                str(limit),
                "--json",
                "name,owner,url,defaultBranch,isPrivate",
            ]
        )

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

        user_data = json.loads(result.stdout)

        self.logger.info(
            f"Authenticated as: {user_data['login']} ({user_data['name']})"
        )
        return user_data

    def get_fork_org(self) -> str:
        """Get the fork organization from configuration"""
        return self.config.get("github", {}).get("fork_org", "jctanner")

    def get_branch_name(self) -> str:
        """Get the migration branch name from configuration"""
        return self.config.get("github", {}).get("branch_name", "gateway-api-migration")

    def get_base_branch(self) -> str:
        """Get the base branch name from configuration"""
        return self.config.get("github", {}).get("base_branch", "main")

    def get_additional_repositories(self) -> List[str]:
        """Get the list of additional repositories from configuration"""
        return self.config.get("additional_repositories", [])

    def should_auto_create_branch(self) -> bool:
        """Check if branches should be automatically created after forking"""
        return self.config.get("migration", {}).get("auto_create_branch", True)

    def should_setup_upstream(self) -> bool:
        """Check if upstream remotes should be automatically set up"""
        return self.config.get("migration", {}).get("setup_upstream", True)

    def get_registry_url(self) -> str:
        """Get the container registry URL from configuration"""
        return self.config.get("registry", {}).get("url", "quay.io")

    def get_registry_namespace(self) -> str:
        """Get the registry namespace/organization from configuration"""
        return self.config.get("registry", {}).get("namespace", "opendatahub")

    def get_registry_tag(self) -> str:
        """Get the default image tag from configuration"""
        return self.config.get("registry", {}).get("tag", "latest")

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

        self.logger.info(
            f"Local checkout {'exists' if exists else 'does not exist'}: {checkout_path}"
        )
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
        self._run_command(
            ["git", "checkout", "-B", base_branch, f"origin/{base_branch}"],
            cwd=repo_path,
        )

        # Rebase from upstream
        self._run_command(["git", "rebase", f"upstream/{base_branch}"], cwd=repo_path)

        # Push the updated base branch to origin
        self._run_command(["git", "push", "origin", base_branch], cwd=repo_path)

        self.logger.info(f"Successfully rebased from upstream/{base_branch}")

    def branch_exists(self, repo_path: Path, branch_name: str) -> bool:
        """
        Check if a branch exists locally or remotely in the repository

        Args:
            repo_path: Path to local repository
            branch_name: Name of branch to check

        Returns:
            bool: True if branch exists locally or on origin, False otherwise
        """
        try:
            # Check local branches first
            result = self._run_command(
                ["git", "branch", "--list", branch_name], cwd=repo_path
            )
            local_exists = bool(result.stdout.strip())

            # Check remote branches
            result = self._run_command(
                ["git", "branch", "-r", "--list", f"origin/{branch_name}"], cwd=repo_path
            )
            remote_exists = bool(result.stdout.strip())

            exists = local_exists or remote_exists

            self.logger.info(
                f"Branch '{branch_name}' {'exists' if exists else 'does not exist'} in {repo_path} "
                f"(local: {local_exists}, remote: {remote_exists})"
            )
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
        with open(manifest_script, "r") as f:
            content = f.read()

        # Create a backup
        backup_script = operator_path / "get_all_manifests.sh.backup"
        with open(backup_script, "w") as f:
            f.write(content)

        # Replace opendatahub-io with fork organization in the COMPONENT_MANIFESTS array
        # Pattern to match lines like: ["component"]="opendatahub-io:repo:ref:path"
        pattern = r'(\["[^"]+"\]=")(opendatahub-io)(:)'
        replacement = rf"\1{fork_org}\3"

        updated_content = re.sub(pattern, replacement, content)

        # Write the updated script
        with open(manifest_script, "w") as f:
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
            raise FileNotFoundError(
                f"get_all_manifests.sh not found at {manifest_script}"
            )

        repo_branches = {}

        with open(manifest_script, "r") as f:
            content = f.read()

        # Look for COMPONENT_MANIFESTS array entries
        # Format: ["key"]="repo-org:repo-name:ref-name:source-folder"

        # Extract only the COMPONENT_MANIFESTS array block
        array_start = content.find("declare -A COMPONENT_MANIFESTS=(")
        if array_start == -1:
            raise ValueError(
                "COMPONENT_MANIFESTS array not found in get_all_manifests.sh"
            )

        array_end = content.find(")", array_start)
        if array_end == -1:
            raise ValueError("COMPONENT_MANIFESTS array closing parenthesis not found")

        array_content = content[array_start : array_end + 1]

        # Extract repository names and branches from the array content only
        pattern = r'\["[^"]+"\]="opendatahub-io:([^:]+):([^:]+):[^"]+"'
        matches = re.findall(pattern, array_content)

        for repo_name, branch_name in matches:
            repo_branches[repo_name] = branch_name

        self.logger.info(
            f"Found {len(repo_branches)} repositories with branches in get_all_manifests.sh"
        )
        return repo_branches

    def setup_manifest_repository(
        self, repo_name: str, base_branch: str = None
    ) -> bool:
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

            self.logger.info(
                f"Setting up manifest repository: {repo_name} (base branch: {base_branch})"
            )

            # Check if fork exists
            fork_created = False
            if not self.fork_exists(original_repo):
                self.logger.info(
                    f"Fork doesn't exist, creating fork for {original_repo}"
                )
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
                    clone_result = self.clone_repository(fork_repo, repo_name)
                    clone_path = Path(clone_result["local_path"])

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
                self.logger.info(
                    f"Creating feature branch {branch_name} in {repo_name}"
                )
                try:
                    # Rebase from upstream first
                    self.rebase_from_upstream(repo_path, base_branch)

                    # Create feature branch
                    self.create_branch(repo_path, branch_name, base_branch)

                except Exception as e:
                    self.logger.error(
                        f"Failed to create branch {branch_name} in {repo_name}: {e}"
                    )
                    return False
            else:
                self.logger.info(
                    f"Feature branch {branch_name} already exists in {repo_name}"
                )

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
            dirty_files = (
                result.stdout.strip().split("\n") if result.stdout.strip() else []
            )

            # Get current branch
            branch_result = self._run_command(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path
            )
            current_branch = branch_result.stdout.strip()

            # Get commit info
            commit_result = self._run_command(
                ["git", "log", "-1", "--format=%H %s"], cwd=repo_path
            )
            commit_info = commit_result.stdout.strip()

            # Get remote URLs
            remotes = self.get_remote_urls(repo_path)

            # Count different types of changes
            untracked = [f for f in dirty_files if f.startswith("??")]
            modified = [f for f in dirty_files if f.startswith(" M")]
            added = [f for f in dirty_files if f.startswith("A ")]
            deleted = [f for f in dirty_files if f.startswith(" D")]

            return {
                "clean": len(dirty_files) == 0,
                "current_branch": current_branch,
                "commit_info": commit_info,
                "total_changes": len(dirty_files),
                "untracked": len(untracked),
                "modified": len(modified),
                "added": len(added),
                "deleted": len(deleted),
                "dirty_files": dirty_files,
                "remotes": remotes,
            }

        except Exception as e:
            self.logger.error(f"Error getting repository status for {repo_path}: {e}")
            return {
                "clean": False,
                "current_branch": "unknown",
                "commit_info": "unknown",
                "total_changes": 0,
                "untracked": 0,
                "modified": 0,
                "added": 0,
                "deleted": 0,
                "dirty_files": [],
                "remotes": {},
                "error": str(e),
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

            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        remote_name = parts[0]
                        remote_url = parts[1]
                        # Only capture fetch URLs (skip push URLs which are duplicates)
                        if len(parts) == 2 or parts[2] == "(fetch)":
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
            branch_result = self._run_command(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path
            )
            current_branch = branch_result.stdout.strip()

            # Add all changes
            self._run_command(["git", "add", "."], cwd=repo_path)

            # Check if there are any staged changes
            diff_result = self._run_command(
                ["git", "diff", "--cached", "--name-only"], cwd=repo_path
            )
            if not diff_result.stdout.strip():
                self.logger.info(f"No changes to commit in {repo_path.name}")
                return True

            # Commit changes
            self._run_command(["git", "commit", "-m", message], cwd=repo_path)

            # Push to origin
            self._run_command(["git", "push", "origin", current_branch], cwd=repo_path)

            self.logger.info(
                f"Successfully committed and pushed changes in {repo_path.name}"
            )
            return True

        except Exception as e:
            self.logger.error(f"Error committing and pushing in {repo_path}: {e}")
            return False

    def get_environment_config(self, environment: str) -> Dict[str, Any]:
        """
        Get environment-specific configuration

        Args:
            environment: Environment name (e.g., 'dev', 'staging', 'prod')

        Returns:
            Dict containing environment configuration
        """
        env_config = self.config.get("environments", {}).get(environment, {})

        # Add registry configuration if using custom registry
        if env_config.get("custom_registry", False):
            env_config.update(
                {
                    "custom_registry_url": self.get_registry_url(),
                    "custom_registry_namespace": self.get_registry_namespace(),
                    "custom_registry_tag": self.get_registry_tag(),
                }
            )

        return env_config
