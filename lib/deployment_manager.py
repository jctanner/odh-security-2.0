import os
import subprocess
import sys
import json
import yaml
import time
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum


class DeploymentStatus(Enum):
    """Deployment status enumeration"""

    NOT_DEPLOYED = "not_deployed"
    DEPLOYING = "deploying"
    DEPLOYED = "deployed"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass
class DeploymentResource:
    """Represents a Kubernetes resource for deployment"""

    name: str
    namespace: str
    kind: str
    api_version: str
    status: DeploymentStatus = DeploymentStatus.NOT_DEPLOYED
    ready: bool = False
    message: Optional[str] = None
    yaml_path: Optional[str] = None


@dataclass
class DeploymentConfig:
    """Configuration for deployment operations"""

    namespace: str = "opendatahub"
    create_namespace: bool = True
    wait_timeout: int = 300  # 5 minutes
    check_interval: int = 5  # 5 seconds
    custom_image: Optional[str] = None
    custom_registry: Optional[str] = None
    dry_run: bool = False
    force: bool = False

    # Component-specific settings
    operator_enabled: bool = True
    dsci_enabled: bool = True
    dsc_enabled: bool = True

    # Resource files
    operator_yaml: Optional[str] = None
    dsci_yaml: Optional[str] = None
    dsc_yaml: Optional[str] = None


@dataclass
class DeploymentResult:
    """Result of a deployment operation"""

    success: bool
    resources: List[DeploymentResource] = field(default_factory=list)
    message: str = ""
    duration: float = 0.0
    stdout: str = ""
    stderr: str = ""


