import click
import os
import subprocess
from configparser import SafeConfigParser
from toposort import toposort_flatten


@click.option("--template", "-t", default="debian-jessie")
def create(ctx, container, template, **kwargs):
    try:
        os.mkdir("/var/lib/machines/{}".format(container.name))
        os.mkdir("/var/lib/machines/{}/fs".format(container.name))
        os.mkdir("/var/lib/machines/{}/overlay.fs".format(container.name))
        os.mkdir("/var/lib/machines/{}/workdir".format(container.name))
    except FileExistsError:
        # The overlay might be left over from a previous container
        pass

    container.dependencies = template.split(',')

def update_sd_units(container, service, *args):
    name = container.name
    mount_name = subprocess.check_output(['systemd-escape', '-p', name]).strip().decode('utf-8')

    # Prepare the overlayfs mount unit
    mount = SafeConfigParser()
    mount.optionxform = str
    mount['Unit'] = {
        'Description': 'OverlayFS for {}'.format(name),
        'PartOf': '{}.service'.format(mount_name)
    }
    mount['Mount'] = container.mounts()[0]
    mount_path = subprocess.check_output(['systemd-escape', '--path', mount['Mount']['Where']]).strip().decode('utf-8')
    dst_filename = "/etc/systemd/system/{}.mount".format(mount_path)
    with open(dst_filename, 'w') as f:
        mount.write(f)

    unit = service['Unit']
    if 'Requires' not in unit:
        unit['Requires'] = ''
    if 'After' not in unit:
        unit['After'] = ''

    unit['Requires'] += 'var-lib-machines-{}-fs.mount '.format(mount_name)
    unit['After'] += 'var-lib-machines-{}-fs.mount '.format(mount_name)

class MountContainer:
    @property
    def dependencies(self):
        return list(dependency['imageName'] for dependency in self.manifest['dependencies'])

    @dependencies.setter
    def dependencies(self, dependencies):
        manifest = self.manifest
        manifest['dependencies'] = list({"imageName": name} for name in dependencies)
        self.manifest = manifest

    def mounts(self):
        options = 'lowerdir={initfs}:{dependencies},upperdir={upperdir},workdir={workdir}'
        options = options.format(
            initfs=os.path.join(self.path, 'init.fs'),
            dependencies=self.mount_lowerdirs(),
            upperdir=os.path.join(self.path, 'overlay.fs'),
            workdir=os.path.join(self.path, 'workdir')
        )
        return [{
            'What': 'overlayfs',
            'Where': os.path.join(self.path, 'fs'),
            'Options': options,
            'Type': 'overlay'
        }]

    def init_mounts(self):
        options = 'lowerdir={dependencies},upperdir={initfs},workdir={workdir}'
        options = options.format(
            initfs=os.path.join(self.path, 'init.fs'),
            dependencies=self.mount_lowerdirs(),
            workdir=os.path.join(self.path, 'workdir')
        )
        return [{
            'What': 'overlayfs',
            'Where': os.path.join(self.path, 'fs'),
            'Options': options,
            'Type': 'overlay'
        }]
        

    def mount_lowerdirs(self):
        # First, build a dependency graph in order to avoid duplicate entries
        dependencies = {}
        pending_deps = set(self.dependencies)
        while len(pending_deps) > 0:
            name = pending_deps.pop()
            if name not in dependencies:
                dependencies[name] = set(self.__class__(name).dependencies)
                pending_deps |= dependencies[name]

        # Then sort it topologically. The list is reversed, because overlayfs
        # will check the mounts in order they are given, so the base fs has to
        # be the last one.
        dependencies = reversed(list(toposort_flatten(dependencies)))
        return ':'.join(os.path.join(self.metadata_dir, dep, 'overlay.fs') for dep in dependencies)

    def default_manifest(self):
        super_dict = {}
        if hasattr(super(), 'default_manifest'):
            super_dict = super().default_manifest()

        super_dict.update({
            "dependencies": [
                {"imageName": "debian-jessie"}
            ],
        })

        return super_dict