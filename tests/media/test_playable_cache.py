from __future__ import annotations

import threading
import time

import pytest

from dashbox.media.playable_cache import PlayableInfoCache


def test_follower_timeout_does_not_cancel_leader() -> None:
    cache = PlayableInfoCache(wait_timeout=0.1)
    release_leader = threading.Event()
    loader_started = threading.Event()
    leader_errors: list[BaseException] = []

    def slow_loader() -> dict[str, object]:
        loader_started.set()
        release_leader.wait(timeout=5.0)
        return {"id": "leader"}

    def run_leader() -> None:
        try:
            cache.get_or_create("key", slow_loader)
        except BaseException as exc:
            leader_errors.append(exc)

    leader = threading.Thread(target=run_leader)
    leader.start()
    assert loader_started.wait(timeout=1.0)

    with pytest.raises(TimeoutError, match="still running"):
        cache.get_or_create("key", lambda: {"id": "follower"})

    release_leader.set()
    leader.join(timeout=1.0)
    assert not leader.is_alive()
    assert leader_errors == []
    assert cache.get_or_create("key", lambda: {"id": "unused"}) == {"id": "leader"}


def test_follower_gets_leader_result_after_waiting() -> None:
    cache = PlayableInfoCache(wait_timeout=1.0)
    release_leader = threading.Event()
    loader_started = threading.Event()
    results: list[dict[str, object]] = []

    def slow_loader() -> dict[str, object]:
        loader_started.set()
        release_leader.wait(timeout=5.0)
        return {"id": "leader"}

    leader = threading.Thread(target=lambda: cache.get_or_create("key", slow_loader))
    leader.start()
    assert loader_started.wait(timeout=1.0)

    follower = threading.Thread(target=lambda: results.append(cache.get_or_create("key", lambda: {"id": "follower"})))
    follower.start()
    time.sleep(0.05)
    release_leader.set()
    leader.join(timeout=1.0)
    follower.join(timeout=1.0)

    assert not leader.is_alive()
    assert not follower.is_alive()
    assert results == [{"id": "leader"}]


def test_leader_completes_normally() -> None:
    cache = PlayableInfoCache(wait_timeout=0.1)

    assert cache.get_or_create("key", lambda: {"id": "leader"}) == {"id": "leader"}
