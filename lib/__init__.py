"""
OpenDataHub Security 2.0 Library Package

This package contains modular components for the OpenDataHub Gateway API migration tool.
"""

from .github_wrapper import GitHubWrapper, RepoInfo
from .ansible_engine import AnsibleEngine
from .build_manager import BuildManager, BuildConfig, BuildResult
from .deployment_manager import DeploymentManager, DeploymentConfig, DeploymentResult, DeploymentStatus

# Keep legacy WorkflowEngine for compatibility during transition
try:
    from .workflow_engine import WorkflowEngine, WorkflowDefinition, WorkflowStep
    _legacy_available = True
except ImportError:
    _legacy_available = False

__all__ = [
    'GitHubWrapper',
    'RepoInfo',
    'AnsibleEngine',
    'BuildManager',
    'BuildConfig',
    'BuildResult',
    'DeploymentManager',
    'DeploymentConfig',
    'DeploymentResult',
    'DeploymentStatus'
]

# Add legacy exports if available
if _legacy_available:
    __all__.extend(['WorkflowEngine', 'WorkflowDefinition', 'WorkflowStep']) 