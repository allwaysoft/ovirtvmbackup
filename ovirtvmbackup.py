#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
# Copyright (c) 2017 Red Hat, Inc.
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
from __future__ import print_function

import logging
import os
import ovirtsdk4 as sdk
import ovirtsdk4.types as types
import ssl
import sys
import time
import uuid

from six.moves.http_client import HTTPSConnection
from six.moves.urllib.parse import urlparse

import argparse
import getpass
import subprocess

logging.basicConfig(level=logging.DEBUG, filename='ovirtvmbackup.log')

def parse_args():
    parser = argparse.ArgumentParser(description="ovirtvmbackup")

    parser.add_argument(
        "vmname",
        help="name of virtual machine")

    parser.add_argument(
        "--backup-dir",
        required=True,
        help="dir to store backup")

    parser.add_argument(
        "--engine-url",
        required=True,
        help="transfer URL (e.g. https://engine_fqdn:port)")

    parser.add_argument(
        "--username",
        required=True,
        help="username of engine API")

    parser.add_argument(
        "--password-file",
        help="file containing password of the specified by user (if file is "
             "not specified, read from standard input)")

    parser.add_argument(
        "-c", "--cafile",
        help="path to oVirt engine certificate for verifying server.")

    return parser.parse_args()


# This example will connect to the server, loop over the disk snapshots
# of a specified disk and download their data into files.
# Note: in order to get the disk's snapshots, we are retrieving *all*
# the snapshots of the storage domain, and filter accordingly.
# Should find a more efficient means in the future.

def get_transfer_service(disk_snapshot_id):
    # Get a reference to the service that manages the image transfer:
    transfers_service = system_service.image_transfers_service()

    # Add a new image transfer:
    transfer = transfers_service.add(
        types.ImageTransfer(
            snapshot=types.DiskSnapshot(id=disk_snapshot_id),
            direction=types.ImageTransferDirection.DOWNLOAD,
        )
    )

    # Get reference to the created transfer service:
    transfer_service = transfers_service.image_transfer_service(transfer.id)

    while transfer.phase == types.ImageTransferPhase.INITIALIZING:
        time.sleep(1)
        transfer = transfer_service.get()

    return transfer_service

def get_proxy_connection(proxy_url):
    # At this stage, the SDK granted the permission to start transferring the disk, and the
    # user should choose its preferred tool for doing it - regardless of the SDK.
    # In this example, we will use Python's httplib.HTTPSConnection for transferring the data.
    context = ssl.create_default_context()

    # Note that ovirt-imageio-proxy by default checks the certificates, so if you don't have
    # your CA certificate of the engine in the system, you need to pass it to HTTPSConnection.
    context.load_verify_locations(cafile='ca.pem')

    return HTTPSConnection(
        proxy_url.hostname,
        proxy_url.port,
        context=context,
    )

def download_disk_snapshot(disk_snapshot,download_dir):
    print("Downloading disk snapshot %s" % disk_snapshot.id)

    transfer_service = None
    try:
        transfer_service = get_transfer_service(disk_snapshot.id)
        transfer = transfer_service.get()
        proxy_url = urlparse(transfer.proxy_url)
        proxy_connection = get_proxy_connection(proxy_url)
        path = download_dir + '/' + disk_snapshot.alias + '-' + disk_snapshot.id

        with open(path, "wb") as mydisk:
            # Set needed headers for downloading:
            transfer_headers = {
                'Authorization': transfer.signed_ticket,
            }

            # Perform the request.
            proxy_connection.request(
                'GET',
                proxy_url.path,
                headers=transfer_headers,
            )
            # Get response
            r = proxy_connection.getresponse()

            # Check the response status:
            if r.status >= 300:
                print("Error: %s" % r.read())

            bytes_to_read = int(r.getheader('Content-Length'))
            chunk_size = 64 * 1024 * 1024

            print("Disk snapshot size: %s bytes" % str(bytes_to_read))

            while bytes_to_read > 0:
                # Calculate next chunk to read
                to_read = min(bytes_to_read, chunk_size)

                # Read next chunk
                chunk = r.read(to_read)

                if chunk == "":
                    raise RuntimeError("Socket disconnected")

                # Write the content to file:
                mydisk.write(chunk)

                # Update bytes_to_read
                bytes_to_read -= len(chunk)

                completed = 1 - (bytes_to_read / float(r.getheader('Content-Length')))

                print("Completed", "{:.0%}".format(completed))
    finally:
        # Finalize the session.
        if transfer_service is not None:
            transfer_service.finalize()

            # Waiting for finalize to complete
            try:
                while transfer_service.get():
                    time.sleep(1)
            except sdk.NotFoundError:
                pass

