
class RateLimiterException(Exception):
    pass


class RateLimitExceededException(RateLimiterException):
    def __init__(self, *args):
        message = "Too many requests. Try after some time."
        super().__init__(message)
