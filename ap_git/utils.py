import logging
import subprocess
import os.path

logger = logging.getLogger(__name__)


def is_git_repo(path: str) -> bool:
    if path is None:
        raise ValueError("path is required, cannot be None")

    if not os.path.exists(path=path):
        raise FileNotFoundError(f"The directory '{path}' does not exist.")

    cmd = ['git', 'rev-parse', '--is-inside-work-tree']
    logger.debug(''.join(cmd))
    ret = subprocess.run(cmd, cwd=path, shell=False)
    return ret.returncode == 0


def is_valid_hex_string(test_str: str) -> bool:
    if test_str is None:
        raise ValueError("test_str cannot be None")

    return all(c in 'abcdef' for c in test_str)