if __name__ == "__main__":
    args = parse_args()
    # The name of the application, to be used as the 'origin' of events
    # sent to the audit log:
    APPLICATION_NAME = 'ovirtvmbackup'
    
    # The name of the virtual machine that contains the data that we
    # want to back-up:
    DATA_VM_NAME = args.vmname
    VM_BACKUP_DIR = args.backup_dir

    # Create the connection to the server:
    print("Connecting...")

    if args.password_file:
        with open(args.password_file) as f:
            password = f.read().rstrip('\n') # ovirt doesn't support empty lines in password
    else:
        password = getpass.getpass()

    connection = sdk.Connection(
        url=args.engine_url + '/ovirt-engine/api',
        username=args.username,
        password=password,
        ca_file=args.cafile,
        debug=True,
        log=logging.getLogger(),
    )

    # Get a reference to the root service:
    system_service = connection.system_service()
    # Get the reference to the service that we will use to send events to
    # the audit log:
    events_service = system_service.events_service()
    
    # In order to send events we need to also send unique integer ids. These
    # should usually come from an external database, but in this example we
    # will just generate them from the current time in seconds since Jan 1st
    # 1970.
    event_id = int(time.time())

    # Get the reference to the service that manages the virtual machines:
    vms_service = system_service.vms_service()
    # Find the virtual machine that we want to back up. Note that we need to
    # use the 'all_content' parameter to retrieve the retrieve the OVF, as
    # it isn't retrieved by default:
    data_vm = vms_service.list(
        search='name=%s' % DATA_VM_NAME,
        all_content=True,
    )[0]
    logging.info(
        'Found data virtual machine \'%s\', the id is \'%s\'.',
        data_vm.name, data_vm.id,
    )
    # Find the services that manage the data and agent virtual machines:
    data_vm_service = vms_service.vm_service(data_vm.id)
    # Create an unique description for the snapshot, so that it is easier
    # for the administrator to identify this snapshot as a temporary one
    # created just for backup purposes:
    snap_description = '%s-backup-%s' % (data_vm.name, uuid.uuid4())
    # Send an external event to indicate to the administrator that the
    # backup of the virtual machine is starting. Note that the description
    # of the event contains the name of the virtual machine and the name of
    # the temporary snapshot, this way, if something fails, the administrator
    # will know what snapshot was used and remove it manually.
    events_service.add(
        event=types.Event(
            vm=types.Vm(
              id=data_vm.id,
            ),
            origin=APPLICATION_NAME,
            severity=types.LogSeverity.NORMAL,
            custom_id=event_id,
            description=(
                'Backup of virtual machine \'%s\' using snapshot \'%s\' is '
                'starting.' % (data_vm.name, snap_description)
            ),
        ),
    )
    event_id += 1
    bckfiledir = VM_BACKUP_DIR + "/" + DATA_VM_NAME + "/" + str(time.strftime("%Y%m%d%H%M%S"))
    mkdir = "mkdir -p " + bckfiledir
    subprocess.call(mkdir, shell=True)
    # Save the OVF to a file, so that we can use to restore the virtual
    # machine later. The name of the file is the name of the virtual
    # machine, followed by a dash and the identifier of the virtual machine,
    # to make it unique:
    ovf_data = data_vm.initialization.configuration.data
    ovf_file = '%s/%s-%s.ovf' % (bckfiledir,data_vm.name, data_vm.id)
    with open(ovf_file, 'w') as ovs_fd:
        ovs_fd.write(ovf_data.encode('utf-8'))
    logging.info('Wrote OVF to file \'%s\'.', os.path.abspath(ovf_file))
    
    
    # Send the request to create the snapshot. Note that this will return
    # before the snapshot is completely created, so we will later need to
    # wait till the snapshot is completely created.
    # The snapshot will not include memory. Change to True the parameter
    # persist_memorystate to get it (in that case the VM will be paused for a while).
    snaps_service = data_vm_service.snapshots_service()
    # delete all exist snapshot to do full backup.
    sl =snaps_service.list()
    
    for sn in sl:
        try:
            ss = snaps_service.snapshot_service(sn.id)
            ss.remove() 
            # Waiting for snapshot remove to complete
            try:
                while ss.get():
                    time.sleep(1)
            except sdk.NotFoundError:
                pass
        except sdk.Error:
            pass

    # end delete all exist snapshot to do full backup.
    snap = snaps_service.add(
        snapshot=types.Snapshot(
            description=snap_description,
            persist_memorystate=False,
        ),
    )
    logging.info(
        'Sent request to create snapshot \'%s\', the id is \'%s\'.',
        snap.description, snap.id,
    )
    # Poll and wait till the status of the snapshot is 'ok', which means
    # that it is completely created:
    snap_service = snaps_service.snapshot_service(snap.id)
    while snap.snapshot_status != types.SnapshotStatus.OK:
        logging.info(
            'Waiting till the snapshot is created, the satus is now \'%s\'.',
            snap.snapshot_status,
        )
        time.sleep(1)
        snap = snap_service.get()
    logging.info('The snapshot is now complete.')
    
    # Retrieve the descriptions of the disks of the snapshot:
    snap_disks_service = snap_service.disks_service()
    snap_disks = snap_disks_service.list()


    # Get a reference to the storage domains service:
    storage_domains_service = system_service.storage_domains_service()

    # Look up fot the storage domain by name:
    storage_domain = storage_domains_service.list()
    for d in storage_domain:
        # Get a reference to the storage domain service in which the disk snapshots reside:
        storage_domain_service = storage_domains_service.storage_domain_service(d.id)

        # Get a reference to the disk snapshots service:
        # Note: we are retrieving here *all* the snapshots of the storage domain.
        # Should find a more efficient means in the future.
        disk_snapshot_service = storage_domain_service.disk_snapshots_service()

        # Get a list of disk snapshots by a disk ID
        all_disk_snapshots = disk_snapshot_service.list()
    
        #for s in all_disk_snapshots:
            #print (s.snapshot.id)
            #print (':')
            #print (snap.id)

        # Filter disk snapshots list by snap id
        disk_snapshots = [s for s in all_disk_snapshots if s.snapshot.id == snap.id]

        # Download disk snapshots
        for disk_snapshot in disk_snapshots:
            #print ('begin download_disk_snapshot:')
            #print (disk_snapshot.id)
            download_disk_snapshot(disk_snapshot,bckfiledir)
            #print (':end download_disk_snapshot')
    # Remove the snapshot:
    snap_service.remove()
    logging.info('Removed the snapshot \'%s\'.', snap.description)
    
    # Send an external event to indicate to the administrator that the
    # backup of the virtual machine is completed:
    events_service.add(
        event=types.Event(
            vm=types.Vm(
              id=data_vm.id,
            ),
            origin=APPLICATION_NAME,
            severity=types.LogSeverity.NORMAL,
            custom_id=event_id,
            description=(
                'Backup of virtual machine \'%s\' using snapshot \'%s\' is '
                'completed.' % (data_vm.name, snap_description)
            ),
        ),
    )
    event_id += 1

    # Close the connection to the server:
    connection.close()
