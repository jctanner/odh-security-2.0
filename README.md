# OpenDataHub Gateway API Migration Tool

A comprehensive tool for migrating the OpenDataHub ecosystem from current networking implementation to Gateway API.

## Prerequisites

- Python 3.8 or higher
- Git
- GitHub CLI (`gh`) installed and authenticated
- Podman or Docker for container operations
- kubectl for Kubernetes operations

## Setup

### 1. Create Virtual Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # On Linux/macOS
# or
venv\Scripts\activate     # On Windows
```

### 2. Install Dependencies

```bash
# Install Python dependencies
pip install -r requirements.txt

# Verify Ansible installation
ansible --version
```

### 3. Configure Authentication

```bash
# Authenticate with GitHub CLI (if not already done)
gh auth login

# The tool will automatically use your GitHub CLI authentication
```

### 4. Initial Setup

```bash
# Verify authentication and show configuration
python tool.py whoami
python tool.py show-config

# Set up all required repository forks
python tool.py setup-forks

# Check repository status
python tool.py forks-status
```

## Usage

### Repository Management

```bash
# Set up a specific repository
python tool.py setup-operator

# Check status of all repositories
python tool.py forks-status
python tool.py forks-status --dirty

# Commit changes across all repositories
python tool.py forks-commit
python tool.py forks-commit -m "Custom commit message"
```

### Workflow Execution (Ansible-based)

```bash
# List available workflows
python tool.py workflow --list

# Show workflow details
python tool.py workflow --show build

# Execute workflows
python tool.py workflow --name build --exec
python tool.py workflow --name build-push-deploy --exec

# Execute with variable overrides
python tool.py workflow --name build --exec --var REGISTRY_TAG=dev
python tool.py workflow --name deploy --exec --var NAMESPACE=test

# View available variables
python tool.py workflow --vars
python tool.py workflow --vars build
```

## Architecture

This tool uses:

- **Ansible**: For robust workflow execution with task files
- **GitHub CLI**: For repository management and authentication  
- **Python**: For the main CLI interface and GitHub operations
- **YAML**: For configuration and workflow definitions

## Project Structure

```
odh-security-2.0/
├── config.yaml              # Project configuration
├── requirements.txt          # Python dependencies
├── tool.py                   # Main CLI interface
├── lib/                      # Python modules
│   ├── github_wrapper.py     # GitHub operations
│   ├── build_manager.py      # Build management
│   ├── deployment_manager.py # Deployment operations
│   └── ansible_engine.py     # Ansible workflow execution
├── tasks/                    # Ansible task files
│   ├── build.yml            # Build tasks
│   ├── push.yml             # Push tasks
│   ├── deploy.yml           # Deploy tasks
│   └── ...
└── src/                     # Local repository checkouts
    ├── opendatahub-operator/
    ├── odh-dashboard/
    └── ...
```

## Development

The virtual environment isolates dependencies and ensures consistent behavior across development environments.

```bash
# Always activate the virtual environment before working
source venv/bin/activate

# Install additional development dependencies if needed
pip install <package>

# Update requirements.txt when adding new dependencies
pip freeze > requirements.txt
``` 

# ODH Dashboard

make build push IMAGE_REPOSITORY=registry.tannerjc.net/odh-dashboard:byoidc


# Notebooks
cd src/kubeflow/components/
podman build -t registry.tannerjc.net/odh-notebooks:byoidc -f odh-notebook-controller/Dockerfile .
podman push registry.tannerjc.net/odh-notebooks:byoidc
