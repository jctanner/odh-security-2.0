# CONTEXT.md

## Purpose
This file tracks the factual state, requests, and rules for this project. It serves as a persistent memory for LLM interactions to maintain continuity across sessions.

**LLM Instructions**: Read this file at the start of each session. Update it immediately after completing requests or when project rules change. Keep entries factual and concise. Do not add commentary, emoji, or marketing language.

## Project Overview
- **Project Name**: odh-security-2.0
- **Repository**: /home/jtanner/workspace/github/jctanner.redhat/odh-security-2.0
- **Status**: Development environment ready, analysis phase next
- **Created**: [Date of first session]
- **Purpose**: Refactor entire opendatahub-io project to use Gateway API

## Project Scope Summary
This project has established a comprehensive development infrastructure for migrating the OpenDataHub ecosystem from current networking implementation to Gateway API. The scope includes:

### **Core Mission**
- Migrate networking components in OpenDataHub to use Gateway API
- Target all repositories that comprise the OpenDataHub operator ecosystem
- Maintain compatibility and functionality during migration

### **Infrastructure Established**
- Fork-based development workflow with feature branches
- Local development environment with multiple build modes
- Automated repository management and build orchestration
- Comprehensive tooling for multi-repository coordination

## Active Requests
*Track current and pending requests*

1. **Gateway API Migration** (In Progress)
   - Refactor entire opendatahub-io project and related repositories to use Gateway API
   - Approach: Multi-repository patching using src/ directory checkouts
   - Status: Development environment setup complete, ready for analysis

## Completed Requests
*Move finished requests here with completion date*

1. **Initial Setup** (Completed)
   - Created CONTEXT.md file
   - Date: Initial session

2. **Directory Structure Setup** (Completed)
   - Created src/ directory for GitHub project checkouts
   - Date: Current session

3. **Git Configuration** (Completed)
   - Created .gitignore to prevent committing src/ contents
   - Date: Current session

4. **Security Setup** (Completed)
   - Created secure token file (not committed to git)
   - Date: Current session

5. **GitHub Automation** (Completed)
   - Created Python wrapper script for GitHub CLI operations
   - Features: repository forking, cloning, branch management
   - Date: Current session

6. **Command Line Interface** (Completed)
   - Added argparse with subcommands to tool.py
   - Subcommands: whoami, list-repos, fork-repo, clone-repo
   - Authentication verification via whoami command
   - Date: Current session

7. **Project Configuration** (Completed)
   - Created config.yaml with fork organization and branch settings
   - Updated tool.py to use configuration file
   - Added show-config and fork-all subcommands
   - Configured target repositories for migration
   - Date: Current session

8. **Fork Organization Update** (Completed)
   - Changed fork organization to jctanner-opendatahub-io
   - Updated config.yaml configuration
   - Date: Current session

9. **Operator Setup Command** (Completed)
   - Added setup-operator command for comprehensive workflow
   - Checks for existing fork, creates if needed
   - Clones repository, sets up upstream, rebases, creates feature branch
   - Only proceeds if local checkout doesn't exist (unless --force used)
   - Added opendatahub-operator to target repositories list
   - Date: Current session

10. **OpenDataHub Operator Setup** (Completed)
    - Successfully executed setup-operator command
    - Fork exists at jctanner-opendatahub-io/opendatahub-operator
    - Repository cloned to src/opendatahub-operator
    - Upstream remote configured, repository rebased
    - Feature branch 'gateway-api-migration' created
    - Ready for Gateway API migration development
    - Date: Current session

11. **Tool Rename** (Completed)
    - Renamed github_wrapper.py to tool.py
    - Reflects expanded scope beyond GitHub operations
    - Updated documentation and references
    - Date: Current session

