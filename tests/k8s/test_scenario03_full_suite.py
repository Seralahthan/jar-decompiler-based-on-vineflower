"""
Scenario 03: Full functional + concurrency tests on K8s.

Mirrors all tests that were run against the Docker container setup:
  - Content-based deduplication
  - Cache isolation between different JARs
  - Multi-version decompilation accuracy
  - Concurrent uploads (multiple users)
  - Concurrent decompilation (same class, multiple threads)
  - Mixed concurrent workloads

Prerequisites:
  - minikube running with the app deployed
  - kubectl port-forward svc/jar-decompiler-svc 8443:443 -n jar-decompiler
  - Fixture JARs built: tests/fixtures/build_jars.sh

Run:
  K8S_BASE_URL=https://localhost:8443 pytest tests/k8s/test_scenario03_full_suite.py -v
"""
import threading
import time
import pytest
import requests
import urllib3

urllib3.disable_warnings()

from conftest import upload_jar, decompile_class, wait_for_index, wait_for_decompile


def new_session():
    """Create an independent requests.Session (for concurrent threads)."""
    s = requests.Session()
    s.verify = False
    return s


# ─── Content-Based Deduplication ─────────────────────────────────────────────

class TestContentDeduplication:
    """Same JAR uploaded by different users shares the global cache."""

    def test_second_upload_gets_cached_class(self, session, base_url, jar_paths):
        """Upload the same JAR twice (different job IDs). Second decompile
        should hit the global cache keyed by JAR SHA-256."""
        job1 = upload_jar(session, base_url, jar_paths["java8"])
        # Decompile a class on job1 (cold)
        r1 = decompile_class(session, base_url, job1, "com/test/java8/StreamDemo.class")
        assert r1.status_code == 200

        # Upload same JAR again → different job_id
        s2 = new_session()
        job2 = upload_jar(s2, base_url, jar_paths["java8"])
        assert job2 != job1

        # Decompile same class on job2 → should be cached from global cache
        r2 = decompile_class(s2, base_url, job2, "com/test/java8/StreamDemo.class")
        assert r2.status_code == 200
        data = r2.json()
        assert data.get("cached") is True, "Same JAR content should use global cache"
        assert "StreamDemo" in data["source"]

    def test_different_jars_have_isolated_content(self, session, base_url, jar_paths):
        """Different JARs return their own class content (no cross-JAR pollution)."""
        job1 = upload_jar(session, base_url, jar_paths["java8"])
        r1 = decompile_class(session, base_url, job1, "com/test/java8/StreamDemo.class")
        source1 = r1.json()["source"]

        s2 = new_session()
        job2 = upload_jar(s2, base_url, jar_paths["java17"])
        r2 = decompile_class(s2, base_url, job2, "com/test/java17/PointRecord.class")
        source2 = r2.json()["source"]

        # Each JAR returns its own class — no cross-contamination
        assert "StreamDemo" in source1
        assert "PointRecord" in source2
        assert source1 != source2, "Different JARs should return different source code"

    def test_cache_shared_across_sessions(self, session, base_url, jar_paths):
        """Two completely independent sessions uploading the same JAR should
        share the decompiled class cache and get identical source code."""
        s1 = new_session()
        job1 = upload_jar(s1, base_url, jar_paths["java11"])
        r1 = decompile_class(s1, base_url, job1, "com/test/java11/VarDemo.class")
        assert r1.status_code == 200
        source1 = r1.json()["source"]

        # Different session, same JAR
        s2 = new_session()
        job2 = upload_jar(s2, base_url, jar_paths["java11"])
        r2 = decompile_class(s2, base_url, job2, "com/test/java11/VarDemo.class")
        assert r2.status_code == 200
        source2 = r2.json()["source"]

        # Both sessions get identical source (from global cache)
        assert source1 == source2, "Same JAR should produce identical source across sessions"
        # Second session should definitely be cached
        assert r2.json().get("cached") is True


# ─── Cache Behavior ──────────────────────────────────────────────────────────

