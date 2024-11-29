import redis

class Builder:
    def __init__(self,
                 sourcedir: str,
                 outdir: str,
                 redis_host: str = 'localhost',
                 redis_port: int = 6379,
                 build_events_channel: str = 'ap_build_events') -> None:
        self.__sourcedir = sourcedir
        self.__outdir = outdir
        self.__redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
        self.__pubsub = self.__redis_client.pubsub()
        self.__pubsub.subscribe(build_events_channel)



    def build(self, build_id: str):

        return

    def run(self):
        for message in self.__pubsub.listen():
            if message['type'] == 'message':
                build_id = message['data'].decode('utf-8')
                self.build(build_id=build_id)
