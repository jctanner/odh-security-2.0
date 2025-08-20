#!/usr/bin/env python3

# Copyright: (c) 2024, OpenDataHub Security Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: live_shell
short_description: Execute shell commands with live output streaming
description:
    - Execute shell commands with live output streaming to stdout
    - Similar to the shell module but with real-time output display
    - Useful for long-running build processes where you want to see progress
version_added: "1.0.0"
options:
    cmd:
        description:
            - The shell command to execute
        type: str
        required: true
    chdir:
        description:
            - Change into this directory before running the command
        type: path
        required: false
    environment:
        description:
            - Environment variables to set when executing the command
        type: dict
        required: false
author:
    - OpenDataHub Security Project
"""

EXAMPLES = r"""
- name: Run a build command with live output
  live_shell:
    cmd: make build
    chdir: /path/to/project
    environment:
      BUILD_ENV: production

- name: Simple command with live output
  live_shell:
    cmd: echo "Hello World"
"""

RETURN = r"""
rc:
    description: The return code of the command
    type: int
    returned: always
stdout:
    description: The standard output of the command
    type: str
    returned: always
stderr:
    description: The standard error of the command (merged with stdout)
    type: str
    returned: always
changed:
    description: Whether the command execution changed the system
    type: bool
    returned: always
"""

from ansible.module_utils.basic import AnsibleModule


def main():
    """Main module function - this is just a placeholder since the action plugin does the real work"""

    module = AnsibleModule(
        argument_spec=dict(
            cmd=dict(type="str", required=True),
            chdir=dict(type="path", required=False),
            environment=dict(type="dict", required=False),
        ),
        supports_check_mode=False,
    )

    # This module should never be called directly - the action plugin handles execution
    module.fail_json(msg="live_shell module should be handled by the action plugin")


if __name__ == "__main__":
    main()
