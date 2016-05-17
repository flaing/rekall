#!/usr/bin/env python
#
#       fileobjscan.py
#       Copyright 2009 Andreas Schuster <a.schuster@yendor.net>
#       Copyright (C) 2009-2011 Volatile Systems
#
#       This program is free software; you can redistribute it and/or modify
#       it under the terms of the GNU General Public License as published by
#       the Free Software Foundation; either version 2 of the License, or
#       (at your option) any later version.
#
#       This program is distributed in the hope that it will be useful,
#       but WITHOUT ANY WARRANTY; without even the implied warranty of
#       MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#       GNU General Public License for more details.
#
#       You should have received a copy of the GNU General Public License
#       along with this program; if not, write to the Free Software
#       Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#       MA 02110-1301, USA.

# pylint: disable=protected-access

"""
@author:       Andreas Schuster
@license:      GNU General Public License 2.0 or later
@contact:      a.schuster@forensikblog.de
@organization: http://computer.forensikblog.de/en/
"""
from rekall import plugin
from rekall.plugins.windows import common


class PoolScanFile(common.PoolScanner):
    """PoolScanner for File objects"""
    def __init__(self, **kwargs):
        super(PoolScanFile, self).__init__(**kwargs)
        self.checks = [
            ('PoolTagCheck', dict(
                tag=self.profile.get_constant("FILE_POOLTAG"))),

            ('CheckPoolSize', dict(
                min_size=self.profile.get_obj_size("_FILE_OBJECT"))),

            ('CheckPoolType', dict(
                paged=True, non_paged=True, free=True)),

            ('CheckPoolIndex', dict(value=0)),
            ]


class FileScan(common.PoolScannerPlugin):
    """ Scan Physical memory for _FILE_OBJECT pool allocations
    """
    __name = "filescan"

    def generate_hits(self):
        """Generate possible hits."""
        scanner = PoolScanFile(profile=self.profile, session=self.session,
                               address_space=self.address_space)

        for pool_obj in scanner.scan():
            for object_obj in pool_obj.IterObject("File", freed=True):
                ## If the string is not reachable we skip it
                file_obj = self.session.profile._FILE_OBJECT(
                    offset=object_obj.obj_end, vm=self.address_space)

                if not file_obj.FileName.v(vm=self.kernel_address_space):
                    continue

                # Real file objects have valid DeviceObject types.
                device_obj = file_obj.DeviceObject.deref(
                    vm=self.session.kernel_address_space)

                if not device_obj.DeviceType.is_valid():
                    continue

                yield (pool_obj, object_obj, file_obj)

    def render(self, renderer):
        """Print the output in a table."""

        renderer.table_header([(' ', 'allocated', '1'),
                               ('Offset', "offset_p", '[addrpad]'),
                               ('#Ptr', "ptr_count", '>6'),
                               ('#Hnd', "hnd_count", '>3'),
                               ('Access', "access", '6'),
                               dict(name='Owner', type="_EPROCESS"),
                               ('Name', "path", '')
                              ])

        for pool_obj, object_obj, file_obj in self.generate_hits():
            # The Process member in the HandleInfo sometimes points at the
            # _EPROCESS owning the handle.
            owner_process = object_obj.HandleInfo.SingleEntry.Process.deref(
                vm=self.kernel_address_space)

            filename = file_obj.file_name_with_drive(
                vm=self.kernel_address_space)

            renderer.table_row(
                'F' if pool_obj.FreePool else "",
                file_obj.obj_offset,
                object_obj.PointerCount,
                object_obj.HandleCount,
                file_obj.AccessString,
                owner_process,
                filename)


class PoolScanDriver(PoolScanFile):
    """ Scanner for _DRIVER_OBJECT """

    def __init__(self, **kwargs):
        super(PoolScanDriver, self).__init__(**kwargs)
        self.checks = [
            ('PoolTagCheck', dict(
                tag=self.profile.get_constant("DRIVER_POOLTAG"))),

            # Must be large enough to hold the driver object.
            ('CheckPoolSize', dict(
                condition=lambda x: x > self.profile.get_obj_size(
                    "_DRIVER_OBJECT"))),

            ('CheckPoolType', dict(
                paged=True, non_paged=True, free=True)),

            ('CheckPoolIndex', dict(value=0)),
            ]

