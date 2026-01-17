from threading import Lock

class ThreadLock:
    _lock = Lock()
    
    @classmethod
    def get_lock(cls):
        return cls._lock

lock = ThreadLock()