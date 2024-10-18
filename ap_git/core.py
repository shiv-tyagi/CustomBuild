import logging
import subprocess
from . import utils
from . import exceptions as ex

logger = logging.getLogger(__name__)


class GitRepo:
    def __init__(self, local_path: str) -> None:
        self.__set_local_path(local_path=local_path)

    def __set_local_path(self, local_path: str) -> None:
        if not utils.is_git_repo(local_path):
            raise ex.NonGitDirectoryError(directory=local_path)

        self.__local_path = local_path

    def get_local_path(self) -> str:
        return self.__local_path

    def __checkout(self, commit_ref: str, force: bool = False) -> None:
        if commit_ref is None:
            raise ValueError("commit_ref is required, cannot be None.")

        cmd = ['git', 'checkout', commit_ref]

        if force:
            cmd.append('-f')

        logger.debug(' '.join(cmd))
        subprocess.run(cmd, cwd=self.__local_path, shell=False, check=True)

    def __reset(self, commit_ref: str, hard: bool = False) -> None:
        if commit_ref is None:
            raise ValueError("commit_ref is required, cannot be None.")

        cmd = ['git', 'reset', commit_ref]

        if hard:
            cmd.append('--hard')

        logger.debug(''.join(cmd))
        subprocess.run(cmd, cwd=self.__local_path, shell=False, check=True)

    def __force_recursive_clean(self) -> None:
        cmd = ['git', 'clean', '-xdff']
        logger.debug(''.join(cmd))
        subprocess.run(cmd, cwd=self.__local_path, shell=False, check=True)

    def __remote_list(self) -> list[str]:
        cmd = ['git', 'remote']
        logger.debug(' '.join(cmd))
        ret = subprocess.run(
            cmd, cwd=self.__local_path, shell=False, capture_output=True,
            encoding='utf-8', check=True
        )
        return ret.stdout.split('\n')[:-1]

    def __is_commit_present_locally(self, commit_ref: str) -> bool:
        if commit_ref is None:
            raise ValueError("commit_ref is required, cannot be None.")

        cmd = ['git', 'rev-parse', commit_ref]
        logger.debug(''.join(cmd))
        ret = subprocess.run(cmd, cwd=self.__local_path, shell=False)
        return ret.returncode == 0

    def __remote_set_url(self, remote: str, url: str) -> None:
        if remote is None:
            raise ValueError("remote is required, cannot be None.")

        if url is None:
            raise ValueError("url is required, cannot be None.")

        cmd = ['git', 'remote', 'set-url', remote, url]
        logger.debug(''.join(cmd))
        subprocess.run(cmd, cwd=self.__local_path, check=True)

    def fetch_remote(self, remote: str, force: bool = False,
                     tags: bool = False, recurse_submodules: bool = False,
                     refetch: bool = False) -> None:
        cmd = ['git', 'fetch']

        if remote:
            cmd.append(remote)
        else:
            logger.info("remote is None, fetching all remotes")
            cmd.append('--all')

        if force:
            cmd.append('--force')

        if tags:
            cmd.append('--tags')

        if refetch:
            cmd.append('--refetch')

        if recurse_submodules:
            cmd.append('--recurse-submodules=yes')
        else:
            cmd.append('--recursesubmodules=no')

        logger.debug(''.join(cmd))
        subprocess.run(cmd, cwd=self.__local_path, shell=False)

    def __branch_create(self, branch_name: str,
                        start_point: str = None) -> None:
        if branch_name is None:
            raise ValueError("branch_name is required, cannot be None.")

        cmd = ['git', 'branch', branch_name]

        if start_point:
            if not self.__is_commit_present_locally(commit_ref=start_point):
                raise ex.CommitNotFoundError(commit_ref=start_point)

            cmd.append(start_point)

        logger.debug(''.join(cmd))
        subprocess.run(cmd, cwd=self.__local_path, shell=False, check=True)

    def __branch_delete(self, branch_name: str, force: bool = False) -> None:
        if branch_name is None:
            raise ValueError("branch_name is required, cannot be None.")

        if not self.__is_commit_present_locally(commit_ref=branch_name):
            raise ex.CommitNotFoundError(commit_ref=branch_name)

        cmd = ['git', 'branch', '-d', branch_name]

        if force:
            cmd.append('--force')

        logger.debug(''.join(cmd))
        subprocess.run(cmd, cwd=self.__local_path, shell=False, check=True)

    def __commit_id_for_remote_ref(self, remote: str,
                                   commit_ref: str) -> str | None:
        if remote is None:
            raise ValueError("remote is required, cannot be None.")

        if remote not in self.__remote_list():
            raise ex.RemoteNotFoundError(remote=remote)

        if commit_ref is None:
            raise ValueError("commit_ref is required, cannot be None.")

        if utils.is_valid_hex_string(test_str=commit_ref):
            # skip conversion if commit_ref is already hex string
            return commit_ref

        # allow branches and tags only for now
        allowed_ref_types = ['tags', 'heads']

        split_ref = commit_ref.split('/', 2)

        if len(split_ref) != 3 or split_ref[0] != 'ref':
            raise ValueError(f"commit_ref '{commit_ref}' format is invalid.")

        _, ref_type, ref_name = split_ref

        if ref_type not in allowed_ref_types:
            raise ValueError(
                f"ref_type '{ref_type}' is not supported,"
                "allowed types are '{allowed_ref_types}'."
            )

        cmd = ['git', 'ls-remote', remote]
        ret = subprocess.run(
            cmd, cwd=self.__local_path, encoding='utf-8', capture_output=True,
            shell=False, check=True
        )

        for line in ret.stdout.split('\n')[:-1]:
            (commit_id, res_ref) = line.split('\t')
            if res_ref == ref_name:
                return commit_id

        return None

    def __ensure_commit_fetched(self, remote: str, commit_id: str) -> None:
        if remote is None:
            raise ValueError("remote is required, cannot be None.")

        if remote not in self.__remote_list():
            raise ex.RemoteNotFoundError(remote=remote)

        if commit_id is None:
            raise ValueError("commit_id is required, cannot be None.")

        if not utils.is_valid_hex_string(test_str=commit_id):
            raise ValueError(
                f"commit_id should be a hex string, got '{commit_id}'."
            )

        if not self.__is_commit_present_locally(commit_ref=commit_id):
            # fetch and retry
            self.fetch_remote(remote=remote, force=True, tags=True)

        if not self.__is_commit_present_locally(commit_ref=commit_id):
            # refetch full tree and retry
            self.fetch_remote(
                remote=remote, force=True, tags=True,
                refetch=True
            )

        if not self.__is_commit_present_locally(commit_ref=commit_id):
            raise ex.CommitNotFoundError(commit_ref=commit_id)

    def checkout_remote_commit_ref(self, remote: str,
                                   commit_ref: str,
                                   force: bool = False,
                                   hard_reset: bool = False,
                                   clean_working_tree: bool = False) -> None:
        if remote is None:
            logger.error("remote cannot be None for checkout to remote commit")
            raise ValueError("remote is required, cannot be None.")

        if remote not in self.__remote_list():
            raise ex.RemoteNotFoundError(remote=remote)

        if commit_ref is None:
            raise ValueError("commit_ref is required, cannot be None.")

        commit_id = self.__commit_id_for_remote_ref(
            remote=remote, commit_ref=commit_ref
        )
        self.__ensure_commit_fetched(remote=remote, commit_id=commit_id)
        self.__checkout(commit_ref=commit_id, force=force)

        if hard_reset:
            self.__reset(commit_ref=commit_id, hard=True)

        if clean_working_tree:
            self.__force_recursive_clean()

    def submodule_update(self, init: bool = False, recursive: bool = False,
                         force: bool = False) -> None:
        cmd = ['git', 'submodule', 'update']

        if init:
            cmd.append('--init')

        if recursive:
            cmd.append('--recursive')

        if force:
            cmd.append('--force')

        logger.debug(''.join(cmd))
        subprocess.run(cmd, cwd=self.__local_path, shell=False, check=True)

    def remote_add(self, remote: str, url: str,
                   overwrite_url: bool = False) -> None:
        if remote is None:
            raise ValueError("remote is required, cannot be None.")

        if url is None:
            raise ValueError("url is required, cannot be None.")

        if remote in self.__remote_list():
            if overwrite_url:
                self.__remote_set_url(remote=remote, url=url)
            else:
                raise ex.DuplicateRemoteError(remote)

        cmd = ['git', 'remote', 'add', remote, url]
        logger.debug(''.join(cmd))
        subprocess.run(cmd, cwd=self.__local_path, shell=False, check=True)

    @staticmethod
    def __clone_from_local(source: str, dest: str, branch: str = None,
                           single_branch: bool = False) -> None:
        if not utils.is_git_repo(source):
            raise ex.NonGitDirectoryError(directory=source)

        cmd = ['git', 'clone', source,  dest]

        if branch:
            cmd.append('--branch='+branch)

        if single_branch:
            cmd.append('--single-branch')

        logger.debug(''.join(cmd))
        subprocess.run(cmd, shell=False, check=True)

    @staticmethod
    def shallow_clone_at_commit_from_local(source: str, remote: str,
                                           commit_ref: str, dest: str) -> None:
        if remote is None:
            raise ValueError("remote is required, cannot be None.")

        if commit_ref is None:
            raise ValueError("commit_ref is required, cannot be None.")

        source_repo = GitRepo(local_path=source)
        commit_id = source_repo.__commit_id_for_remote_ref(
            remote=remote, commit_ref=commit_ref
        )
        source_repo.__ensure_commit_fetched(remote=remote, commit_id=commit_id)
        temp_branch_name = "temp-b-"+commit_id
        source_repo.__branch_create(branch_name=temp_branch_name,
                                    start_point=commit_id)
        GitRepo.__clone_from_local(source=source, dest=dest,
                                   branch=temp_branch_name, single_branch=True)
        source_repo.__branch_delete(branch_name=temp_branch_name, force=True)