class DriverScan(FileScan):
    "Scan for driver objects _DRIVER_OBJECT "

    __name = "driverscan"

    def generate_hits(self):
        """Generate possible hits."""
        scanner = PoolScanDriver(session=self.session,
                                 profile=self.profile,
                                 address_space=self.address_space)

        for pool_obj in scanner.scan():
            for object_obj in pool_obj.IterObject("Driver", freed=True):
                object_name = object_obj.NameInfo.Name.v(
                    vm=self.kernel_address_space)

                driver_obj = self.profile._DRIVER_OBJECT(
                    object_obj.obj_end, vm=self.address_space)

                extension_obj = self.profile._DRIVER_EXTENSION(
                    driver_obj.obj_end, vm=self.address_space)

                yield (pool_obj, object_obj, driver_obj, extension_obj,
                       object_name)


    def render(self, renderer):
        """Renders the text-based output"""
        renderer.table_header([(' ', 'allocated', '1'),
                               ('Offset(P)', "offset_p", '[addrpad]'),
                               ('#Ptr', "ptr_count", '>4'),
                               ('#Hnd', "hnd_count", '>4'),
                               ('Start', "driver_start", '[addrpad]'),
                               ('Size', "driver_size", '[addr]'),
                               ('Service Key', "driver_servicekey", '20'),
                               ('Name', "driver_name", '12'),
                               ('Driver Name', "path", '')
                              ])

        for _ in self.generate_hits():
            pool_obj, object_obj, driver_obj, extension_obj, object_name = _
            renderer.table_row(
                'F' if pool_obj.FreePool else "",
                driver_obj.obj_offset,
                object_obj.PointerCount,
                object_obj.HandleCount,
                driver_obj.DriverStart,
                driver_obj.DriverSize,
                extension_obj.ServiceKeyName.v(vm=self.kernel_address_space),
                object_name,
                driver_obj.DriverName.v(vm=self.kernel_address_space))


class PoolScanSymlink(PoolScanFile):
    """ Scanner for symbolic link objects """
    def __init__(self, **kwargs):
        super(PoolScanSymlink, self).__init__(**kwargs)
        self.checks = [
            ('PoolTagCheck', dict(
                tag=self.profile.get_constant("SYMLINK_POOLTAG"))),

            ('CheckPoolSize', dict(
                min_size=self.profile.get_obj_size(
                    "_OBJECT_SYMBOLIC_LINK"))),

            ('CheckPoolType', dict(paged=True, non_paged=True, free=True)),
            ]


class SymLinkScan(FileScan):
    "Scan for symbolic link objects "

    __name = "symlinkscan"

    def generate_hits(self):
        """Generate possible hits."""
        scanner = PoolScanSymlink(profile=self.profile, session=self.session,
                                  address_space=self.address_space)
        for pool_obj in scanner.scan():
            for object_obj in pool_obj.IterObject("SymbolicLink", freed=True):
                object_name = object_obj.NameInfo.Name.v(
                    vm=self.kernel_address_space)

                link_obj = self.profile._OBJECT_SYMBOLIC_LINK(
                    object_obj.obj_end, vm=self.address_space)

                yield pool_obj, object_obj, link_obj, object_name

    def render(self, renderer):
        """ Renders text-based output """
        renderer.table_header([(' ', 'allocated', '1'),
                               ('Offset(P)', "offset_p", '[addrpad]'),
                               ('#Ptr', "ptr_count", '>6'),
                               ('#Hnd', "hnd_count", '>6'),
                               ('Creation time', "symlink_creation_time", '24'),
                               ('From', "symlink_from", ''),
                               ('To', "symlink_to", '60'),
                              ])


        for pool_obj, o, link, name in self.generate_hits():
            renderer.table_row(
                'F' if pool_obj.FreePool else "",
                link.obj_offset,
                o.PointerCount,
                o.HandleCount,
                link.CreationTime or '',
                name,
                link.LinkTarget.v(vm=self.kernel_address_space))


class PoolScanMutant(PoolScanDriver):
    """ Scanner for Mutants _KMUTANT """
    def __init__(self, **kwargs):
        super(PoolScanMutant, self).__init__(**kwargs)
        self.checks = [
            ('PoolTagCheck', dict(tag=self.profile.get_constant(
                "MUTANT_POOLTAG"))),

            ('CheckPoolSize', dict(
                min_size=self.profile.get_obj_size("_KMUTANT"))),

            ('CheckPoolType', dict(
                paged=True, non_paged=True, free=True)),

            ('CheckPoolIndex', dict(value=0)),
            ]


class MutantScan(plugin.VerbosityMixIn, FileScan):
    "Scan for mutant objects _KMUTANT "

    __name = "mutantscan"

    def generate_hits(self):
        scanner = PoolScanMutant(profile=self.profile, session=self.session,
                                 address_space=self.address_space)

        for pool_obj in scanner.scan():
            for object_obj in pool_obj.IterObject("Mutant", freed=True):
                object_name = object_obj.NameInfo.Name.v(
                    vm=self.kernel_address_space)

                # By default we suppress non-named mutants because they are not
                # very interesting.
                if self.plugin_args.verbosity < 5 and not object_name:
                    continue

                mutant = self.profile._KMUTANT(
                    object_obj.obj_end, vm=self.address_space)

                yield (pool_obj, object_obj, mutant, object_name)

    def render(self, renderer):
        """Renders the output"""

        renderer.table_header([(' ', 'allocated', '1'),
                               ('Offset(P)', "offset_p", '[addrpad]'),
                               ('#Ptr', "ptr_count", '>6'),
                               ('#Hnd', "hnd_count", '>4'),
                               ('Signal', "mutant_signal", '6'),
                               ('Thread', "mutant_thread", '[addrpad]'),
                               ('CID', "cid", '>9'),
                               ('Name', "mutant_name", '')
                              ])

        for pool_obj, object_obj, mutant, _ in self.generate_hits():
            if mutant.OwnerThread > 0x80000000:
                thread = self.profile._ETHREAD(
                    offset=mutant.OwnerThread, vm=self.kernel_address_space)

                CID = "{0}:{1}".format(thread.Cid.UniqueProcess,
                                       thread.Cid.UniqueThread)
            else:
                CID = ""

            renderer.table_row(
                'F' if pool_obj.FreePool else "",
                mutant.obj_offset,
                object_obj.PointerCount,
                object_obj.HandleCount,
                mutant.Header.SignalState,
                mutant.OwnerThread,
                CID,
                object_obj.NameInfo.Name.v(vm=self.kernel_address_space))


