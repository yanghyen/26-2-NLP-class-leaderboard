from collections import deque
from typing import Protocol

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings


class QueueUnavailableError(RuntimeError):
    pass


class JobQueue(Protocol):
    def enqueue(self, job_id: str) -> None: ...

    def dequeue(self, timeout: int = 0) -> str | None: ...


class RedisJobQueue:
    def __init__(self, url: str | None = None, name: str | None = None) -> None:
        settings = get_settings()
        self.name = name or settings.queue_name
        self.client = Redis.from_url(url or settings.redis_url, decode_responses=True)

    def enqueue(self, job_id: str) -> None:
        try:
            # Recovery may redispatch a DB-backed QUEUED job. Keep FIFO without
            # accumulating copies on every sweep (Redis >= 6; Compose uses 7).
            self.client.eval(
                "if not redis.call('LPOS', KEYS[1], ARGV[1]) then "
                "return redis.call('RPUSH', KEYS[1], ARGV[1]) end return 0",
                1, self.name, job_id,
            )
        except RedisError as exc:
            raise QueueUnavailableError("evaluation queue is unavailable") from exc

    def dequeue(self, timeout: int = 0) -> str | None:
        try:
            item = self.client.blpop(self.name, timeout=timeout)
        except RedisError as exc:
            raise QueueUnavailableError("evaluation queue is unavailable") from exc
        return item[1] if item else None


class InMemoryJobQueue:
    def __init__(self) -> None:
        self.items: deque[str] = deque()

    def enqueue(self, job_id: str) -> None:
        self.items.append(job_id)

    def dequeue(self, timeout: int = 0) -> str | None:
        return self.items.popleft() if self.items else None


def get_job_queue() -> JobQueue:
    return RedisJobQueue()
