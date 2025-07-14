# Workflow System

This directory contains modular YAML workflow definitions for the OpenDataHub Gateway API migration project.

## Available Workflows

### Core Modular Workflows
- **`build.yaml`** - Build OpenDataHub operator image (2 steps)
- **`push.yaml`** - Push built image to registry (1 step)  
- **`deploy.yaml`** - Deploy full OpenDataHub stack to Kubernetes (10 steps)

### Composite Workflows
- **`build-push.yaml`** - Build and push operator image (includes: build, push)
- **`build-only.yaml`** - Extended build with status checks (includes: build + 3 additional steps)
- **`build-push-deploy.yaml`** - Complete end-to-end workflow (includes: build, push, deploy)

## Using Workflows

### Configuration
All workflows automatically use variables from `config.yaml`:
- `REGISTRY_URL`, `REGISTRY_NAMESPACE`, `REGISTRY_TAG` - Registry configuration
- `FORK_ORG`, `BRANCH_NAME` - GitHub configuration  
- `BUILD_*` - Build defaults
- Plus all other config sections

### Variable Precedence
Variables are merged in order of precedence:
1. **config.yaml** (lowest precedence)
2. **Included workflows** 
3. **Main workflow** 
4. **Runtime variables** (highest precedence)

### Include System
Workflows can include other workflows using the `includes` field:

```yaml
name: "My Custom Workflow"
description: "Example workflow with includes"

includes:
  - "build"
  - "push"

variables:
  CUSTOM_VAR: "value"

steps:
  - name: "Additional step"
    type: "shell"
    command: "echo"
    args: ["Custom step after includes"]
```

### Step Execution Order
1. Steps from included workflows execute first (in include order)
2. Steps from main workflow execute after all includes

### Circular Include Protection
The system detects and prevents circular includes with clear error messages.

## Workflow Variables

### View Available Variables
```python
from lib import WorkflowEngine
wf = WorkflowEngine()
wf.show_available_variables()
```

### Preview Workflow Variables
```python
# Preview final variables for a workflow
vars = wf.preview_workflow_variables('build-push-deploy')
print(vars)

# With runtime overrides
vars = wf.preview_workflow_variables('build-push-deploy', {'REGISTRY_TAG': 'custom'})
```

## Step Types

### Tool Steps
Execute tool.py subcommands:
```yaml
- name: "Build operator"
  type: "tool"
  command: "build-operator"
  args: ["--image", "--local"]
```

### Kubectl Steps  
Execute kubectl commands:
```yaml
- name: "Deploy operator"
  type: "kubectl"
  command: "apply"
  args: ["-f", "operator.yaml"]
```

### Shell Steps
Execute shell commands:
```yaml
- name: "Show result"
  type: "shell"
  command: "echo"
  args: ["Build completed!"]
```

### Nested Workflows
Execute other workflows:
```yaml
- name: "Run build workflow"
  type: "workflow"
  command: "build"
```

## Best Practices

1. **Use includes** for common step sequences
2. **Keep base workflows focused** - single responsibility
3. **Override variables minimally** - prefer config.yaml defaults
4. **Use descriptive names** for workflow files and steps
5. **Test workflows independently** before composing them

## Examples

### Simple Build
```bash
# Use basic build workflow
python -c "from lib import WorkflowEngine; WorkflowEngine().execute_workflow('build')"
```

### Build with Custom Registry
```bash
# Override registry tag at runtime
python -c "from lib import WorkflowEngine; WorkflowEngine().execute_workflow('build', {'REGISTRY_TAG': 'dev'})"
```

### Full End-to-End
```bash
# Complete build-push-deploy workflow
python -c "from lib import WorkflowEngine; WorkflowEngine().execute_workflow('build-push-deploy')"
``` 