class PoolScanProcess(common.PoolScanner):
    """PoolScanner for File objects"""

    # Kernel addresses are above this value.
    kernel = 0x80000000

    def __init__(self, **kwargs):
        super(PoolScanProcess, self).__init__(**kwargs)
        self.kernel = self.profile.get_constant_object(
            "MmSystemRangeStart", "Pointer").v() or 0x80000000

        self.checks = [
            # Must have the right pool tag.
            ('PoolTagCheck', dict(
                tag=self.profile.get_constant("EPROCESS_POOLTAG"))),

            # Must be large enough for an _EPROCESS.
            ('CheckPoolSize', dict(min_size=self.profile.get_obj_size(
                "_EPROCESS"))),

            # It seems that on old XP versions _EPROCESS was allocated from
            # paged pool but it's rare to see that.
            ('CheckPoolType', dict(
                paged=True, non_paged=True, free=True)),

            ('CheckPoolIndex', dict(value=0)),
        ]

        # The DTB is page aligned on AMD64 and I386 but aligned to 0x20
        # on PAE kernels.
        if self.session.kernel_address_space.metadata("pae"):
            self.dtb_alignment = 0x20
        else:
            self.dtb_alignment = 0x1000

    def scan(self, **kwargs):
        for pool_obj in super(PoolScanProcess, self).scan(**kwargs):
            # Also fetch freed objects.
            for object_header in pool_obj.IterObject("Process", freed=True):
                eprocess = object_header.Body.cast("_EPROCESS")

                if eprocess.Pcb.DirectoryTableBase == 0:
                    continue

                if eprocess.Pcb.DirectoryTableBase % self.dtb_alignment != 0:
                    continue

                # Pointers must point to the kernel part of the address space.
                list_head = eprocess.ActiveProcessLinks
                if (list_head.Flink < self.kernel or
                        list_head.Blink < self.kernel):
                    continue

                yield pool_obj, eprocess


class PSScan(common.WinScanner):
    """Scan Physical memory for _EPROCESS pool allocations.

    Status flags:
      E: A known _EPROCESS address from pslist.
      P: A known pid from pslist.
    """

    name = "psscan"

    table_header = plugin.PluginHeader(
        dict(name=' ', cname='allocated', width=1),
        dict(name='_EPROCESS (P)', cname="offset_p", type="_EPROCESS"),
        dict(name='Offset(V)', cname="offset_v", style="address"),
        dict(name='PPID', cname="ppid", width=6, align="r"),
        dict(name='PDB', cname="pdb", style="address"),
        dict(name='Stat', cname='stat', width=4),
        dict(name='Time created', cname="process_create_time", width=24),
        dict(name='Time exited', cname="process_exit_time", width=24),
    )

    # Only bother to scan non paged pool by default.
    scanner_defaults = dict(
        scan_kernel_nonpaged_pool=True
    )

    def collect(self):
        """Render results in a table."""
        # Try to do a regular process listing so we can compare if the process
        # is known.
        pslist = self.session.plugins.pslist()

        # These are virtual addresses.
        known_eprocess = set()
        known_pids = set()
        for task in pslist.list_eprocess():
            known_eprocess.add(task)
            known_pids.add(task.UniqueProcessId)

        # Scan each requested run in turn.
        for run in self.generate_memory_ranges():
            # Just grab the AS and scan it using our scanner
            scanner = PoolScanProcess(session=self.session,
                                      profile=self.profile,
                                      address_space=run.address_space)

            for pool_obj, eprocess in scanner.scan(
                    offset=run.start, maxlen=run.length):
                if run.data["type"] == "PhysicalAS":
                    # Switch address space from physical to virtual.
                    virtual_eprocess = (
                        pslist.virtual_process_from_physical_offset(eprocess))
                else:
                    virtual_eprocess = eprocess

                known = ""
                if virtual_eprocess in known_eprocess:
                    known += "E"

                if eprocess.UniqueProcessId in known_pids:
                    known += "P"

                yield('F' if pool_obj.FreePool else "",
                      eprocess,
                      virtual_eprocess.obj_offset,
                      eprocess.InheritedFromUniqueProcessId,
                      eprocess.Pcb.DirectoryTableBase,
                      known,
                      eprocess.CreateTime or '',
                      eprocess.ExitTime or '')