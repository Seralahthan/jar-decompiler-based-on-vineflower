"""Cache deduplication tests — verify content-based caching across jobs."""

import time

from conftest import (
    decompile_class,
    poll_index_until,
    upload_jar,
)


class TestClassCacheDeduplication:
    """Two uploads of the same JAR should share the decompiled class cache."""

    def test_second_upload_gets_cached_class(self, session, base_url, jar_paths, clean_cache):
        jar = jar_paths["java11"]
        class_path = "com/test/java11/VarDemo.class"

        # First upload — cold decompile
        job_a = upload_jar(session, base_url, jar)
        source_a, cached_a = decompile_class(session, base_url, job_a, class_path)
        assert cached_a is False
        assert "VarDemo" in source_a

        # Second upload of the SAME JAR — should hit global cache
        job_b = upload_jar(session, base_url, jar)
        assert job_b != job_a  # different job IDs
        source_b, cached_b = decompile_class(session, base_url, job_b, class_path)
        assert cached_b is True
        assert source_a == source_b

    def test_different_jars_do_not_share_cache(self, session, base_url, jar_paths, clean_cache):
        class_path_8 = "com/test/java8/StreamDemo.class"
        class_path_11 = "com/test/java11/VarDemo.class"

        job_a = upload_jar(session, base_url, jar_paths["java8"])
        source_a, _ = decompile_class(session, base_url, job_a, class_path_8)

        job_b = upload_jar(session, base_url, jar_paths["java11"])
        source_b, cached_b = decompile_class(session, base_url, job_b, class_path_11)

        # Different JARs, different classes — no cache sharing
        assert cached_b is False
        assert source_a != source_b


class TestClassCacheSpeedImprovement:
    """Cached decompilation should be faster than cold decompilation."""

    def test_cached_is_faster(self, session, base_url, jar_paths, clean_cache):
        job_id = upload_jar(session, base_url, jar_paths["java8"])
        class_path = "com/test/java8/StreamDemo.class"

        # Cold
        t0 = time.monotonic()
        source_cold, cached_cold = decompile_class(
            session, base_url, job_id, class_path,
        )
        cold_time = time.monotonic() - t0

        # Warm
        t0 = time.monotonic()
        source_warm, cached_warm = decompile_class(
            session, base_url, job_id, class_path,
        )
        warm_time = time.monotonic() - t0

        assert cached_cold is False
        assert cached_warm is True
        assert source_cold == source_warm
        assert warm_time < cold_time, (
            f"Cached request ({warm_time:.3f}s) was not faster than "
            f"cold request ({cold_time:.3f}s)"
        )


class TestMethodIndexCacheDeduplication:
    """Two uploads of the same JAR should share the method index."""

    def test_second_upload_gets_instant_index(self, session, base_url, jar_paths, clean_cache):
        jar = jar_paths["java17"]

        # First upload — build index (runs Vineflower)
        job_a = upload_jar(session, base_url, jar)
        resp = session.post(f"{base_url}/api/build-index/{job_a}")
        assert resp.status_code == 202
        poll_index_until(session, base_url, job_a)

        # Verify search works on first job
        resp = session.get(
            f"{base_url}/api/search-methods/{job_a}", params={"q": "distance"},
        )
        results_a = resp.json()["results"]
        assert len(results_a) >= 1

        # Second upload of the SAME JAR — index should be instant
        job_b = upload_jar(session, base_url, jar)
        t0 = time.monotonic()
        resp = session.post(f"{base_url}/api/build-index/{job_b}")
        index_time = time.monotonic() - t0

        # Should return 200 (already done) because global cache has the index
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # Verify search works on second job too
        resp = session.get(
            f"{base_url}/api/search-methods/{job_b}", params={"q": "distance"},
        )
        results_b = resp.json()["results"]
        assert len(results_b) >= 1

        # Index reuse should be nearly instant (no Vineflower run)
        assert index_time < 2.0, (
            f"Index build took {index_time:.3f}s — expected instant (cached)"
        )