class DeploymentManager:
    """Manager for OpenDataHub deployment operations"""

    def __init__(self, project_root: str = None):
        """Initialize the deployment manager

        Args:
            project_root: Root directory of the project. If None, auto-detected.
        """
        self.project_root = project_root or self._find_project_root()
        self.operator_dir = os.path.join(
            self.project_root, "src", "opendatahub-operator"
        )
        self.deployments_dir = os.path.join(self.project_root, "deployments")

    def _find_project_root(self) -> str:
        """Find the project root directory by looking for config.yaml"""
        current_dir = os.getcwd()

        while current_dir != "/":
            if os.path.exists(os.path.join(current_dir, "config.yaml")):
                return current_dir
            current_dir = os.path.dirname(current_dir)

        # If not found, use current directory
        return os.getcwd()

    def deploy_operator(
        self, config: DeploymentConfig, verbose: bool = False
    ) -> DeploymentResult:
        """Deploy the OpenDataHub operator

        Args:
            config: Deployment configuration
            verbose: Enable verbose output

        Returns:
            DeploymentResult containing deployment status and details
        """
        start_time = time.time()

        # Validate kubectl
        kubectl_issues = self._validate_kubectl()
        if kubectl_issues:
            return DeploymentResult(
                success=False,
                message=f"kubectl validation failed: {'; '.join(kubectl_issues)}",
            )

        # Create namespace if needed
        if config.create_namespace:
            namespace_result = self._create_namespace(config.namespace, verbose)
            if not namespace_result.success:
                return namespace_result

        # Find operator YAML
        operator_yaml = config.operator_yaml or self._find_operator_yaml()
        if not operator_yaml:
            return DeploymentResult(
                success=False, message="Operator YAML file not found"
            )

        # Apply operator resources
        result = self._apply_yaml_file(
            operator_yaml, config.namespace, config.dry_run, verbose
        )

        if result.success and not config.dry_run:
            # Wait for operator to be ready
            operator_ready = self._wait_for_operator_ready(
                config.namespace, config.wait_timeout, verbose
            )
            if not operator_ready:
                result.success = False
                result.message = "Operator deployment timed out"

        result.duration = time.time() - start_time
        return result

    def deploy_dsci(
        self, config: DeploymentConfig, verbose: bool = False
    ) -> DeploymentResult:
        """Deploy DataScienceClusterInitialization (DSCI)

        Args:
            config: Deployment configuration
            verbose: Enable verbose output

        Returns:
            DeploymentResult containing deployment status and details
        """
        start_time = time.time()

        # Find DSCI YAML
        dsci_yaml = config.dsci_yaml or self._find_dsci_yaml()
        if not dsci_yaml:
            return DeploymentResult(success=False, message="DSCI YAML file not found")

        # Apply DSCI resources
        result = self._apply_yaml_file(
            dsci_yaml, config.namespace, config.dry_run, verbose
        )

        if result.success and not config.dry_run:
            # Wait for DSCI to be ready
            dsci_ready = self._wait_for_dsci_ready(
                config.namespace, config.wait_timeout, verbose
            )
            if not dsci_ready:
                result.success = False
                result.message = "DSCI deployment timed out"

        result.duration = time.time() - start_time
        return result

    def deploy_dsc(
        self, config: DeploymentConfig, verbose: bool = False
    ) -> DeploymentResult:
        """Deploy DataScienceCluster (DSC)

        Args:
            config: Deployment configuration
            verbose: Enable verbose output

        Returns:
            DeploymentResult containing deployment status and details
        """
        start_time = time.time()

        # Find DSC YAML
        dsc_yaml = config.dsc_yaml or self._find_dsc_yaml()
        if not dsc_yaml:
            return DeploymentResult(success=False, message="DSC YAML file not found")

        # Apply DSC resources
        result = self._apply_yaml_file(
            dsc_yaml, config.namespace, config.dry_run, verbose
        )

        if result.success and not config.dry_run:
            # Wait for DSC to be ready
            dsc_ready = self._wait_for_dsc_ready(
                config.namespace, config.wait_timeout, verbose
            )
            if not dsc_ready:
                result.success = False
                result.message = "DSC deployment timed out"

        result.duration = time.time() - start_time
        return result

    def deploy_full(
        self, config: DeploymentConfig, verbose: bool = False
    ) -> DeploymentResult:
        """Deploy full OpenDataHub stack (operator + DSCI + DSC)

        Args:
            config: Deployment configuration
            verbose: Enable verbose output

        Returns:
            DeploymentResult containing deployment status and details
        """
        start_time = time.time()
        combined_result = DeploymentResult(success=True)

        # Deploy operator
        if config.operator_enabled:
            print("Deploying OpenDataHub operator...")
            operator_result = self.deploy_operator(config, verbose)
            combined_result.resources.extend(operator_result.resources)
            combined_result.stdout += operator_result.stdout
            combined_result.stderr += operator_result.stderr

            if not operator_result.success:
                combined_result.success = False
                combined_result.message = (
                    f"Operator deployment failed: {operator_result.message}"
                )
                combined_result.duration = time.time() - start_time
                return combined_result

        # Deploy DSCI
        if config.dsci_enabled:
            print("Deploying DataScienceClusterInitialization...")
            dsci_result = self.deploy_dsci(config, verbose)
            combined_result.resources.extend(dsci_result.resources)
            combined_result.stdout += dsci_result.stdout
            combined_result.stderr += dsci_result.stderr

            if not dsci_result.success:
                combined_result.success = False
                combined_result.message = (
                    f"DSCI deployment failed: {dsci_result.message}"
                )
                combined_result.duration = time.time() - start_time
                return combined_result

        # Deploy DSC
        if config.dsc_enabled:
            print("Deploying DataScienceCluster...")
            dsc_result = self.deploy_dsc(config, verbose)
            combined_result.resources.extend(dsc_result.resources)
            combined_result.stdout += dsc_result.stdout
            combined_result.stderr += dsc_result.stderr

            if not dsc_result.success:
                combined_result.success = False
                combined_result.message = f"DSC deployment failed: {dsc_result.message}"
                combined_result.duration = time.time() - start_time
                return combined_result

        combined_result.duration = time.time() - start_time
        combined_result.message = "Full OpenDataHub deployment completed successfully"
        return combined_result

    def undeploy_operator(
        self, config: DeploymentConfig, verbose: bool = False
    ) -> DeploymentResult:
        """Undeploy the OpenDataHub operator

        Args:
            config: Deployment configuration
            verbose: Enable verbose output

        Returns:
            DeploymentResult containing undeployment status and details
        """
        operator_yaml = config.operator_yaml or self._find_operator_yaml()
        if not operator_yaml:
            return DeploymentResult(
                success=False, message="Operator YAML file not found"
            )

        return self._delete_yaml_file(
            operator_yaml, config.namespace, config.dry_run, verbose
        )

    def undeploy_dsci(
        self, config: DeploymentConfig, verbose: bool = False
    ) -> DeploymentResult:
        """Undeploy DataScienceClusterInitialization (DSCI)

        Args:
            config: Deployment configuration
            verbose: Enable verbose output

        Returns:
            DeploymentResult containing undeployment status and details
        """
        dsci_yaml = config.dsci_yaml or self._find_dsci_yaml()
        if not dsci_yaml:
            return DeploymentResult(success=False, message="DSCI YAML file not found")

        return self._delete_yaml_file(
            dsci_yaml, config.namespace, config.dry_run, verbose
        )

    def undeploy_dsc(
        self, config: DeploymentConfig, verbose: bool = False
    ) -> DeploymentResult:
        """Undeploy DataScienceCluster (DSC)

        Args:
            config: Deployment configuration
            verbose: Enable verbose output

        Returns:
            DeploymentResult containing undeployment status and details
        """
        dsc_yaml = config.dsc_yaml or self._find_dsc_yaml()
        if not dsc_yaml:
            return DeploymentResult(success=False, message="DSC YAML file not found")

        return self._delete_yaml_file(
            dsc_yaml, config.namespace, config.dry_run, verbose
        )

    def undeploy_full(
        self, config: DeploymentConfig, verbose: bool = False
    ) -> DeploymentResult:
        """Undeploy full OpenDataHub stack (DSC + DSCI + operator)

        Args:
            config: Deployment configuration
            verbose: Enable verbose output

        Returns:
            DeploymentResult containing undeployment status and details
        """
        start_time = time.time()
        combined_result = DeploymentResult(success=True)

        # Undeploy in reverse order (DSC -> DSCI -> operator)
        if config.dsc_enabled:
            print("Undeploying DataScienceCluster...")
            dsc_result = self.undeploy_dsc(config, verbose)
            combined_result.resources.extend(dsc_result.resources)
            combined_result.stdout += dsc_result.stdout
            combined_result.stderr += dsc_result.stderr

            if not dsc_result.success:
                print(f"Warning: DSC undeployment failed: {dsc_result.message}")

        if config.dsci_enabled:
            print("Undeploying DataScienceClusterInitialization...")
            dsci_result = self.undeploy_dsci(config, verbose)
            combined_result.resources.extend(dsci_result.resources)
            combined_result.stdout += dsci_result.stdout
            combined_result.stderr += dsci_result.stderr

            if not dsci_result.success:
                print(f"Warning: DSCI undeployment failed: {dsci_result.message}")

        if config.operator_enabled:
            print("Undeploying OpenDataHub operator...")
            operator_result = self.undeploy_operator(config, verbose)
            combined_result.resources.extend(operator_result.resources)
            combined_result.stdout += operator_result.stdout
            combined_result.stderr += operator_result.stderr

            if not operator_result.success:
                print(
                    f"Warning: Operator undeployment failed: {operator_result.message}"
                )

        combined_result.duration = time.time() - start_time
        combined_result.message = "Full OpenDataHub undeployment completed"
        return combined_result

    def get_deployment_status(self, namespace: str = "opendatahub") -> Dict[str, Any]:
        """Get current deployment status

        Args:
            namespace: Kubernetes namespace to check

        Returns:
            Dictionary with deployment status information
        """
        status = {
            "namespace": namespace,
            "namespace_exists": self._namespace_exists(namespace),
            "operator": self._get_operator_status(namespace),
            "dsci": self._get_dsci_status(namespace),
            "dsc": self._get_dsc_status(namespace),
            "pods": self._get_pods_status(namespace),
            "services": self._get_services_status(namespace),
        }

        return status

    def validate_deployment(self, namespace: str = "opendatahub") -> List[str]:
        """Validate deployment and return any issues

        Args:
            namespace: Kubernetes namespace to validate

        Returns:
            List of validation error messages (empty if valid)
        """
        issues = []

        # Check kubectl
        kubectl_issues = self._validate_kubectl()
        issues.extend(kubectl_issues)

        # Check namespace
        if not self._namespace_exists(namespace):
            issues.append(f"Namespace '{namespace}' does not exist")

        # Check operator
        operator_status = self._get_operator_status(namespace)
        if not operator_status["deployed"]:
            issues.append("OpenDataHub operator not deployed")
        elif not operator_status["ready"]:
            issues.append("OpenDataHub operator not ready")

        # Check DSCI
        dsci_status = self._get_dsci_status(namespace)
        if not dsci_status["deployed"]:
            issues.append("DataScienceClusterInitialization not deployed")
        elif not dsci_status["ready"]:
            issues.append("DataScienceClusterInitialization not ready")

        return issues

    def _validate_kubectl(self) -> List[str]:
        """Validate kubectl is available and configured

        Returns:
            List of validation error messages
        """
        issues = []

        # Check kubectl command
        try:
            result = subprocess.run(
                ["kubectl", "version", "--client"],
                capture_output=True,
                text=True,
                check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            issues.append("kubectl command not found - install kubectl")
            return issues

        # Check cluster connection
        try:
            result = subprocess.run(
                ["kubectl", "cluster-info"], capture_output=True, text=True, check=True
            )
        except subprocess.CalledProcessError:
            issues.append("kubectl cannot connect to cluster - check kubeconfig")

        return issues

    def _create_namespace(
        self, namespace: str, verbose: bool = False
    ) -> DeploymentResult:
        """Create a Kubernetes namespace

        Args:
            namespace: Namespace name
            verbose: Enable verbose output

        Returns:
            DeploymentResult
        """
        if self._namespace_exists(namespace):
            return DeploymentResult(
                success=True, message=f"Namespace '{namespace}' already exists"
            )

        cmd = ["kubectl", "create", "namespace", namespace]
        return self._run_kubectl_command(cmd, verbose)

    def _namespace_exists(self, namespace: str) -> bool:
        """Check if a namespace exists

        Args:
            namespace: Namespace name

        Returns:
            True if namespace exists, False otherwise
        """
        try:
            result = subprocess.run(
                ["kubectl", "get", "namespace", namespace],
                capture_output=True,
                text=True,
                check=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False

    def _apply_yaml_file(
        self,
        yaml_file: str,
        namespace: str,
        dry_run: bool = False,
        verbose: bool = False,
    ) -> DeploymentResult:
        """Apply a YAML file to the cluster

        Args:
            yaml_file: Path to YAML file
            namespace: Target namespace
            dry_run: Perform dry run only
            verbose: Enable verbose output

        Returns:
            DeploymentResult
        """
        cmd = ["kubectl", "apply", "-f", yaml_file, "-n", namespace]
        if dry_run:
            cmd.append("--dry-run=client")

        return self._run_kubectl_command(cmd, verbose)

    def _delete_yaml_file(
        self,
        yaml_file: str,
        namespace: str,
        dry_run: bool = False,
        verbose: bool = False,
    ) -> DeploymentResult:
        """Delete resources from a YAML file

        Args:
            yaml_file: Path to YAML file
            namespace: Target namespace
            dry_run: Perform dry run only
            verbose: Enable verbose output

        Returns:
            DeploymentResult
        """
        cmd = ["kubectl", "delete", "-f", yaml_file, "-n", namespace]
        if dry_run:
            cmd.append("--dry-run=client")

        return self._run_kubectl_command(cmd, verbose)

    def _run_kubectl_command(
        self, cmd: List[str], verbose: bool = False
    ) -> DeploymentResult:
        """Run a kubectl command

        Args:
            cmd: Command and arguments
            verbose: Enable verbose output

        Returns:
            DeploymentResult
        """
        if verbose:
            print(f"Running: {' '.join(cmd)}")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)

            if verbose:
                print(f"stdout: {result.stdout}")
                print(f"stderr: {result.stderr}")

            return DeploymentResult(
                success=True,
                stdout=result.stdout,
                stderr=result.stderr,
                message="Command executed successfully",
            )

        except subprocess.CalledProcessError as e:
            return DeploymentResult(
                success=False,
                stdout=e.stdout,
                stderr=e.stderr,
                message=f"Command failed with exit code {e.returncode}",
            )

    def _find_operator_yaml(self) -> Optional[str]:
        """Find operator YAML file

        Returns:
            Path to operator YAML file or None if not found
        """
        # Check common locations
        locations = [
            os.path.join(self.deployments_dir, "operator.yaml"),
            os.path.join(self.operator_dir, "config", "operator.yaml"),
            os.path.join(self.operator_dir, "deploy", "operator.yaml"),
        ]

        for location in locations:
            if os.path.exists(location):
                return location

        return None

    def _find_dsci_yaml(self) -> Optional[str]:
        """Find DSCI YAML file

        Returns:
            Path to DSCI YAML file or None if not found
        """
        locations = [
            os.path.join(self.deployments_dir, "dsci.yaml"),
            os.path.join(self.operator_dir, "config", "samples", "dsci.yaml"),
        ]

        for location in locations:
            if os.path.exists(location):
                return location

        return None

    def _find_dsc_yaml(self) -> Optional[str]:
        """Find DSC YAML file

        Returns:
            Path to DSC YAML file or None if not found
        """
        locations = [
            os.path.join(self.deployments_dir, "dsc.yaml"),
            os.path.join(self.operator_dir, "config", "samples", "dsc.yaml"),
        ]

        for location in locations:
            if os.path.exists(location):
                return location

        return None

    def _wait_for_operator_ready(
        self, namespace: str, timeout: int, verbose: bool = False
    ) -> bool:
        """Wait for operator to be ready

        Args:
            namespace: Kubernetes namespace
            timeout: Timeout in seconds
            verbose: Enable verbose output

        Returns:
            True if operator is ready, False if timed out
        """
        # Implementation depends on operator deployment structure
        # This is a placeholder - would need to check specific operator pods/deployments
        return True

    def _wait_for_dsci_ready(
        self, namespace: str, timeout: int, verbose: bool = False
    ) -> bool:
        """Wait for DSCI to be ready

        Args:
            namespace: Kubernetes namespace
            timeout: Timeout in seconds
            verbose: Enable verbose output

        Returns:
            True if DSCI is ready, False if timed out
        """
        # Implementation would check DSCI status
        return True

    def _wait_for_dsc_ready(
        self, namespace: str, timeout: int, verbose: bool = False
    ) -> bool:
        """Wait for DSC to be ready

        Args:
            namespace: Kubernetes namespace
            timeout: Timeout in seconds
            verbose: Enable verbose output

        Returns:
            True if DSC is ready, False if timed out
        """
        # Implementation would check DSC status
        return True

    def _get_operator_status(self, namespace: str) -> Dict[str, Any]:
        """Get operator status

        Args:
            namespace: Kubernetes namespace

        Returns:
            Dictionary with operator status
        """
        # Placeholder implementation
        return {"deployed": False, "ready": False, "replicas": 0, "ready_replicas": 0}

    def _get_dsci_status(self, namespace: str) -> Dict[str, Any]:
        """Get DSCI status

        Args:
            namespace: Kubernetes namespace

        Returns:
            Dictionary with DSCI status
        """
        # Placeholder implementation
        return {"deployed": False, "ready": False, "phase": "Unknown"}

    def _get_dsc_status(self, namespace: str) -> Dict[str, Any]:
        """Get DSC status

        Args:
            namespace: Kubernetes namespace

        Returns:
            Dictionary with DSC status
        """
        # Placeholder implementation
        return {"deployed": False, "ready": False, "phase": "Unknown"}

    def _get_pods_status(self, namespace: str) -> List[Dict[str, Any]]:
        """Get pods status in namespace

        Args:
            namespace: Kubernetes namespace

        Returns:
            List of pod status dictionaries
        """
        # Placeholder implementation
        return []

    def _get_services_status(self, namespace: str) -> List[Dict[str, Any]]:
        """Get services status in namespace

        Args:
            namespace: Kubernetes namespace

        Returns:
            List of service status dictionaries
        """
        # Placeholder implementation
        return []
