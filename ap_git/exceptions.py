class APGitException(Exception):
    pass


class NonGitDirectoryError(APGitException):
    def __init__(self, directory: str):
        message = f"The directory '{directory}' is not a Git directory."
        super().__init__(message)


class CommitNotFoundError(APGitException):
    def __init__(self, commit_ref: str):
        message = f"The commit with ref/id '{commit_ref}' not found in tree."
        super().__init__(message)


class RemoteNotFoundError(APGitException):
    def __init__(self, remote: str):
        message = f"The remote named '{remote}' is not added."
        super().__init__(message)


class DuplicateRemoteError(APGitException):
    def __init__(self, remote: str):
        message = f"The remote named '{remote}' already exists."
        super().__init__(message)
