"""Multi-threaded concurrency tests — validates locking, caching, and backpressure."""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from conftest import decompile_class, upload_jar


class TestConcurrentUploads:
    """Multiple users uploading different JARs simultaneously."""

    def test_parallel_uploads_all_succeed(self, session, base_url, jar_paths):
        versions = list(jar_paths.keys())

        def upload_one(version):
            # Each thread uses its own session for connection safety
            s = requests.Session()
            return version, upload_jar(s, base_url, jar_paths[version])

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(upload_one, v) for v in versions]
            results = [f.result(timeout=30) for f in futures]

        job_ids = [r[1] for r in results]
        assert len(set(job_ids)) == len(versions), "All uploads should produce unique job IDs"

        # Verify each job's tree is accessible
        for version, job_id in results:
            resp = session.get(f"{base_url}/api/tree/{job_id}")
            assert resp.status_code == 200
            assert resp.json()["class_count"] >= 2


class TestConcurrentDecompileSameClass:
    """Multiple users decompiling the same class from the same JAR content.
    Only one JVM should spawn; others should wait and get the cached result."""

    def test_same_class_10_concurrent_requests(self, session, base_url, jar_paths, clean_cache):
        jar = jar_paths["java8"]
        class_path = "com/test/java8/StreamDemo.class"
        num_threads = 10

        # Upload the same JAR N times (simulating N different users)
        job_ids = [upload_jar(session, base_url, jar) for _ in range(num_threads)]

        def decompile_one(job_id): 
            s = requests.Session()
            resp = s.post(
                f"{base_url}/api/decompile-class/{job_id}",
                json={"class_path": class_path},
            )
            assert resp.status_code == 200
            return resp.json()

        with ThreadPoolExecutor(max_workers=num_threads) as pool:
            futures = [pool.submit(decompile_one, jid) for jid in job_ids]
            results = [f.result(timeout=60) for f in futures]

        # All should return the same source
        sources = {r["source"] for r in results}
        assert len(sources) == 1, "All threads should get identical decompiled source"

        # At most a few should have cached=False (ideally just 1, but timing
        # means a small number might slip through before the cache is populated)
        cold_count = sum(1 for r in results if not r["cached"])
        assert cold_count >= 1, "At least one request should be a cold decompile"
        assert cold_count <= 3, (
            f"Expected at most 3 cold decompiles (lock contention), got {cold_count}"
        )


class TestConcurrentDecompileDifferentClasses:
    """Multiple users decompiling different classes from the same JAR concurrently.
    These should run in parallel without blocking each other."""

    def test_different_classes_parallel(self, session, base_url, jar_paths):
        job_id = upload_jar(session, base_url, jar_paths["java8"])
        classes = [
            "com/test/java8/StreamDemo.class",
            "com/test/java8/LambdaHolder.class",
        ]

        def decompile_one(class_path):
            s = requests.Session()
            resp = s.post(
                f"{base_url}/api/decompile-class/{job_id}",
                json={"class_path": class_path},
            )
            assert resp.status_code == 200
            return class_path, resp.json()["source"]

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(decompile_one, cp) for cp in classes]
            results = dict(f.result(timeout=30) for f in futures)

        assert "StreamDemo" in results[classes[0]]
        assert "LambdaHolder" in results[classes[1]]


class TestConcurrentSameJarTwoUploads:
    """Two uploads of the same JAR — second decompile should hit global cache."""

    def test_cache_shared_across_jobs(self, session, base_url, jar_paths, clean_cache):
        jar = jar_paths["java11"]
        class_path = "com/test/java11/VarDemo.class"

        # Upload 1: cold decompile
        job_a = upload_jar(session, base_url, jar)
        source_a, cached_a = decompile_class(session, base_url, job_a, class_path)
        assert cached_a is False

        # Upload 2: same JAR, different job_id — should be cached
        job_b = upload_jar(session, base_url, jar)
        source_b, cached_b = decompile_class(session, base_url, job_b, class_path)
        assert cached_b is True
        assert source_a == source_b


class TestConcurrentMixedJars:
    """Concurrent decompilation across different Java versions simultaneously."""

    def test_all_versions_decompile_concurrently(self, session, base_url, jar_paths):
        tasks = [
            ("java8", "com/test/java8/StreamDemo.class", "StreamDemo"),
            ("java11", "com/test/java11/VarDemo.class", "VarDemo"),
            ("java17", "com/test/java17/PointRecord.class", "PointRecord"),
            ("java21", "com/test/java21/ModernPatterns.class", "ModernPatterns"),
        ]

        # Upload all JARs first
        uploads = {}
        for version, class_path, _ in tasks:
            uploads[version] = upload_jar(session, base_url, jar_paths[version])

        def decompile_one(version, class_path, expected_class):
            s = requests.Session()
            job_id = uploads[version]
            resp = s.post(
                f"{base_url}/api/decompile-class/{job_id}",
                json={"class_path": class_path},
            )
            assert resp.status_code == 200
            source = resp.json()["source"]
            assert expected_class in source
            return version, source

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [
                pool.submit(decompile_one, v, cp, ec)
                for v, cp, ec in tasks
            ]
            results = dict(f.result(timeout=60) for f in futures)

        assert len(results) == 4


class TestFloodBackpressure:
    """Flood the full-decompile pool to trigger 503 backpressure.

    With defaults: FULL_DECOMPILE_POOL_TOTAL=2, queue_limit=4.
    Submitting more than 4 start-decompile requests simultaneously should
    cause at least one 503 response.
    """

    def test_start_decompile_flood_returns_503(self, session, base_url, jar_paths):
        jar = jar_paths["java17"]
        num_jobs = 10

        # Upload N JARs
        job_ids = [upload_jar(session, base_url, jar) for _ in range(num_jobs)]

        def start_one(job_id):
            s = requests.Session()
            resp = s.post(f"{base_url}/api/start-decompile/{job_id}")
            return resp.status_code

        # Fire all start-decompile requests concurrently
        with ThreadPoolExecutor(max_workers=num_jobs) as pool:
            futures = [pool.submit(start_one, jid) for jid in job_ids]
            status_codes = [f.result(timeout=30) for f in futures]

        accepted = status_codes.count(202)
        busy = status_codes.count(503)

        assert accepted >= 1, "At least one job should be accepted"
        assert busy >= 1, (
            f"Expected at least one 503 (backpressure), but got "
            f"{accepted} accepted, {busy} busy out of {num_jobs}"
        )
