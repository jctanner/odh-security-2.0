import os
import subprocess
import sys
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

@dataclass
class BuildConfig:
    """Configuration for a build operation"""
    local: bool = False
    use_branch: bool = False
    image: bool = False
    custom_registry: bool = False
    manifests_only: bool = False
    push_image: bool = False
    
    # Registry configuration
    registry_url: Optional[str] = None
    registry_namespace: Optional[str] = None
    registry_tag: Optional[str] = None
    
    # Build context
    fork_org: Optional[str] = None
    branch_name: Optional[str] = None
    
    def __post_init__(self):
        """Validate build configuration"""
        if self.custom_registry and not all([self.registry_url, self.registry_namespace, self.registry_tag]):
            raise ValueError("Custom registry requires registry_url, registry_namespace, and registry_tag")
        
        if self.push_image and not self.image:
            raise ValueError("Cannot push image without building image (image=True required)")

@dataclass
class BuildResult:
    """Result of a build operation"""
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    image_name: Optional[str] = None
    registry_url: Optional[str] = None

class BuildManager:
    """Manager for build operations with different modes and configurations"""
    
    def __init__(self, project_root: str = None):
        """Initialize the build manager
        
        Args:
            project_root: Root directory of the project. If None, auto-detected.
        """
        self.project_root = project_root or self._find_project_root()
        self.operator_dir = os.path.join(self.project_root, 'src', 'opendatahub-operator')
        
    def _find_project_root(self) -> str:
        """Find the project root directory by looking for config.yaml"""
        current_dir = os.getcwd()
        
        while current_dir != '/':
            if os.path.exists(os.path.join(current_dir, 'config.yaml')):
                return current_dir
            current_dir = os.path.dirname(current_dir)
        
        # If not found, use current directory
        return os.getcwd()
    
    def build_operator(self, config: BuildConfig, verbose: bool = False) -> BuildResult:
        """Build the OpenDataHub operator
        
        Args:
            config: Build configuration
            verbose: Enable verbose output
            
        Returns:
            BuildResult containing success status and details
        """
        # Validate operator directory exists
        if not os.path.exists(self.operator_dir):
            return BuildResult(
                success=False,
                exit_code=1,
                stdout="",
                stderr=f"Operator directory not found: {self.operator_dir}"
            )
        
        # Determine make target
        make_target = self._determine_make_target(config)
        
        # Set up environment variables
        env_vars = self._setup_environment_variables(config)
        
        # Execute make command
        return self._execute_make(make_target, env_vars, verbose)
    
    def push_image(self, config: BuildConfig, verbose: bool = False) -> BuildResult:
        """Push a built image to registry
        
        Args:
            config: Build configuration (must have custom_registry=True)
            verbose: Enable verbose output
            
        Returns:
            BuildResult containing success status and details
        """
        if not config.custom_registry:
            return BuildResult(
                success=False,
                exit_code=1,
                stdout="",
                stderr="Image push requires custom_registry=True"
            )
        
        # Set up environment variables
        env_vars = self._setup_environment_variables(config)
        
        # Execute make push command
        return self._execute_make("image-push-custom-registry", env_vars, verbose)
    
    def build_and_push(self, config: BuildConfig, verbose: bool = False) -> BuildResult:
        """Build and push operator image in one operation
        
        Args:
            config: Build configuration
            verbose: Enable verbose output
            
        Returns:
            BuildResult containing success status and details
        """
        # First build the image
        build_config = BuildConfig(
            local=config.local,
            use_branch=config.use_branch,
            image=True,  # Force image build
            custom_registry=config.custom_registry,
            manifests_only=False,  # Can't push manifests
            push_image=False,  # Don't push yet
            registry_url=config.registry_url,
            registry_namespace=config.registry_namespace,
            registry_tag=config.registry_tag,
            fork_org=config.fork_org,
            branch_name=config.branch_name
        )
        
        print("Building operator image...")
        build_result = self.build_operator(build_config, verbose)
        
        if not build_result.success:
            return build_result
        
        # Then push the image
        print("Pushing operator image...")
        push_config = BuildConfig(
            custom_registry=config.custom_registry,
            registry_url=config.registry_url,
            registry_namespace=config.registry_namespace,
            registry_tag=config.registry_tag,
            fork_org=config.fork_org,
            branch_name=config.branch_name
        )
        
        push_result = self.push_image(push_config, verbose)
        
        # Return combined result
        return BuildResult(
            success=push_result.success,
            exit_code=push_result.exit_code,
            stdout=build_result.stdout + "\n" + push_result.stdout,
            stderr=build_result.stderr + "\n" + push_result.stderr,
            image_name=build_result.image_name,
            registry_url=push_result.registry_url
        )
    
    def _determine_make_target(self, config: BuildConfig) -> str:
        """Determine the appropriate make target based on configuration
        
        Args:
            config: Build configuration
            
        Returns:
            Make target string
        """
        if config.manifests_only:
            if config.local:
                return "get-manifests-local-branch" if config.use_branch else "get-manifests-local"
            else:
                return "get-manifests-fork-branch" if config.use_branch else "get-manifests-fork"
        elif config.image:
            if config.custom_registry:
                if config.local:
                    return "image-build-custom-registry-local-branch" if config.use_branch else "image-build-custom-registry-local"
                else:
                    return "image-build-custom-registry-fork-branch" if config.use_branch else "image-build-custom-registry-fork"
            else:
                if config.local:
                    return "image-build-local-branch" if config.use_branch else "image-build-local"
                else:
                    return "image-build-fork-branch" if config.use_branch else "image-build-fork"
        else:
            # Default to manifests only
            if config.local:
                return "get-manifests-local-branch" if config.use_branch else "get-manifests-local"
            else:
                return "get-manifests-fork-branch" if config.use_branch else "get-manifests-fork"
    
    def _setup_environment_variables(self, config: BuildConfig) -> Dict[str, str]:
        """Set up environment variables for make command
        
        Args:
            config: Build configuration
            
        Returns:
            Dictionary of environment variables
        """
        env_vars = {}
        
        if config.fork_org:
            env_vars['FORK_ORG'] = config.fork_org
        
        if config.branch_name:
            env_vars['BRANCH_NAME'] = config.branch_name
        
        if config.custom_registry:
            env_vars['CUSTOM_REGISTRY_URL'] = config.registry_url
            env_vars['CUSTOM_REGISTRY_NAMESPACE'] = config.registry_namespace
            env_vars['CUSTOM_REGISTRY_TAG'] = config.registry_tag
        
        return env_vars
    
    def _execute_make(self, target: str, env_vars: Dict[str, str], verbose: bool = False) -> BuildResult:
        """Execute a make command with environment variables
        
        Args:
            target: Make target to execute
            env_vars: Environment variables to set
            verbose: Enable verbose output
            
        Returns:
            BuildResult containing execution details
        """
        # Set up environment
        run_env = os.environ.copy()
        run_env.update(env_vars)
        
        # Build command
        cmd = ['make', target]
        
        if verbose:
            print(f"Executing: {' '.join(cmd)}")
            print(f"Environment: {env_vars}")
            print(f"Working directory: {self.operator_dir}")
        
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                env=run_env,
                cwd=self.operator_dir
            )
            
            stdout, stderr = process.communicate()
            
            if verbose or process.returncode != 0:
                print(f"stdout: {stdout}")
                print(f"stderr: {stderr}")
            
            return BuildResult(
                success=process.returncode == 0,
                exit_code=process.returncode,
                stdout=stdout,
                stderr=stderr,
                image_name=self._extract_image_name(stdout) if 'image' in target else None,
                registry_url=env_vars.get('CUSTOM_REGISTRY_URL')
            )
            
        except Exception as e:
            return BuildResult(
                success=False,
                exit_code=1,
                stdout="",
                stderr=f"Error executing make command: {e}"
            )
    
    def _extract_image_name(self, stdout: str) -> Optional[str]:
        """Extract built image name from make output
        
        Args:
            stdout: Make command output
            
        Returns:
            Image name if found, None otherwise
        """
        # Look for common patterns in podman/docker build output
        lines = stdout.split('\n')
        for line in lines:
            if 'Successfully tagged' in line:
                # Docker format: Successfully tagged image:tag
                parts = line.split('Successfully tagged ')
                if len(parts) > 1:
                    return parts[1].strip()
            elif 'COMMIT' in line and 'quay.io' in line:
                # Podman format: COMMIT quay.io/org/image:tag
                parts = line.split()
                if len(parts) > 1:
                    return parts[1].strip()
        
        return None
    
    def get_build_status(self) -> Dict[str, any]:
        """Get current build system status
        
        Returns:
            Dictionary with build system status information
        """
        status = {
            'operator_dir_exists': os.path.exists(self.operator_dir),
            'operator_dir': self.operator_dir,
            'project_root': self.project_root,
            'makefile_exists': os.path.exists(os.path.join(self.operator_dir, 'Makefile')),
            'dockerfile_exists': os.path.exists(os.path.join(self.operator_dir, 'Dockerfile')),
            'manifests_dir_exists': os.path.exists(os.path.join(self.operator_dir, 'opt', 'manifests')),
        }
        
        # Check for manifest files
        manifests_dir = os.path.join(self.operator_dir, 'opt', 'manifests')
        if os.path.exists(manifests_dir):
            status['manifest_count'] = len([f for f in os.listdir(manifests_dir) if f.endswith('.yaml')])
        else:
            status['manifest_count'] = 0
        
        return status
    
    def validate_build_environment(self) -> List[str]:
        """Validate the build environment and return any issues
        
        Returns:
            List of validation error messages (empty if valid)
        """
        issues = []
        
        if not os.path.exists(self.operator_dir):
            issues.append(f"Operator directory not found: {self.operator_dir}")
        
        if not os.path.exists(os.path.join(self.operator_dir, 'Makefile')):
            issues.append("Makefile not found in operator directory")
        
        if not os.path.exists(os.path.join(self.operator_dir, 'Dockerfile')):
            issues.append("Dockerfile not found in operator directory")
        
        # Check for make command
        try:
            subprocess.run(['make', '--version'], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            issues.append("make command not found - install GNU make")
        
        # Check for podman or docker
        has_podman = False
        has_docker = False
        
        try:
            subprocess.run(['podman', '--version'], capture_output=True, check=True)
            has_podman = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        
        try:
            subprocess.run(['docker', '--version'], capture_output=True, check=True)
            has_docker = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        
        if not has_podman and not has_docker:
            issues.append("Neither podman nor docker found - install one of them")
        
        return issues 