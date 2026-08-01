"""In-memory доставка id durable chat events и rate limiting для single-process."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque


OVERFLOW = object()


@dataclass(eq=False)
class ChatSubscription:
    queue: asyncio.Queue[int | object]
    user_id: int


class ChatBroker:
    """Fan-out event ids; содержимое событий всегда перечитывается из БД."""

    def __init__(self, queue_size: int = 100) -> None:
        self.queue_size = queue_size
        self._subscribers: set[ChatSubscription] = set()
        self._lock = asyncio.Lock()
        self._closed = False

    async def subscribe(self, user_id: int) -> ChatSubscription:
        subscription = ChatSubscription(
            queue=asyncio.Queue(maxsize=self.queue_size),
            user_id=user_id,
        )
        async with self._lock:
            if self._closed:
                raise RuntimeError("Chat broker is closed")
            self._subscribers.add(subscription)
        return subscription

    async def unsubscribe(self, subscription: ChatSubscription) -> None:
        async with self._lock:
            self._subscribers.discard(subscription)

    async def publish(self, event_id: int) -> None:
        async with self._lock:
            subscribers = tuple(self._subscribers)
        for subscription in subscribers:
            try:
                subscription.queue.put_nowait(event_id)
            except asyncio.QueueFull:
                # Sentinel обязан попасть в bounded queue. Старые id безопасно отбросить:
                # reconnect восстановит их из durable chat_events.
                while True:
                    try:
                        subscription.queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                subscription.queue.put_nowait(OVERFLOW)

    async def close(self) -> None:
        async with self._lock:
            self._closed = True
            subscribers = tuple(self._subscribers)
            self._subscribers.clear()
        for subscription in subscribers:
            while True:
                try:
                    subscription.queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            subscription.queue.put_nowait(OVERFLOW)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


class ChatRateLimiter:
    """Sliding-window limits для текущего single-process deployment."""

    def __init__(self) -> None:
        self._attempts: dict[tuple[str, int], Deque[float]] = defaultdict(deque)
        self._streams: dict[int, int] = defaultdict(int)
        self._lock = asyncio.Lock()

    async def allow(
        self,
        action: str,
        user_id: int,
        *,
        limit: int,
        period_seconds: float,
    ) -> bool:
        now = time.monotonic()
        cutoff = now - period_seconds
        key = (action, user_id)
        async with self._lock:
            self._prune_inactive(now)
            attempts = self._attempts[key]
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            if len(attempts) >= limit:
                return False
            attempts.append(now)
            return True

    async def acquire_stream(self, user_id: int, *, limit: int) -> bool:
        async with self._lock:
            if self._streams[user_id] >= limit:
                return False
            self._streams[user_id] += 1
            return True

    async def release_stream(self, user_id: int) -> None:
        async with self._lock:
            current = self._streams.get(user_id, 0)
            if current <= 1:
                self._streams.pop(user_id, None)
            else:
                self._streams[user_id] = current - 1

    def _prune_inactive(self, now: float) -> None:
        # Самое длинное текущее окно — 10 минут; часовой запас не даёт ключам
        # неактивных пользователей бесконечно накапливаться.
        cutoff = now - 3600
        stale = [
            key
            for key, attempts in self._attempts.items()
            if not attempts or attempts[-1] <= cutoff
        ]
        for key in stale:
            self._attempts.pop(key, None)