12. **Build System Integration** (Completed)
    - Added build-operator subcommand to tool.py
    - Patched get_all_manifests.sh to support fork organization and local checkouts
    - Patched Makefile with new targets: get-manifests-fork, get-manifests-local, image-build-fork, image-build-local
    - Patched Dockerfile to handle new build arguments: FORK_ORG, LOCAL_MODE, LOCAL_CHECKOUTS_DIR
    - Updated image-build-local to use parent directory as build context for local checkouts
    - Supports building with fork repositories or local checkouts
    - Date: Current session

13. **Feature Branch Support** (Completed)
    - Added --branch parameter to get_all_manifests.sh script
    - Added BRANCH_NAME variable and support to Makefile
    - Added new make targets: get-manifests-fork-branch, get-manifests-local-branch, image-build-fork-branch, image-build-local-branch
    - Updated Dockerfile to support BRANCH_NAME build argument
    - Added --use-branch flag to build-operator command in tool.py
    - Build process now supports using gateway-api-migration feature branch from config.yaml
    - Date: Current session

14. **Working Directory Flexibility** (Completed)
    - Updated GitHubWrapper to automatically find config.yaml and .github_token files in project root
    - Tool can now be run from anywhere within the project directory tree
    - No longer requires changing to specific directories to run commands
    - Improved user experience by eliminating directory navigation requirements
    - Date: Current session

15. **Local Manifests Pre-population** (Completed)
    - Redesigned local checkout workflow to pre-populate opt/manifests/ on host before Docker build
    - Added SKIP_MANIFESTS_FETCH environment variable to prevent Docker build from overwriting manifests
    - Updated image-build-local targets to call get-manifests-local before building
    - Cleaner separation between host-based manifest preparation and container building
    - Date: Current session

16. **Git Authentication Hanging Fix** (Completed)
    - Added environment variables to prevent git from prompting for credentials (GIT_TERMINAL_PROMPT=0, GIT_ASKPASS="", SSH_ASKPASS="")
    - Implemented repository existence check using 'gh repo view' before attempting git clone
    - Added graceful error handling for non-existent fork repositories
    - Enhanced error reporting with specific component failures and helpful suggestions
    - Build process now fails fast instead of hanging on missing repositories
    - Date: Current session

