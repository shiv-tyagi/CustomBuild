import logging
import subprocess
import string

logger = logging.getLogger(__name__)


class GitWizard:
    def __init__(self, local_repo_path):
        self.local_repo_path = local_repo_path
        return

    def __checkout(self, commit_ref: str, force=False):
        cmd = ['git', 'checkout', commit_ref]

        if force:
            cmd.append('-f')

        logger.debug(' '.join(cmd))
        subprocess.run(cmd, cwd=self.local_repo_path, shell=False, check=True)

    def __reset(self, commit_ref: str, hard=False):
        cmd = ['git', 'reset', commit_ref]

        if hard:
            cmd.append('--hard')

        logger.debug(''.join(cmd))
        subprocess.run(cmd, cwd=self.local_repo_path, shell=False, check=True)

    def __force_recursive_clean(self):
        cmd = ['git', 'clean', '-xdff']
        logger.debug(''.join(cmd))
        subprocess.run(cmd, cwd=self.local_repo_path, shell=False, check=True)

    def __clone(self, out_path: str, branch: str=None, single_branch=False):
        cmd = ['git', 'clone', self.local_repo_path,  out_path]

        if branch:
            cmd.append('--branch='+branch)

        if single_branch:
            cmd.append('--single-branch')

        logger.debug(''.join(cmd))
        subprocess.run(cmd, cwd=self.local_repo_path, shell=False, check=True)

    def __remote_list(self):
        cmd = ['git', 'remote']

        logger.debug(' '.join(cmd))
        ret = subprocess.run(cmd, cwd=self.local_repo_path, shell=False, capture_output=True, encoding='utf-8', check=True)

        return ret.stdout.split('\n')[:-1]
    
    def __is_commit_present_locally(self, commit_ref: str):
        cmd = ['git', 'rev-parse', commit_ref]
        logger.debug(''.join(cmd))
        ret = subprocess.run(cmd, cwd=self.local_repo_path, shell=False)
        return ret.returncode == 0

    def __is_valid_hex_string(self, test_str: str):
        return all(c in 'abcdef' for c in test_str)

    def fetch_remote(self, remote: str, force=False, tags=False, all=False, recurse_submodules=False):
        cmd = ['git', 'fetch', remote]

        if force:
            cmd.append('--force')

        if tags:
            cmd.append('--tags')

        if all:
            cmd.append('--all')

        if recurse_submodules:
            cmd.append('--recurse_submodules=yes')
        else:
            cmd.append('--recurse_submodules=no')

        logger.debug(''.join(cmd))
        subprocess.run(cmd, cwd=self.local_repo_path, shell=False)

    def __branch_create(self, branch_name: str, start_point: str=None):
        cmd = ['git', 'branch', branch_name]

        if start_point:
            cmd.append(start_point)

        logger.debug(''.join(cmd))
        subprocess.run(cmd, cwd=self.local_repo_path, shell=False, check=True)

    def __branch_delete(self, branch_name: str, force=False):
        cmd = ['git', 'branch', '-d', branch_name]

        if force:
            cmd.append('--force')

        logger.debug(''.join(cmd))
        subprocess.run(cmd, cwd=self.local_repo_path, shell=False, check=True)
    
    def commit_id_for_remote_ref(self, remote: str, commit_ref: str):
        allowed_ref_types = ['tags', 'heads'] # allow branches and tags only for now

        split_ref = commit_ref.split('/', 3)

        if len(split_ref) != 3 or split_ref[0] != 'ref':
            raise Exception("invalid format")

        _, ref_type, ref_name = split_ref

        if ref_type not in allowed_ref_types:
            raise Exception("ref type not supported")

        cmd = ['git', 'ls-remote', remote]
        ret =  subprocess.run(cmd, cwd=self.local_repo_path, encoding='utf-8', capture_output=True, shell=False, check=True)
        '''To-do: handle different scenarios like remote not added, connection error etc.'''

        for line in ret.stdout.split('\n')[:-1]:
            (commit_id, res_ref) = line.split('\t')
            _, res_ref_type, res_ref_name = res_ref.split('/', 3)

            if res_ref_type not in allowed_ref_types:
                continue

            if res_ref_name == ref_name:
                return commit_id

        return None
    
    def __ensure_commit_exists(self, remote: str, commit_id: str):
        if not self.__is_commit_present_locally(commit_ref=commit_ref):
            # fetch and retry
            self.fetch_remote(remote=remote, force=True, tags=True)
        
            if not self.__is_commit_present_locally(commit_ref=commit_id):
                raise Exception("commit not found exception")

    def checkout_remote_commit_ref(self, remote: str, commit_ref: str, force=False, hard_reset=False, clean_working_tree=False):
        # this handles conflicting refs
        if self.__is_valid_hex_string(test_str=commit_ref):
            # we got a commit hash, use it directly
            commit_id = commit_ref
        else:
            # try finding hash for ref
            commit_id = self.commit_id_for_remote_ref(remote=remote, commit_ref=commit_ref)

            if not commit_id:
                raise Exception("Commit not found in remote")
        
        if not self.__is_commit_present_locally(commit_ref=commit_id):
            # fetch and retry
            self.fetch_remote(remote=remote, force=True, tags=True)
        
            if not self.__is_commit_present_locally(commit_ref=commit_id):
                raise Exception("commit not found exception")

        self.__checkout(commit_ref=commit_id, force=force)

        if hard_reset:
            self.__reset(commit_ref=commit_id, hard=True)
        
        if clean_working_tree:
            self.__force_recursive_clean()
    
    def submodule_update(self, init=False, recursive=False, force=False):
        cmd = ['git', 'submodule', 'update']

        if init:
            cmd.append('--init')

        if recursive:
            cmd.append('--recursive')

        if force:
            cmd.append('--force')

        logger.debug(''.join(cmd))
        subprocess.run(cmd, cwd=self.local_repo_path, shell=False, check=True)

    def remote_set_url(self, remote: str, url: str):
        cmd = ['git', 'remote', 'set-url', remote, url]
        logger.debug(''.join(cmd))
        subprocess.run(cmd, cwd=self.local_repo_path, check=True)

    def remote_add(self, remote: str, url: str, overwrite_url=False):
        if remote in self.__remote_list():
            if overwrite_url:
                self.remote_set_url(remote=remote, url=url)
            else:
                raise Exception("Remote %s already exists" % remote)

        cmd = ['git', 'remote', 'add', remote, url]
        logger.debug(''.join(cmd))
        subprocess.run(cmd, cwd=self.local_repo_path, shell=False, check=True)

    def clone_repo_at_commit(self, commit_id: str, out_dir: str):
        if not self.__is_valid_hex_string(commit_id):
            raise Exception("Invalid commit id")
        
        ## add same logic like checkout

        temp_branch_name = "temp-b-"+commit_id
        self.__branch_create(branch_name=temp_branch_name, start_point=commit_id)
        self.__clone(out_path=out_dir, branch=temp_branch_name, single_branch=True)
        self.__branch_delete(branch_name=temp_branch_name, force=True)
        return

# use git checkout return code to handle situations like dirty working tree etc.
# Nonetype exceptions
# 