class TestCacheBehavior:
    def test_cached_response_is_faster(self, session, base_url, jar_paths):
        """Cached responses should be significantly faster than cold decompiles."""
        job_id = upload_jar(session, base_url, jar_paths["java17"])

        # Cold decompile
        t1 = time.time()
        decompile_class(session, base_url, job_id, "com/test/java17/ShapeHierarchy.class")
        cold_time = time.time() - t1

        # Cached decompile
        t2 = time.time()
        r = decompile_class(session, base_url, job_id, "com/test/java17/ShapeHierarchy.class")
        cached_time = time.time() - t2

        assert r.json().get("cached") is True
        # Cached should be at least 2x faster (usually 10x+)
        assert cached_time < cold_time, \
            f"Cached ({cached_time:.3f}s) should be faster than cold ({cold_time:.3f}s)"

    def test_index_cache_persists_across_uploads(self, session, base_url, jar_paths):
        """Method index for the same JAR should be cached globally."""
        job1 = upload_jar(session, base_url, jar_paths["java8"])
        session.post(f"{base_url}/api/build-index/{job1}")
        wait_for_index(session, base_url, job1)

        # Upload same JAR again
        s2 = new_session()
        job2 = upload_jar(s2, base_url, jar_paths["java8"])
        r = s2.post(f"{base_url}/api/build-index/{job2}")
        # Should return 200 (already indexed) not 202 (started)
        assert r.status_code == 200, \
            f"Expected 200 (cached index), got {r.status_code}"


# ─── Multi-Version Accuracy ──────────────────────────────────────────────────

class TestDecompilationAccuracy:
    """Verify decompiled output contains expected Java constructs."""

    @pytest.mark.parametrize("version,class_path,expected_patterns", [
        ("java8", "com/test/java8/StreamDemo.class",
         ["StreamDemo", "import", "class"]),
        ("java8", "com/test/java8/LambdaHolder.class",
         ["LambdaHolder", "class"]),
        ("java11", "com/test/java11/VarDemo.class",
         ["VarDemo", "class"]),
        ("java17", "com/test/java17/PointRecord.class",
         ["PointRecord"]),
        ("java17", "com/test/java17/ShapeHierarchy.class",
         ["ShapeHierarchy", "class"]),
        ("java21", "com/test/java21/ModernPatterns.class",
         ["ModernPatterns", "class"]),
    ])
    def test_decompile_accuracy(self, session, base_url, jar_paths,
                                 version, class_path, expected_patterns):
        job_id = upload_jar(session, base_url, jar_paths[version])
        r = decompile_class(session, base_url, job_id, class_path)
        assert r.status_code == 200
        source = r.json().get("source", "")
        for pattern in expected_patterns:
            assert pattern in source, \
                f"Expected '{pattern}' in decompiled source of {class_path}"


# ─── Concurrent Uploads ──────────────────────────────────────────────────────

