import yaml
import os
import subprocess
import tempfile
import sys
from typing import Dict, List, Any, Optional
from pathlib import Path


class AnsibleEngine:
    """Engine for executing Ansible-based workflows using task files"""

    def __init__(self, project_root: str = None):
        """Initialize the Ansible engine

        Args:
            project_root: Root directory of the project. If None, auto-detected.
        """
        self.project_root = project_root or self._find_project_root()
        self.tasks_dir = os.path.join(self.project_root, "tasks")
        self.config_file = os.path.join(self.project_root, "config.yaml")
        self.config = self._load_config()

    def _find_project_root(self) -> str:
        """Find the project root directory by looking for config.yaml"""
        current_dir = os.getcwd()

        while current_dir != "/":
            if os.path.exists(os.path.join(current_dir, "config.yaml")):
                return current_dir
            current_dir = os.path.dirname(current_dir)

        # Fallback to current directory
        return os.getcwd()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from config.yaml"""
        if not os.path.exists(self.config_file):
            return {}

        try:
            with open(self.config_file, "r") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Warning: Could not load config file {self.config_file}: {e}")
            return {}

    def _config_to_variables(
        self, runtime_vars: Dict[str, str] = None
    ) -> Dict[str, Any]:
        """Convert config and runtime variables to Ansible variables

        Args:
            runtime_vars: Runtime variable overrides

        Returns:
            Dictionary of variables for Ansible playbook
        """
        variables = {}

        # Add project paths
        variables.update(
            {
                "project_root": self.project_root,
                "local_checkouts_dir": os.path.join(self.project_root, "src"),
                "tasks_dir": self.tasks_dir,
            }
        )

        # Add config variables with Ansible-friendly names
        if "github" in self.config:
            github_config = self.config["github"]
            variables.update(
                {
                    "fork_org": github_config.get("fork_org"),
                    "branch_name": github_config.get("branch_name"),
                    "base_branch": github_config.get("base_branch"),
                }
            )

        if "registry" in self.config:
            registry_config = self.config["registry"]
            variables.update(
                {
                    "registry_url": registry_config.get("url"),
                    "registry_namespace": registry_config.get("namespace"),
                    "registry_tag": registry_config.get("tag"),
                }
            )

        if "build" in self.config:
            build_config = self.config["build"]
            variables.update(
                {
                    "build_local": build_config.get("local"),
                    "build_use_branch": build_config.get("use_branch"),
                    "build_image": build_config.get("image"),
                    "build_custom_registry": build_config.get("custom_registry"),
                    "build_manifests_only": build_config.get("manifests_only"),
                }
            )

        # Add deployment defaults
        deployment_config = self.config.get("deployment", {})
        variables.update(
            {
                "namespace": deployment_config.get("namespace", "opendatahub"),
                "wait_timeout": deployment_config.get("wait_timeout", 300),
                "dsci_config": deployment_config.get("dsci", {}),
                "dsc_config": deployment_config.get("dsc", {}),
            }
        )

        # Add runtime variable overrides
        if runtime_vars:
            variables.update(runtime_vars)

        # Remove None values
        variables = {k: v for k, v in variables.items() if v is not None}

        return variables

    def list_tasks(self) -> List[str]:
        """List all available task files

        Returns:
            List of task file names (without .yml extension)
        """
        if not os.path.exists(self.tasks_dir):
            return []

        task_files = []
        for file in os.listdir(self.tasks_dir):
            if file.endswith(".yml") or file.endswith(".yaml"):
                task_name = os.path.splitext(file)[0]
                task_files.append(task_name)

        return sorted(task_files)

    def task_exists(self, task_name: str) -> bool:
        """Check if a task file exists

        Args:
            task_name: Name of the task file (without extension)

        Returns:
            True if task file exists, False otherwise
        """
        task_file = os.path.join(self.tasks_dir, f"{task_name}.yml")
        alt_task_file = os.path.join(self.tasks_dir, f"{task_name}.yaml")
        return os.path.exists(task_file) or os.path.exists(alt_task_file)

    def get_task_file_path(self, task_name: str) -> Optional[str]:
        """Get the full path to a task file

        Args:
            task_name: Name of the task file (without extension)

        Returns:
            Full path to task file, or None if not found
        """
        task_file = os.path.join(self.tasks_dir, f"{task_name}.yml")
        if os.path.exists(task_file):
            return task_file

        alt_task_file = os.path.join(self.tasks_dir, f"{task_name}.yaml")
        if os.path.exists(alt_task_file):
            return alt_task_file

        return None

    def generate_playbook(
        self, task_name: str, variables: Dict[str, Any] = None
    ) -> str:
        """Generate an Ansible playbook that includes the specified task file

        Args:
            task_name: Name of the task file to include
            variables: Variables to pass to the playbook

        Returns:
            Playbook content as YAML string
        """
        if variables is None:
            variables = {}

        # Get all variables including config and runtime overrides
        all_variables = self._config_to_variables(runtime_vars=variables)

        # Get the absolute path to the task file
        task_file_path = self.get_task_file_path(task_name)
        if not task_file_path:
            raise ValueError(f"Task file '{task_name}' not found")

        playbook_data = [
            {
                "name": f"Execute {task_name} tasks",
                "hosts": "localhost",
                "connection": "local",
                "gather_facts": False,
                "vars": all_variables,
                "tasks": [
                    {
                        "name": f"Include {task_name} tasks",
                        "include_tasks": task_file_path,
                    }
                ],
            }
        ]

        return yaml.dump(playbook_data, default_flow_style=False, sort_keys=False)

    def execute_task(
        self, task_name: str, variables: Dict[str, str] = None, verbose: bool = False
    ) -> bool:
        """Execute a task file using Ansible

        Args:
            task_name: Name of the task file to execute
            variables: Runtime variable overrides
            verbose: Enable verbose output

        Returns:
            True if execution succeeded, False otherwise
        """
        if not self.task_exists(task_name):
            print(f"Error: Task file '{task_name}' not found in {self.tasks_dir}")
            return False

        print(f"Executing task: {task_name}")

        # Generate playbook content
        try:
            playbook_content = self.generate_playbook(task_name, variables)
        except ValueError as e:
            print(f"Error: {e}")
            return False

        if verbose:
            print("Generated playbook:")
            print(playbook_content)
            print("-" * 40)

        # Create temporary playbook file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write(playbook_content)
            playbook_path = f.name

        try:
            # Prepare ansible-playbook command
            cmd = ["ansible-playbook"]

            if verbose:
                cmd.append("-v")

            # Set ANSIBLE_HOST_KEY_CHECKING=False to avoid SSH key checking issues
            env = os.environ.copy()
            env["ANSIBLE_HOST_KEY_CHECKING"] = "False"

            # Set action plugins path so Ansible can find our custom live_shell plugin
            action_plugins_path = os.path.join(self.project_root, "action_plugins")
            env["ANSIBLE_ACTION_PLUGINS"] = action_plugins_path

            # Set library path so Ansible can find our custom live_shell module
            library_path = os.path.join(self.project_root, "library")
            env["ANSIBLE_LIBRARY"] = library_path

            # Set config file path to ensure correct ansible.cfg is used
            ansible_cfg_path = os.path.join(self.project_root, "ansible.cfg")
            env["ANSIBLE_CONFIG"] = ansible_cfg_path

            # Change to project root directory so action plugins can be found
            cmd.extend(["-i", "localhost,", playbook_path])

            print(f"Running: {' '.join(cmd)}")

            # Execute ansible-playbook
            result = subprocess.run(
                cmd,
                cwd=self.project_root,  # Run from project root to find action plugins
                env=env,
                capture_output=False,  # Always stream output live for debugging
                text=True,
            )

            success = result.returncode == 0
            print(
                f"Task {task_name} {'succeeded' if success else 'failed'} (exit code: {result.returncode})"
            )

            return success

        except FileNotFoundError:
            print(
                "Error: ansible-playbook command not found. Please install ansible-core:"
            )
            print("  pip install ansible-core")
            return False
        except Exception as e:
            print(f"Error executing task {task_name}: {e}")
            return False
        finally:
            # Clean up temporary playbook file
            try:
                os.unlink(playbook_path)
            except Exception:
                pass

    def show_task_info(self, task_name: str) -> None:
        """Display information about a task file

        Args:
            task_name: Name of the task file to show
        """
        task_path = self.get_task_file_path(task_name)
        if not task_path:
            print(f"Task '{task_name}' not found")
            return

        print(f"Task: {task_name}")
        print(f"File: {task_path}")
        print(f"Tasks directory: {self.tasks_dir}")
        print()

        try:
            with open(task_path, "r") as f:
                content = f.read()
                print("Task file content:")
                print("-" * 40)
                print(content)
        except Exception as e:
            print(f"Error reading task file: {e}")

    def get_available_variables(self) -> Dict[str, Any]:
        """Get all available variables for tasks

        Returns:
            Dictionary of available variables
        """
        return self._config_to_variables()

    def show_available_variables(self) -> None:
        """Print all available variables"""
        variables = self.get_available_variables()

        print("Available Ansible variables:")
        print()

        # Group variables by category
        categories = {
            "Project Paths": ["project_root", "local_checkouts_dir", "tasks_dir"],
            "GitHub Settings": ["fork_org", "branch_name", "base_branch"],
            "Registry Settings": ["registry_url", "registry_namespace", "registry_tag"],
            "Build Settings": [
                "build_local",
                "build_use_branch",
                "build_image",
                "build_custom_registry",
                "build_manifests_only",
            ],
        }

        for category, var_names in categories.items():
            category_vars = {k: v for k, v in variables.items() if k in var_names}
            if category_vars:
                print(f"{category}:")
                for name, value in category_vars.items():
                    print(f"  {name}: {value}")
                print()

        # Show any additional variables
        shown_vars = set()
        for var_names in categories.values():
            shown_vars.update(var_names)

        additional_vars = {k: v for k, v in variables.items() if k not in shown_vars}
        if additional_vars:
            print("Additional Variables:")
            for name, value in additional_vars.items():
                print(f"  {name}: {value}")
            print()
