"""
Usage:
    updater.py check <repo> <path>
    updater.py update <repo> <path>
"""
import os
import sys
import tarfile
from pathlib import Path

import requests
from distutils.version import StrictVersion
from docopt import docopt
from shutil import rmtree

ASSET_ID_FILE = '.asset_id'
CURRENT_PATH = 'current'
HISTORY_COUNT = 5
RELEASES_PATH = 'releases'
RELEASE_PREFIX = 'website-v'

RELEASE_URL = 'https://api.github.com/repos/{repo}/releases'


def _release_filter(release):
    return not release['draft'] and not release['prerelease'] and release['assets']


def get_latest_release_asset(repo):
    with requests.get(RELEASE_URL.format(repo=repo)) as response:
        response.raise_for_status()
        data = response.json()

    release = next(filter(_release_filter, data), None)

    if release is None:
        raise ValueError("Unable to find matching release")

    return release['assets'][0]


def check_for_update(args):
    repo = args['<repo>']
    deploy_path = Path(args['<path>']).resolve()
    if not deploy_path.is_dir():
        sys.exit("Website not deployed")

    asset_id_file = deploy_path / CURRENT_PATH / ASSET_ID_FILE
    if not asset_id_file.exists():
        sys.exit("No assets currently deployed")

    with open(str(asset_id_file)) as f:
        current_id = f.read().strip().splitlines()[0]

    if not current_id:
        sys.exit("No assets currently deployed")

    asset = get_latest_release_asset(repo)
    if str(asset['id']) != current_id:
        sys.exit("Assets out of date")

    sys.exit(0)


def do_update(args):
    deploy_path = Path(args['<path>']).resolve()
    releases_dir = deploy_path / RELEASES_PATH
    current_link = deploy_path / CURRENT_PATH

    asset = get_latest_release_asset(args['<repo>'])

    # Requires that the asset be '<name>.tar.gz'
    release_name = asset['name'].rsplit('.', 2)[0]

    release_dir = releases_dir / release_name
    if not release_dir.exists():
        release_dir.mkdir(parents=True)

    with requests.get(
            asset['url'], stream=True,
            headers={
                'Accept': 'application/octet-stream',
            }
    ) as response:
        with tarfile.open(fileobj=response.raw, mode='r|*') as tarball:
            tarball.extractall(path=str(release_dir))

    # Record the ID of this asset for later update checks
    with open(str(release_dir / ASSET_ID_FILE), 'w') as f:
        print(asset['id'], file=f)

    if current_link.is_symlink():
        current_link.unlink()

    current_link.symlink_to(release_dir, target_is_directory=True)
    print('Deployed', release_name)

    do_cleanup(releases_dir, release_name)


def do_cleanup(releases_dir, latest_release):
    directories = os.listdir(releases_dir)
    removed = 0

    if len(directories) <= HISTORY_COUNT:
        print('Did not run clean up (too few historic releases)')
        return

    # Trim "website-v" prefix for sorting with distutils.version
    versions = [directory.replace(RELEASE_PREFIX, '') for directory in directories]
    versions.sort(key=StrictVersion, reverse=True)

    for version in versions[HISTORY_COUNT:]:
        if RELEASE_PREFIX + version != latest_release:
            # Replace the prefix for purging
            release_name = RELEASE_PREFIX + version
            rmtree(releases_dir / release_name)
            removed += 1
        else:
            print('Cannot remove most recent release!')

    if removed > 0:
        print(f'Cleaned up {removed} historic releases')
    else:
        print('No clean up required')


def main():
    args = docopt(__doc__)

    if args['check']:
        check_for_update(args)
    elif args['update']:
        do_update(args)
    else:
        raise ValueError("Invalid arguments from docopt")


if __name__ == '__main__':
    main()
