"""Shared fixtures and helpers for the integration test suite."""

import os
import time
from pathlib import Path

import pytest
import redis as redis_lib
import requests

BASE_URL = os.environ.get("DECOMPILER_URL", "http://localhost:9090")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
FIXTURES_DIR = Path(__file__).parent / "fixtures"
JARS_DIR = FIXTURES_DIR / "jars"


DOCKER_CONTAINER = os.environ.get("DECOMPILER_CONTAINER", "jar-decompiler-test")


def flush_global_cache():
    """Delete all cache:*, index:*, and lock:* keys from Redis.

    This ensures tests that assert on cold/warm cache behaviour start
    from a known-clean state.  Tries direct Redis first; falls back to
    ``docker exec redis-cli`` when Redis is inside the container.
    """
    # Try direct Redis connection first
    try:
        r = redis_lib.from_url(REDIS_URL, decode_responses=True)
        r.ping()
        for pattern in ("cache:*", "index:*", "lock:*"):
            cursor = "0"
            while True:
                cursor, keys = r.scan(cursor=cursor, match=pattern, count=200)
                if keys:
                    r.delete(*keys)
                if cursor == 0 or cursor == "0":
                    break
        return
    except Exception:
        pass

    # Fallback: flush via docker exec (Redis bundled inside the container)
    import subprocess
    try:
        subprocess.run(
            ["docker", "exec", DOCKER_CONTAINER, "redis-cli", "FLUSHDB"],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass  # No Redis reachable — in-memory mode, nothing to flush


# ── Pytest fixtures ──────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


@pytest.fixture(scope="session")
def session():
    """Shared requests.Session with connection pooling."""
    s = requests.Session()
    # Wait for the service to become reachable
    for attempt in range(15):
        try:
            s.get(f"{BASE_URL}/", timeout=5)
            return s
        except requests.ConnectionError:
            time.sleep(2)
    pytest.fail(f"Service not reachable at {BASE_URL} after 30s")


@pytest.fixture()
def clean_cache():
    """Flush the global decompiler cache before a test.

    Use this fixture in any test that needs to observe cold-cache behaviour.
    """
    flush_global_cache()
    yield
    # No teardown needed — other tests that don't care about cache state
    # simply don't request this fixture.


@pytest.fixture(scope="session")
def jar_paths():
    """Dict mapping version label to JAR file path."""
    paths = {}
    for name in ("java8-fixtures.jar", "java11-fixtures.jar",
                  "java17-fixtures.jar", "java21-fixtures.jar"):
        p = JARS_DIR / name
        assert p.exists(), f"Fixture JAR not found: {p}. Run build_jars.sh first."
        paths[name.split("-")[0]] = p
    return paths


# ── Helper functions (not fixtures — called explicitly by tests) ─────────


def upload_jar(session, base_url, jar_path):
    """Upload a JAR and return job_id."""
    with open(jar_path, "rb") as f:
        resp = session.post(
            f"{base_url}/api/upload",
            files={"jar": (jar_path.name, f, "application/java-archive")},
        )
    assert resp.status_code == 202, f"Upload failed: {resp.status_code} {resp.text}"
    data = resp.json()
    assert "job_id" in data
    return data["job_id"]


def decompile_class(session, base_url, job_id, class_path):
    """Decompile a single class and return (source, cached) tuple."""
    resp = session.post(
        f"{base_url}/api/decompile-class/{job_id}",
        json={"class_path": class_path},
    )
    assert resp.status_code == 200, f"Decompile failed: {resp.status_code} {resp.text}"
    data = resp.json()
    return data["source"], data["cached"]


def poll_status_until(session, base_url, job_id, target="done",
                      timeout=120, interval=2):
    """Poll /api/status/<job_id> until status matches target or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = session.get(f"{base_url}/api/status/{job_id}")
        assert resp.status_code == 200
        data = resp.json()
        if data["status"] == target:
            return data
        if data["status"] == "error":
            pytest.fail(f"Job {job_id} errored: {data['message']}")
        time.sleep(interval)
    pytest.fail(f"Job {job_id} did not reach '{target}' within {timeout}s")


def poll_index_until(session, base_url, job_id, target="done",
                     timeout=120, interval=2):
    """Poll /api/index-status/<job_id> until status matches target or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = session.get(f"{base_url}/api/index-status/{job_id}")
        assert resp.status_code == 200
        data = resp.json()
        if data["status"] == target:
            return data
        if data["status"] == "error":
            pytest.fail(f"Index for {job_id} errored")
        time.sleep(interval)
    pytest.fail(f"Index for {job_id} did not reach '{target}' within {timeout}s")