class TestConcurrentUploads:
    def test_parallel_uploads_4_users(self, base_url, jar_paths):
        """4 users uploading different JARs simultaneously."""
        results = {}

        def do_upload(name, jar_path):
            s = new_session()
            try:
                job_id = upload_jar(s, base_url, jar_path)
                r = s.get(f"{base_url}/api/tree/{job_id}")
                results[name] = {
                    "job_id": job_id,
                    "tree_ok": r.status_code == 200,
                    "class_count": r.json().get("class_count", 0),
                }
            except Exception as e:
                results[name] = {"error": str(e)}

        threads = []
        for ver in ["java8", "java11", "java17", "java21"]:
            t = threading.Thread(target=do_upload, args=(ver, jar_paths[ver]))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=30)

        assert len(results) == 4, f"Expected 4 results, got {len(results)}"
        for ver, result in results.items():
            assert "error" not in result, f"{ver} failed: {result.get('error')}"
            assert result["tree_ok"], f"{ver}: tree request failed"
            assert result["class_count"] > 0, f"{ver}: no classes found"

    def test_parallel_uploads_same_jar(self, base_url, jar_paths):
        """Multiple users uploading the same JAR get separate job IDs."""
        job_ids = []

        def do_upload():
            s = new_session()
            jid = upload_jar(s, base_url, jar_paths["java8"])
            job_ids.append(jid)

        threads = [threading.Thread(target=do_upload) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert len(job_ids) == 4
        assert len(set(job_ids)) == 4, "All job IDs should be unique"


# ─── Concurrent Decompilation ────────────────────────────────────────────────

class TestConcurrentDecompilation:
    def test_same_class_10_threads(self, base_url, jar_paths):
        """10 threads decompiling the same class concurrently.
        Only one should actually run Vineflower (distributed lock);
        the rest should wait and get the cached result."""
        s = new_session()
        job_id = upload_jar(s, base_url, jar_paths["java8"])

        results = []
        errors = []

        def decompile_one():
            sv = new_session()
            try:
                r = decompile_class(sv, base_url, job_id,
                                    "com/test/java8/StreamDemo.class")
                results.append({
                    "status": r.status_code,
                    "cached": r.json().get("cached"),
                    "has_source": "source" in r.json(),
                })
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=decompile_one) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)

        assert len(errors) == 0, f"Errors: {errors}"
        assert len(results) == 10, f"Expected 10 results, got {len(results)}"
        assert all(r["status"] == 200 for r in results), \
            "All threads should get 200"
        assert all(r["has_source"] for r in results), \
            "All threads should get source code"

    def test_different_classes_parallel(self, base_url, jar_paths):
        """Multiple threads decompiling different classes from the same JAR."""
        s = new_session()
        job_id = upload_jar(s, base_url, jar_paths["java8"])

        classes = [
            "com/test/java8/StreamDemo.class",
            "com/test/java8/LambdaHolder.class",
        ]
        results = {}

        def decompile_one(cls):
            sv = new_session()
            r = decompile_class(sv, base_url, job_id, cls)
            results[cls] = r.status_code == 200

        threads = [threading.Thread(target=decompile_one, args=(c,)) for c in classes]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)

        for cls in classes:
            assert results.get(cls) is True, f"Failed to decompile {cls}"

    def test_mixed_jars_concurrent(self, base_url, jar_paths):
        """Concurrent decompilation across different JARs."""
        workloads = [
            ("java8", "com/test/java8/StreamDemo.class"),
            ("java11", "com/test/java11/VarDemo.class"),
            ("java17", "com/test/java17/PointRecord.class"),
            ("java21", "com/test/java21/ModernPatterns.class"),
        ]
        results = {}

        def work(ver, cls):
            sv = new_session()
            jid = upload_jar(sv, base_url, jar_paths[ver])
            r = decompile_class(sv, base_url, jid, cls)
            results[ver] = {
                "status": r.status_code,
                "has_source": "source" in r.json(),
            }

        threads = [threading.Thread(target=work, args=(v, c)) for v, c in workloads]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)

        for ver in ["java8", "java11", "java17", "java21"]:
            assert results[ver]["status"] == 200, f"{ver}: got {results[ver]['status']}"
            assert results[ver]["has_source"], f"{ver}: no source returned"


# ─── Full Workflow End-to-End ────────────────────────────────────────────────

class TestEndToEndWorkflow:
    """Complete user workflow: upload → browse → decompile → index → search → ZIP."""

    def test_complete_workflow(self, session, base_url, jar_paths):
        # 1. Upload
        job_id = upload_jar(session, base_url, jar_paths["java17"])

        # 2. Browse tree
        r = session.get(f"{base_url}/api/tree/{job_id}")
        assert r.status_code == 200
        tree = r.json()
        assert tree["class_count"] > 0

        # 3. Decompile individual classes
        for cls in ["com/test/java17/PointRecord.class",
                     "com/test/java17/ShapeHierarchy.class"]:
            r = decompile_class(session, base_url, job_id, cls)
            assert r.status_code == 200
            assert "source" in r.json()

        # 4. Build index
        session.post(f"{base_url}/api/build-index/{job_id}")
        assert wait_for_index(session, base_url, job_id)

        # 5. Search
        r = session.get(f"{base_url}/api/search-methods/{job_id}?q=Point")
        assert r.status_code == 200

        # 6. Full decompile + ZIP
        session.post(f"{base_url}/api/start-decompile/{job_id}")
        assert wait_for_decompile(session, base_url, job_id)
        r = session.get(f"{base_url}/api/download/{job_id}")
        assert r.status_code == 200
        assert r.content[:2] == b"PK"
