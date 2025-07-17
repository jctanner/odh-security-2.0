import yaml
import os
import subprocess
import sys
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from pathlib import Path


@dataclass
class WorkflowStep:
    """Represents a single step in a workflow"""

    name: str
    type: str  # 'kubectl', 'tool', 'workflow', 'shell'
    command: str
    args: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None
    working_directory: Optional[str] = None
    ignore_errors: bool = False
    condition: Optional[str] = None


@dataclass
class WorkflowDefinition:
    """Represents a complete workflow definition"""

    name: str
    description: str
    steps: List[WorkflowStep]
    variables: Optional[Dict[str, str]] = None
    includes: Optional[List[str]] = None


class WorkflowEngine:
    """Engine for executing custom YAML workflow definitions"""

    def __init__(self, project_root: str = None):
        """Initialize the workflow engine

        Args:
            project_root: Root directory of the project. If None, auto-detected.
        """
        self.project_root = project_root or self._find_project_root()
        self.workflows_dir = os.path.join(self.project_root, "workflows")
        self.config_file = os.path.join(self.project_root, "config.yaml")
        self.config = self._load_config()

    def _find_project_root(self) -> str:
        """Find the project root directory by looking for config.yaml"""
        current_dir = os.getcwd()

        while current_dir != "/":
            if os.path.exists(os.path.join(current_dir, "config.yaml")):
                return current_dir
            current_dir = os.path.dirname(current_dir)

        # If not found, use current directory
        return os.getcwd()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from config.yaml

        Returns:
            Dictionary containing configuration values
        """
        if not os.path.exists(self.config_file):
            return {}

        try:
            with open(self.config_file, "r") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Warning: Could not load config file {self.config_file}: {e}")
            return {}

    def _config_to_variables(self) -> Dict[str, str]:
        """Convert config dictionary to workflow variables

        Flattens nested config into uppercase variable names.
        Example: github.fork_org -> GITHUB_FORK_ORG

        Returns:
            Dictionary of config values as workflow variables
        """
        variables = {}

        def flatten_dict(d: Dict[str, Any], prefix: str = "") -> None:
            for key, value in d.items():
                if isinstance(value, dict):
                    flatten_dict(value, f"{prefix}{key.upper()}_")
                else:
                    var_name = f"{prefix}{key.upper()}"
                    variables[var_name] = str(value)

        flatten_dict(self.config)

        # Add some convenience aliases for common values
        if "GITHUB_FORK_ORG" in variables:
            variables["FORK_ORG"] = variables["GITHUB_FORK_ORG"]
        if "GITHUB_BRANCH_NAME" in variables:
            variables["BRANCH_NAME"] = variables["GITHUB_BRANCH_NAME"]
        if "REGISTRY_URL" in variables:
            variables["REGISTRY_URL"] = variables["REGISTRY_URL"]
        if "REGISTRY_NAMESPACE" in variables:
            variables["REGISTRY_NAMESPACE"] = variables["REGISTRY_NAMESPACE"]
        if "REGISTRY_TAG" in variables:
            variables["REGISTRY_TAG"] = variables["REGISTRY_TAG"]

        # Add computed project-relative paths (absolute paths)
        variables["PROJECT_ROOT"] = self.project_root
        variables["LOCAL_CHECKOUTS_DIR"] = os.path.join(self.project_root, "src")
        variables["WORKFLOWS_DIR"] = self.workflows_dir

        return variables

    def load_workflow(self, workflow_name: str) -> WorkflowDefinition:
        """Load a workflow definition from YAML file with include support

        Args:
            workflow_name: Name of the workflow file (without .yaml extension)

        Returns:
            WorkflowDefinition object with includes resolved

        Raises:
            FileNotFoundError: If workflow file doesn't exist
            yaml.YAMLError: If YAML parsing fails
        """
        return self._load_workflow_with_includes(workflow_name, set())

    def _load_workflow_with_includes(
        self, workflow_name: str, loaded_workflows: set
    ) -> WorkflowDefinition:
        """Load a workflow definition with recursive include processing

        Args:
            workflow_name: Name of the workflow file (without .yaml extension)
            loaded_workflows: Set of already loaded workflows to prevent circular includes

        Returns:
            WorkflowDefinition object with includes resolved

        Raises:
            FileNotFoundError: If workflow file doesn't exist
            yaml.YAMLError: If YAML parsing fails
            ValueError: If circular includes detected
        """
        if workflow_name in loaded_workflows:
            raise ValueError(
                f"Circular include detected: {workflow_name} is already being loaded"
            )

        workflow_file = os.path.join(self.workflows_dir, f"{workflow_name}.yaml")

        if not os.path.exists(workflow_file):
            raise FileNotFoundError(f"Workflow file not found: {workflow_file}")

        with open(workflow_file, "r") as f:
            workflow_data = yaml.safe_load(f)

        # Track this workflow as being loaded
        loaded_workflows.add(workflow_name)

        # Process includes first
        merged_variables = {}
        merged_steps = []

        if "includes" in workflow_data:
            for include_name in workflow_data["includes"]:
                try:
                    included_workflow = self._load_workflow_with_includes(
                        include_name, loaded_workflows.copy()
                    )

                    # Merge variables (included workflows have lower precedence)
                    if included_workflow.variables:
                        merged_variables.update(included_workflow.variables)

                    # Merge steps (included steps come first)
                    merged_steps.extend(included_workflow.steps)

                except Exception as e:
                    print(
                        f"Warning: Could not load included workflow '{include_name}': {e}"
                    )
                    continue

        # Add variables from main workflow (higher precedence)
        if workflow_data.get("variables"):
            merged_variables.update(workflow_data["variables"])

        # Parse steps from main workflow
        main_steps = []
        for step_data in workflow_data.get("steps", []):
            step = WorkflowStep(
                name=step_data["name"],
                type=step_data["type"],
                command=step_data["command"],
                args=step_data.get("args"),
                env=step_data.get("env"),
                working_directory=step_data.get("working_directory"),
                ignore_errors=step_data.get("ignore_errors", False),
                condition=step_data.get("condition"),
            )
            main_steps.append(step)

        # Add main workflow steps after included steps
        merged_steps.extend(main_steps)

        return WorkflowDefinition(
            name=workflow_data["name"],
            description=workflow_data.get("description", ""),
            steps=merged_steps,
            variables=merged_variables if merged_variables else None,
            includes=workflow_data.get("includes"),
        )

    def execute_workflow(
        self, workflow_name: str, variables: Dict[str, str] = None
    ) -> bool:
        """Execute a workflow by name

        Args:
            workflow_name: Name of the workflow to execute
            variables: Runtime variables to override workflow defaults

        Returns:
            True if all steps succeeded, False otherwise
        """
        try:
            workflow = self.load_workflow(workflow_name)
            return self._execute_workflow_definition(workflow, variables)
        except Exception as e:
            print(f"Error loading workflow '{workflow_name}': {e}")
            return False

    def _execute_workflow_definition(
        self, workflow: WorkflowDefinition, variables: Dict[str, str] = None
    ) -> bool:
        """Execute a workflow definition

        Args:
            workflow: WorkflowDefinition to execute
            variables: Runtime variables

        Returns:
            True if all steps succeeded, False otherwise
        """
        print(f"Executing workflow: {workflow.name}")
        print(f"Description: {workflow.description}")
        print()

        # Merge variables in order of precedence: config < workflow < runtime
        runtime_vars = {}

        # 1. Start with config variables
        runtime_vars.update(self._config_to_variables())

        # 2. Add workflow-defined variables (can override config)
        if workflow.variables:
            runtime_vars.update(workflow.variables)

        # 3. Add runtime variables (can override both config and workflow)
        if variables:
            runtime_vars.update(variables)

        for i, step in enumerate(workflow.steps, 1):
            if not self._execute_step(step, runtime_vars, i, len(workflow.steps)):
                if not step.ignore_errors:
                    print(f"Workflow failed at step {i}: {step.name}")
                    return False
                else:
                    print(f"Step {i} failed but continuing due to ignore_errors=true")

        print(f"Workflow '{workflow.name}' completed successfully!")
        return True

    def _execute_step(
        self,
        step: WorkflowStep,
        variables: Dict[str, str],
        step_num: int,
        total_steps: int,
    ) -> bool:
        """Execute a single workflow step

        Args:
            step: WorkflowStep to execute
            variables: Runtime variables for variable substitution
            step_num: Current step number
            total_steps: Total number of steps

        Returns:
            True if step succeeded, False otherwise
        """
        print(f"[{step_num}/{total_steps}] {step.name}")

        # Check condition if specified
        if step.condition and not self._evaluate_condition(step.condition, variables):
            print(f"  Skipping step due to condition: {step.condition}")
            return True

        # Substitute variables in command and args
        command = self._substitute_variables(step.command, variables)

        # If args not specified, split command by spaces to get command + args
        if step.args is None:
            # Split command into parts, first part is command, rest are args
            command_parts = command.split()
            if len(command_parts) > 1:
                command = command_parts[0]
                args = command_parts[1:]
            else:
                args = []
        else:
            # Use explicitly provided args
            args = [self._substitute_variables(arg, variables) for arg in step.args]

        # Substitute variables in working_directory if specified
        working_directory = None
        if step.working_directory:
            working_directory = self._substitute_variables(
                step.working_directory, variables
            )

        # Execute based on step type
        if step.type == "kubectl":
            return self._execute_kubectl(command, args, step.env, working_directory)
        elif step.type == "tool":
            return self._execute_tool(command, args, step.env, working_directory)
        elif step.type == "workflow":
            return self._execute_nested_workflow(command, variables)
        elif step.type == "shell":
            return self._execute_shell(command, args, step.env, working_directory)
        else:
            print(f"  Unknown step type: {step.type}")
            return False

    def _evaluate_condition(self, condition: str, variables: Dict[str, str]) -> bool:
        """Evaluate a simple condition

        Args:
            condition: Condition string to evaluate
            variables: Variables available for condition evaluation

        Returns:
            True if condition is met, False otherwise
        """
        # Simple condition evaluation - can be extended
        condition = self._substitute_variables(condition, variables)

        # For now, just check if it's "true" or "false"
        return condition.lower() == "true"

    def _substitute_variables(self, text: str, variables: Dict[str, str]) -> str:
        """Substitute variables in text using ${VAR} syntax

        Args:
            text: Text with potential variables
            variables: Dictionary of variable values

        Returns:
            Text with variables substituted
        """
        import re

        def replace_var(match):
            var_name = match.group(1)
            return variables.get(var_name, match.group(0))

        return re.sub(r"\$\{([^}]+)\}", replace_var, text)

    def _execute_kubectl(
        self,
        command: str,
        args: List[str],
        env: Dict[str, str] = None,
        working_directory: str = None,
    ) -> bool:
        """Execute a kubectl command

        Args:
            command: kubectl subcommand
            args: Additional arguments
            env: Environment variables
            working_directory: Directory to run command in

        Returns:
            True if command succeeded, False otherwise
        """
        cmd = ["kubectl", command] + args
        return self._run_command(cmd, env, working_directory)

    def _execute_tool(
        self,
        command: str,
        args: List[str],
        env: Dict[str, str] = None,
        working_directory: str = None,
    ) -> bool:
        """Execute a tool.py subcommand

        Args:
            command: tool.py subcommand
            args: Additional arguments
            env: Environment variables
            working_directory: Directory to run command in

        Returns:
            True if command succeeded, False otherwise
        """
        tool_path = os.path.join(self.project_root, "tool.py")
        cmd = ["python", tool_path, command] + args
        return self._run_command(cmd, env, working_directory)

    def _execute_nested_workflow(
        self, workflow_name: str, variables: Dict[str, str]
    ) -> bool:
        """Execute a nested workflow

        Args:
            workflow_name: Name of the nested workflow
            variables: Variables to pass to nested workflow

        Returns:
            True if nested workflow succeeded, False otherwise
        """
        print(f"  Executing nested workflow: {workflow_name}")
        return self.execute_workflow(workflow_name, variables)

    def _execute_shell(
        self,
        command: str,
        args: List[str],
        env: Dict[str, str] = None,
        working_directory: str = None,
    ) -> bool:
        """Execute a shell command

        Args:
            command: Shell command
            args: Additional arguments
            env: Environment variables
            working_directory: Directory to run command in

        Returns:
            True if command succeeded, False otherwise
        """
        cmd = [command] + args
        return self._run_command(cmd, env, working_directory)

    def _run_command(
        self, cmd: List[str], env: Dict[str, str] = None, working_directory: str = None
    ) -> bool:
        """Run a command with real-time output

        Args:
            cmd: Command and arguments as list
            env: Environment variables to set
            working_directory: Directory to run command in (defaults to project_root)

        Returns:
            True if command succeeded, False otherwise
        """
        cwd = working_directory if working_directory else self.project_root
        print(f"  Running: {' '.join(cmd)}")
        if working_directory:
            print(f"  In directory: {cwd}")

        # Set up environment
        run_env = os.environ.copy()
        if env:
            run_env.update(env)

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                env=run_env,
                cwd=cwd,
            )

            # Print output in real-time
            for line in process.stdout:
                print(f"    {line.rstrip()}")

            process.wait()

            if process.returncode == 0:
                print(f"  ✓ Command succeeded")
                return True
            else:
                print(f"  ✗ Command failed with exit code {process.returncode}")
                return False

        except Exception as e:
            print(f"  ✗ Error executing command: {e}")
            return False

    def list_workflows(self) -> List[str]:
        """List available workflows

        Returns:
            List of workflow names (without .yaml extension)
        """
        if not os.path.exists(self.workflows_dir):
            return []

        workflows = []
        for file in os.listdir(self.workflows_dir):
            if file.endswith(".yaml"):
                workflows.append(file[:-5])  # Remove .yaml extension

        return sorted(workflows)

    def create_workflows_directory(self):
        """Create the workflows directory if it doesn't exist"""
        os.makedirs(self.workflows_dir, exist_ok=True)

    def get_available_variables(self) -> Dict[str, str]:
        """Get all available variables from config.yaml

        Returns:
            Dictionary of available variables that can be used in workflows
        """
        return self._config_to_variables()

    def show_available_variables(self) -> None:
        """Print all available variables from config.yaml"""
        variables = self.get_available_variables()
        print("Available workflow variables from config.yaml:")
        print()

        # Group variables by category
        categories = {}
        for key, value in variables.items():
            if key.startswith("GITHUB_"):
                categories.setdefault("GitHub", []).append((key, value))
            elif key.startswith("REGISTRY_"):
                categories.setdefault("Registry", []).append((key, value))
            elif key.startswith("BUILD_"):
                categories.setdefault("Build", []).append((key, value))
            elif key.startswith("MIGRATION_"):
                categories.setdefault("Migration", []).append((key, value))
            elif key.startswith("PROJECT_"):
                categories.setdefault("Project", []).append((key, value))
            elif key in ["FORK_ORG", "BRANCH_NAME"]:
                categories.setdefault("Aliases", []).append((key, value))
            else:
                categories.setdefault("Other", []).append((key, value))

        for category, vars_list in categories.items():
            print(f"{category}:")
            for key, value in sorted(vars_list):
                print(f"  {key}: {value}")
            print()

    def preview_workflow_variables(
        self, workflow_name: str, runtime_vars: Dict[str, str] = None
    ) -> Dict[str, str]:
        """Preview the final set of variables that would be used for a workflow

        Args:
            workflow_name: Name of the workflow
            runtime_vars: Runtime variables to override defaults

        Returns:
            Dictionary of final variables that would be used
        """
        try:
            workflow = self.load_workflow(workflow_name)

            # Apply same merge logic as _execute_workflow_definition
            final_vars = {}
            final_vars.update(self._config_to_variables())

            if workflow.variables:
                final_vars.update(workflow.variables)

            if runtime_vars:
                final_vars.update(runtime_vars)

            return final_vars

        except Exception as e:
            print(f"Error previewing variables for workflow '{workflow_name}': {e}")
            return {}
