import subprocess
import os
import sys
import click
from .container import Container  # noqa -- reexport


class BridgeType(click.ParamType):
    name = '[mac:]bridge[:host_interface:guest_interface]'

    def convert(self, value, param, ctx):
        value = value.split(':')
        if len(value) == 1:
            return {'bridge': value[0]}
        if len(value) == 2:
            return {
                'mac': value[0],
                'bridge': value[1]
            }
        if len(value) == 3:
            return {
                'bridge': value[0],
                'host': value[1],
                'guest': value[2]
            }
        if len(value) == 4:
            return {
                'mac': value[0],
                'bridge': value[1],
                'host': value[2],
                'guest': value[3]
            }
        raise ValueError('Wrong bridge format: {}'.format(value))

BRIDGE = BridgeType()


@click.group()
def cli():
    pass


def get_pid(name):
    data = subprocess.check_output(['/bin/machinectl', 'show', name]) \
                     .decode("utf-8").strip().split("\n")
    data = dict(line.split("=", 1) for line in data)
    return data['Leader']


def systemd_reload():
    subprocess.check_call(["/bin/systemctl", "daemon-reload"])


def container_exists(name):
    return name == os.path.basename(name) \
       and os.path.exists(os.path.join("/var/lib/machines", name, 'fs'))


def require_existing_container(f):
    def inner(*args, **kwargs):
        name = kwargs['name']
        if not container_exists(name):
            print("Container {} does not exist".format(name), file=sys.stderr)
            sys.exit(1)

        f(*args, **kwargs)

    inner.__name__ = getattr(f, '__name__', None) or f.name
    return inner


def is_active(name):
    return subprocess.call(['/bin/systemctl', 'is-active', name],
                           stdout=subprocess.DEVNULL) == 0


def run_hooks(type, *args):
    dirname = os.path.dirname(__file__)
    hooks_dir = os.path.join(dirname, 'hooks', type)
    if not os.path.exists(hooks_dir):
        return

    for path in sorted(os.listdir(hooks_dir)):
        path = os.path.join(hooks_dir, path)
        if not os.path.isfile(path) or not os.access(path, os.X_OK):
            print("NOT running hook {path} "
                  "(`chmod +x {path}`?)".format(path=path), file=sys.stderr)
            continue

        subprocess.call([path] + list(args))
