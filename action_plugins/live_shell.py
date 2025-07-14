#!/usr/bin/env python3

# Copyright: (c) 2024, OpenDataHub Security Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import annotations

import os
import subprocess
import shlex
from ansible.plugins.action import ActionBase
from ansible.utils.display import Display
from ansible.errors import AnsibleError

display = Display()

class ActionModule(ActionBase):
    """Custom action plugin that runs shell commands with live output streaming"""
    
    TRANSFERS_FILES = False
    _requires_connection = False
    
    def run(self, tmp=None, task_vars=None):
        """Execute shell command with live output streaming"""
        
        # Call parent run method to get base result
        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp  # tmp no longer has any effect
        
        # Get the shell command from task args
        command = self._task.args.get('cmd', '')
        if not command:
            result['failed'] = True
            result['msg'] = 'cmd parameter is required'
            return result
        
        # Get working directory (chdir)
        chdir = self._task.args.get('chdir', None)
        if chdir:
            chdir = self._templar.template(chdir, task_vars)
        
        # Get environment variables
        env = os.environ.copy()
        task_env = self._task.args.get('environment', {})
        if task_env:
            for key, value in task_env.items():
                env[key] = self._templar.template(str(value), task_vars)
        
        # Command is already templated by Ansible before reaching action plugin
        templated_command = command
        
        # Display what we're running
        display.vv(f"TASK OUTPUT: Running command: {templated_command}")
        if chdir:
            display.vv(f"TASK OUTPUT: Working directory: {chdir}")
        
        try:
            # Execute the command with live output
            process = subprocess.Popen(
                templated_command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # Merge stderr into stdout
                universal_newlines=True,
                bufsize=1,  # Line buffered
                cwd=chdir,
                env=env
            )
            
            # Stream output line by line
            output_lines = []
            while True:
                line = process.stdout.readline()
                if line:
                    # Remove trailing newline for display, but keep for storage
                    display_line = line.rstrip('\n')
                    display.display(f"TASK OUTPUT: {display_line}")
                    output_lines.append(line)
                elif process.poll() is not None:
                    break
            
            # Wait for process to complete
            return_code = process.wait()
            
            # Prepare result
            result['rc'] = return_code
            result['stdout'] = ''.join(output_lines)
            result['stderr'] = ''  # We merged stderr into stdout
            result['changed'] = True  # Assume shell commands change something
            
            if return_code != 0:
                result['failed'] = True
                result['msg'] = f'Command failed with return code {return_code}'
            else:
                result['failed'] = False
                
        except Exception as e:
            result['failed'] = True
            result['msg'] = f'Error executing command: {str(e)}'
            result['rc'] = -1
            
        return result 