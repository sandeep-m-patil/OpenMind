import fakeredis
import pytest
import redis

MEGABYTE = 1024 * 1024
DEFAULT_CAPACITY_KEYS = 1000


class _CappedPipeline:
    def __init__(self, owner: "CappedRedis") -> None:
        self._owner = owner
        self._writes: list[tuple[str, dict]] = []

    def hset(self, key: str, mapping: dict) -> None:
        self._writes.append((key, mapping))

    def hget(self, key: str, field: str) -> None:
        self._writes.append((key, {"__hget__": field}))

    def execute(self, raise_on_error: bool = True) -> list:
        return [self._owner.apply(key, fields) for key, fields in self._writes]


class CappedRedis:
    """fakeredis with a key-count 'maxmemory': writes past capacity get OutOfMemoryError,
    like a real Redis whose memory is full of keys it is not allowed to evict."""

    def __init__(self, capacity_keys: int = DEFAULT_CAPACITY_KEYS, policy: str = "volatile-lru") -> None:
        self.store = fakeredis.FakeRedis(decode_responses=True)
        self.capacity_keys = capacity_keys
        self.policy = policy

    def pipeline(self, transaction: bool = True) -> _CappedPipeline:
        return _CappedPipeline(self)

    def apply(self, key: str, fields: dict):
        if "__hget__" in fields:
            return self.store.hget(key, fields["__hget__"])
        if not self.store.exists(key) and self.store.dbsize() >= self.capacity_keys:
            return redis.exceptions.OutOfMemoryError("command not allowed when used memory > 'maxmemory'.")
        return self.store.hset(key, mapping=fields)

    def hset(self, key: str, mapping: dict):
        result = self.apply(key, mapping)
        if isinstance(result, redis.exceptions.OutOfMemoryError):
            raise result
        return result

    def info(self, section: str) -> dict:
        if section == "memory":
            return {"used_memory": self.store.dbsize() * MEGABYTE // 32, "maxmemory": 32 * MEGABYTE}
        return {"evicted_keys": 0}

    def config_get(self, name: str) -> dict:
        return {name: self.policy}

    def ping(self) -> bool:
        return True

    def __getattr__(self, name):
        return getattr(self.store, name)


@pytest.fixture
def capped_redis() -> CappedRedis:
    return CappedRedis()
