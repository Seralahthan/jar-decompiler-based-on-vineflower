"""Shared fixtures for K8s integration tests."""
import os
import pytest
import requests
import urllib3

urllib3.disable_warnings()

BASE_URL = os.environ.get("K8S_BASE_URL", "https://localhost:8443")
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures", "jars")

JAR_FILES = {
    "java8": os.path.join(FIXTURES_DIR, "java8-fixtures.jar"),
    "java11": os.path.join(FIXTURES_DIR, "java11-fixtures.jar"),
    "java17": os.path.join(FIXTURES_DIR, "java17-fixtures.jar"),
    "java21": os.path.join(FIXTURES_DIR, "java21-fixtures.jar"),
}


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


@pytest.fixture
def session():
    """A fresh requests.Session per test (no TLS verification)."""
    s = requests.Session()
    s.verify = False
    yield s
    s.close()


@pytest.fixture(scope="session")
def shared_session():
    """A single session reused across the entire test session."""
    s = requests.Session()
    s.verify = False
    yield s
    s.close()


@pytest.fixture(scope="session")
def jar_paths():
    """Paths to fixture JARs, keyed by Java version."""
    for ver, path in JAR_FILES.items():
        if not os.path.exists(path):
            pytest.skip(f"Fixture JAR not found: {path}. Run tests/fixtures/build_jars.sh first.")
    return JAR_FILES


def upload_jar(session, base_url, jar_path, jar_name=None):
    """Upload a JAR and return (job_id, response)."""
    name = jar_name or os.path.basename(jar_path)
    with open(jar_path, "rb") as f:
        r = session.post(
            f"{base_url}/api/upload",
            files={"jar": (name, f, "application/java-archive")},
        )
    assert r.status_code == 202, f"Upload failed: {r.status_code} {r.text}"
    data = r.json()
    assert "job_id" in data
    return data["job_id"]


def decompile_class(session, base_url, job_id, class_path):
    """Decompile a single class and return the response JSON."""
    r = session.post(
        f"{base_url}/api/decompile-class/{job_id}",
        json={"class_path": class_path},
    )
    return r


def wait_for_index(session, base_url, job_id, timeout=30):
    """Poll index-status until done or timeout."""
    import time
    for _ in range(timeout):
        r = session.get(f"{base_url}/api/index-status/{job_id}")
        if r.json().get("status") == "done":
            return True
        time.sleep(1)
    return False


def wait_for_decompile(session, base_url, job_id, timeout=60):
    """Poll status until full decompilation is done or timeout."""
    import time
    for _ in range(timeout):
        r = session.get(f"{base_url}/api/status/{job_id}")
        status = r.json().get("status")
        if status == "done":
            return True
        if status == "error":
            return False
        time.sleep(1)
    return False
