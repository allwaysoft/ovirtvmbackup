#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
# Copyright (c) 2016 Red Hat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import logging

import ovirtsdk4 as sdk
import ovirtsdk4.types as types

logging.basicConfig(level=logging.DEBUG, filename='example.log')

# This example will connect to the server and create a new virtual machine:

# Create the connection to the server:
connection = sdk.Connection(
    url='https://engine.localdomain/ovirt-engine/api',
    username='admin@internal',
    password='password',
    ca_file='ca.crt',
    debug=True,
    log=logging.getLogger(),
)

# Get the reference to the "vms" service:
vms_service = connection.system_service().vms_service()

# Use the "add" method to create a new virtual machine:

ovf_file_path = '/data/ovirtbackup/winxp-e55cebcc-f354-4b66-b858-a11e1c647f1a.ovf'
ovf_data = open(ovf_file_path, 'r').read()
vm = vms_service.add(
    types.Vm(
        cluster=types.Cluster(
            name='Default',
        ),
        initialization = types.Initialization(
            configuration = types.Configuration(
                type = types.ConfigurationType.OVF,
                data = ovf_data
            )
        ),
    ),
)





# Close the connection to the server:
connection.close()