17. **Setup-Forks Subcommand** (Completed)
    - Created idempotent setup-forks subcommand to address repository gap (Known Issue #1)
    - Parses get_all_manifests.sh COMPONENT_MANIFESTS array to extract all 15 required repositories
    - Automatically forks, clones, and creates feature branches for all manifest dependencies
    - Added --dry-run option for safe preview of operations without making changes
    - Added --skip-existing option to only process missing repositories
    - Comprehensive status reporting with success/failure/skip tracking
    - Eliminates manual setup of 15+ repositories needed for local manifest building
    - Date: Current session

18. **SSH Origins and Repository-Specific Base Branches** (Completed)
    - Fixed clone_repository() to use SSH URLs (git@github.com:) for fork origins instead of HTTPS
    - Upstream remotes remain HTTPS for broader compatibility
    - Enhanced parse_manifest_repositories() to extract repository-specific base branches from get_all_manifests.sh
    - Implemented repository-specific base branch handling (stable, dev, release-* branches)
    - Added 3-second delay between fork creation and cloning to prevent race conditions
    - Fixed create_branch() to handle different default branch names across repositories
    - All 15 repositories now successfully set up with correct base branches and SSH origins
    - Date: Current session

19. **Multi-Repository Status and Commit Management** (Completed)
    - Added forks-status subcommand to display status of all local repositories
    - Added forks-commit subcommand to commit and push changes across all repositories
    - Compact display format: ORG/REPO:BRANCH with clean/dirty status and change summary
    - Change notation: 2M (modified), 1U (untracked), 3A (added), 1D (deleted)
    - Remote URLs display: Shows origin (SSH) and upstream (HTTPS) URLs for each repository
    - Filter option: --dirty flag to show only repositories with uncommitted changes
    - Logging suppression by default for clean output, verbose mode available
    - Comprehensive commit workflow with detailed progress reporting
    - Supports custom commit messages and handles repositories with no changes
    - Enables efficient management of changes across 15+ repositories simultaneously
    - Date: Current session

20. **Build Configuration Defaults** (Completed)
    - Added build section to config.yaml with default settings for build-operator command
    - Added getter methods to GitHubWrapper for retrieving build configuration defaults
    - Modified cmd_build_operator to apply config defaults when command-line arguments aren't provided
    - Command-line arguments can override config defaults for specific flags
    - Enhanced show-config to display build configuration section
    - Updated help text and usage examples to mention config defaults
    - Clear feedback showing which defaults were applied from configuration
    - Simplified usage: build-operator command can now run with no arguments using preferred defaults
    - Supports local, use_branch, image, custom_registry, and manifests_only defaults
    - Date: Current session

21. **Build System Troubleshooting and Resolution** (Completed)
    - Identified build-operator command failing due to broken YAML parsing in Makefile
    - Root cause: sed commands in custom registry targets couldn't parse config.yaml registry section
    - Fixed image-build-custom-registry-local-branch and image-push-custom-registry targets
    - Replaced broken sed commands with working awk commands for registry URL, namespace, and tag extraction
    - Successful build completion with all features working: local checkouts, feature branch, custom registry
    - Confirmed full build system functionality: manifest pre-population, multi-stage Docker build, custom registry tagging
    - Build system now fully tested and operational for Gateway API migration development
    - Date: Current session

22. **Makefile Environment Variable Refactoring** (Completed)
    - Refactored Makefile to use environment variables instead of parsing config.yaml directly
    - Removed all hardcoded ../../config.yaml references and sed/awk parsing commands
    - Added environment variable defaults: FORK_ORG, BRANCH_NAME, CUSTOM_REGISTRY_URL, CUSTOM_REGISTRY_NAMESPACE, CUSTOM_REGISTRY_TAG
    - Updated tool.py to set appropriate environment variables when calling make commands
    - Cleaner separation of concerns: Makefile handles build logic, tool.py handles configuration
    - Improved maintainability and eliminated brittle YAML parsing in shell scripts
    - All build targets now use environment variables with proper validation
    - Date: Current session

## Established Requirements
*Technical and operational requirements we must follow*

### **Development Workflow**
1. **Fork Organization**: All forks created under `jctanner-opendatahub-io` organization
2. **Feature Branch**: Use `gateway-api-migration` branch across all repositories for this work
3. **Base Branch**: Create feature branches from repository-specific base branches defined in get_all_manifests.sh
4. **Upstream Tracking**: All forks must have upstream remotes configured for rebasing

### **Repository Management**
5. **Checkout Location**: All repository checkouts must be in `src/` subdirectory
6. **Build Modes**: Support both fork repository and local checkout workflows
7. **Branch Support**: Build system must support using feature branches from config.yaml
8. **Multi-Repository**: Handle 16+ repositories that comprise OpenDataHub manifest dependencies

### **Security and Authentication**
9. **Token Security**: GitHub token stored in `.github_token` file, never committed or documented
10. **Git Authentication**: Must prevent git credential prompting to avoid hanging
11. **Fast Failure**: Repository existence checks required before git operations
12. **SSH Origins**: Fork repositories must use SSH URLs (git@github.com:) for origins
13. **Race Condition Prevention**: Delays required between fork creation and cloning operations

### **Build System**
14. **Working Directory**: Tool must work from anywhere within project directory tree
15. **Environment Variables**: Consistent use of build arguments and environment variables
16. **Command Visibility**: All build commands must show full execution details
17. **Manifest Pre-population**: Local mode must pre-populate manifests before Docker build
18. **Configuration-Driven Defaults**: Build commands must support config-driven defaults with command-line override capability
19. **Environment Variable Architecture**: Makefile must use environment variables exclusively, never parse config files directly
20. **Environment Variable Validation**: All Makefile targets must validate required environment variables with helpful error messages
21. **Configuration Separation**: tool.py handles configuration reading, Makefile handles build logic only

### **Tool Behavior**
19. **Configuration Discovery**: Automatically find config.yaml and token files in project root
20. **Error Handling**: Graceful failure with helpful error messages and suggestions
21. **Repository Dependencies**: Handle missing fork repositories without hanging or failing silently
22. **Repository-Specific Branches**: Use base branches defined in get_all_manifests.sh for each repository
23. **Multi-Repository Management**: Provide commands to check status and commit changes across all repositories
24. **Clean Output**: Suppress verbose logging by default for status commands, enable with --verbose flag
25. **Status Filtering**: Support filtering repository status display to show only repositories with changes
26. **Configuration Transparency**: Show which defaults were applied from configuration versus command-line arguments
27. **Environment Variable Setting**: tool.py must set all required environment variables before calling make commands
28. **Build Environment Isolation**: All configuration values must be passed to Makefile via environment variables, not shared files

## Negative Requirements
*Explicit constraints on what we will NOT do*

### **Documentation and Communication**
1. **No Emoji or Buzzwords**: Documentation must remain factual and professional
2. **No Automatic Documentation**: Never create README.md or documentation files unless explicitly requested
3. **No Commentary**: Keep CONTEXT.md entries factual without editorial comments

### **Security and Privacy**
4. **No Token Exposure**: Never document, log, or commit GitHub token contents
5. **No Credential Storage**: Never store credentials in code or configuration files
6. **No Authentication Prompts**: Never allow git operations that could prompt for credentials

### **Code and Build Practices**  
7. **No Iterative Fixing**: Don't loop more than 3 times fixing linter errors on same file
8. **No Parameter Invention**: Never make up values for optional parameters
9. **No Directory Pollution**: Never commit src/ directory contents to main repository
10. **No Build Context Copying**: Don't copy entire local checkouts into Docker build context
11. **No Config File Parsing in Makefile**: Never parse config.yaml or other configuration files directly in Makefile targets
12. **No Hardcoded Config Paths**: Never hardcode paths to configuration files (e.g., ../../config.yaml) in build scripts

### **Development Workflow**
11. **No Manual Processes**: Don't require manual directory navigation for tool operation
12. **No Silent Failures**: Don't allow operations to fail without clear error reporting
13. **No Blocking Operations**: Don't perform operations that could hang indefinitely
14. **No Custom Formats**: Don't use non-standard tool call formats or syntax

### **Project Scope**
15. **No Architecture Changes**: Don't modify core OpenDataHub architecture beyond networking
16. **No Breaking Changes**: Don't introduce changes that break existing functionality
17. **No Feature Additions**: Focus only on Gateway API migration, not new features

## Project Rules
*Operational guidelines for maintaining project integrity*

1. Update CONTEXT.md after each significant change or request completion
2. All target repositories defined in config.yaml for consistent migration  
3. Fork organization and branch naming must follow config.yaml settings
4. Each project checkout will be patched for Gateway API migration
5. Comprehensive error handling with actionable suggestions required

## Technical State
*Current codebase and configuration status*

- **Files**: 6 (CONTEXT.md, src/, .gitignore, .github_token, tool.py, config.yaml)
- **Structure**: src/ directory for GitHub project checkouts with 15 repositories
- **Git Configuration**: .gitignore prevents committing src/ contents and token file
- **Authentication**: Secure token file configured, git credential prompting disabled
- **Configuration**: YAML config file with fork organization, branch settings, and build defaults
- **Automation**: Multi-purpose Python tool for project management (tool.py)
- **Repository Setup**: All 15 required repositories forked, cloned, and configured with feature branches
- **Target Repositories**: 15 repositories successfully set up with SSH origins and repository-specific base branches
- **Multi-Repository Management**: forks-status and forks-commit commands for efficient change management
- **Build System**: Fully operational with environment variable architecture, config-driven defaults, local checkout workflow, feature branch support, and custom registry integration
- **Build System Testing**: Complete end-to-end testing confirmed - manifest pre-population, multi-stage Docker build, custom registry tagging all working
- **Build Architecture**: Environment variable-based configuration with clean separation between tool.py (configuration) and Makefile (build logic)
- **Current Architecture**: Analysis required - networking implementation unknown
- **Target Architecture**: Gateway API (migration approach to be determined)
- **Dependencies**: GitHub CLI ('gh'), Python 3.6+, PyYAML, podman/docker
- **Testing**: Build system fully tested and operational, application testing pending analysis

## Architecture Decisions
*Record significant technical decisions and rationale*

1. **Gateway API Adoption** (Planned)
   - Migration from current networking solution to Gateway API
   - Rationale: [To be documented during analysis phase]

2. **Environment Variable Build Architecture** (Implemented)
   - Makefile uses environment variables exclusively, never parses config files directly
   - tool.py reads configuration and sets environment variables before calling make
   - Rationale: Clean separation of concerns, improved maintainability, eliminates brittle YAML parsing in shell scripts
   - Benefits: Better testability, cleaner error handling, improved performance

## Known Issues
*Track bugs, limitations, or technical debt*

1. **Repository Mismatch** (✅ Resolved)
   - config.yaml defines 7 target repositories for migration
   - get_all_manifests.sh requires 15 repositories for manifest dependencies
   - ✅ Resolved by setup-forks subcommand that handles all manifest dependencies

2. **Missing Fork Repositories** (✅ Resolved)
   - Most repositories in jctanner-opendatahub-io organization didn't exist
   - Build system handles this gracefully with fast failure and helpful error messages
   - ✅ Resolved by setup-forks subcommand that creates all necessary forks with proper configuration

3. **Branch Consistency and SSH Origins** (✅ Resolved)
   - Feature branches needed to be created consistently across all fork repositories
   - Some repositories use different default branch names (main vs master vs stable vs dev)
   - HTTPS origins caused authentication issues with private/missing repositories
   - ✅ Resolved by repository-specific base branch handling and SSH origins for forks

## Next Steps
*Immediate planned actions*

1. **Architecture Analysis Phase** (Ready to Begin)
   - Analyze current networking implementation in opendatahub-operator
   - Identify all networking components that need Gateway API migration
   - Document current Ingress/Route/Service usage patterns
   - Map dependencies between networking components

2. **Repository Dependency Management** (✅ Complete)
   - ✅ Created setup-forks subcommand to fork all 15 required repositories
   - ✅ Ensures all manifest dependencies have proper forks with feature branches
   - ✅ Addressed the gap between config.yaml repos and get_all_manifests.sh requirements
   - ✅ Implemented SSH origins and repository-specific base branch handling
   - ✅ All repositories successfully set up with correct configuration

3. **Build System Development** (✅ Complete)
   - ✅ Implemented config-driven build defaults for simplified usage
   - ✅ Troubleshot and resolved YAML parsing issues in Makefile
   - ✅ Confirmed end-to-end build functionality with local checkouts, feature branches, and custom registry
   - ✅ Full build system operational for Gateway API migration development

4. **Migration Strategy Development** (Next Phase)
   - Define Gateway API migration approach based on analysis
   - Create step-by-step migration plan with validation checkpoints
   - Establish testing strategy for networking changes

5. **Implementation Phase** (Future)
   - Begin Gateway API migration in opendatahub-operator
   - Coordinate changes across dependent repositories
   - Validate networking functionality throughout migration

6. **Validation and Testing** (Future)
   - Test Gateway API implementation in development environment
   - Verify compatibility with existing OpenDataHub deployments
   - Document any breaking changes or migration requirements

---
*Last Updated: 2025-01-11 16:15 UTC - Makefile Environment Variable Refactoring Complete* 