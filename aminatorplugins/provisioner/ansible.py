# -*- coding: utf-8 -*-
#
#  Copyright 2013 Answers for AWS LLC
#
#     Licensed under the Apache License, Version 2.0 (the "License");
#     you may not use this file except in compliance with the License.
#     You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#     Unless required by applicable law or agreed to in writing, software
#     distributed under the License is distributed on an "AS IS" BASIS,
#     WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#     See the License for the specific language governing permissions and
#     limitations under the License.
#

"""
aminator.plugins.provisioner.ansible
====================================
Ansible provisioner
"""

import logging
import os
import shutil

from aminator.plugins.provisioner.base import BaseProvisionerPlugin
from aminator.config import conf_action
from aminator.util.linux import command

__all__ = ('AnsibleProvisionerPlugin',)
log = logging.getLogger(__name__)


class AnsiblePluginException(Exception):
    pass

class AnsibleProvisionerPlugin(BaseProvisionerPlugin):
    """
    AnsibleProvisionerPlugin takes the majority of its behavior from BaseLinuxProvisionerPlugin
    See BaseLinuxProvisionerPlugin for details
    """
    _name = 'ansible'


    def add_plugin_args(self):
        """ Add Ansible specific variables """

        ansible_config = self._parser.add_argument_group(title='Ansible Options', description='Options for the Ansible provisioner')

        ansible_config.add_argument('-ev', '--extra-vars', dest='extravars', help='A set of additional key=value variables to be used in the playbook',
                                 action=conf_action(self._config.plugins[self.full_name]))

        ansible_config.add_argument('--app-version', dest='appversion', help='Manually set the application version number so it is tagging in the AMI',
                                 action=conf_action(self._config.plugins[self.full_name]))

        ansible_config.add_argument('--playbooks-path', dest='playbooks_path_source', help='Absolute path to the playbooks to be copied over the chroot env.',
                                 action=conf_action(self._config.plugins[self.full_name]))

        ansible_config.add_argument('--vault-password', dest='vault_password', help='Flag if a vault password has to be provided to Ansible.',
                                 action=conf_action(self._config.plugins[self.full_name], action='store_true'))





    def _write_local_inventory(self):
        """ Writes a local inventory file inside the chroot environment """

        context = self._config.context
        config = self._config.plugins[self.full_name]
        path = config.get('inventory_file_path', '/etc/ansible')
        filename = path + "/" + config.get('inventory_file')
        context.package.inventory = filename

        if not os.path.isdir(path):
            log.debug("creating %s", path)
            os.makedirs(path)
            log.debug("created %s", path)

        with open(filename, 'w') as f:
            log.debug("writing %s", filename)
            f.write(config.get('inventory_file_content'))
            log.debug("wrote %s", filename)

        return True


    def _pre_chroot_block(self):
        """ Run commands after mounting the volume, but before chroot'ing """

        self._copy_playbooks()


    def _copy_playbooks(self):
        """ Copies all playbook files from the aminator server (outside the
            chroot) to the chroot environment """

        config = self._config.plugins[self.full_name]
        playbooks_path_source = config.get('playbooks_path_source')
        playbooks_path_dest = self._distro._mountpoint + config.get('playbooks_path_dest')

        if not os.path.isdir(playbooks_path_source):
            log.critical("directory does not exist %s", playbooks_path_source)

        if os.path.isdir(playbooks_path_dest):
            log.critical("directory already exists %s", playbooks_path_dest)
            return False

        shutil.copytree(playbooks_path_source, playbooks_path_dest)
        # pass in vault password into the chroot env
        if config.get('vault_password'):
            try:
                f = open(os.path.join(self._distro._mountpoint, 'tmp',
                                      'vault_password'), 'w')
                f.writelines(os.environ['VAULT_PWD'])
                f.close()
            except KeyError as e:
                log.error('Environment variable for Ansible vault not set!')

        return True


    def _provision_package(self):
        """ Sets up the command to get Ansible to run """

        result = self._write_local_inventory()
        if not result:
            log.critical('Could not write local inventory file: {0.std_err}'.format(result.result))
            return False

        context = self._config.context
        config = self._config.plugins[self.full_name]
        extra_vars = config.get('extravars', '')
        path = config.get('playbooks_path_dest')
        vault_password = config.get('vault_password', '')

        log.info('Running Ansible playbook %s...', context.package.arg)
        return run_ansible_playbook(context.package.inventory, extra_vars, path, context.package.arg, vault_password)


    def _store_package_metadata(self):
        """ Store metadata about the AMI created """

        self._ansible_cleanup()

        context = self._config.context
        config = self._config.plugins[self.full_name]
        metadata = {}
        metadata['name'] = context.package.arg
        metadata['version'] = config.get('appversion', '')
        metadata['release'] = ''
        metadata['extra_vars'] = config.get('extravars', '')
        context.package.attributes = metadata


    def _ansible_cleanup(self):
        """ Clean up any Ansible files left over (if necessary) """

        config = self._config.plugins[self.full_name]
        keep_playbooks = config.get('keep_playbooks')
        vault_password = config.get ('vault_password')

        if not keep_playbooks:
            playbooks_path_dest = config.get('playbooks_path_dest')
            shutil.rmtree(playbooks_path_dest)

        if vault_password:
            os.remove('/tmp/vault_password')


    def _refresh_package_metadata(self):
        """ Empty until Aminator is reorganized - end of August 2013 """
        return True

    def _deactivate_provisioning_service_block(self):
        """ Empty until Aminator is reorganized - end of August 2013 """
        return True

    def _activate_provisioning_service_block(self):
        """ Empty until Aminator is reorganized - end of August 2013 """
        return True


@command()
def run_ansible_playbook(inventory, extra_vars, playbook_dir, playbook, vault_password):
    path = playbook_dir + '/' + playbook
    command = 'ansible-playbook -c local -i {0} -e \'ami=True {1}\' {2}'.format(inventory, extra_vars, path)
    if vault_password:
        command += ' --vault-password-file /tmp/vault_password'
    return command