"""
Scenario 01: Single pod on a single-node K8s cluster.

Tests basic functionality — upload, tree, decompile, cache, index, search,
full decompile + ZIP download, and error handling.

Prerequisites:
  - minikube running with the app deployed (1 replica)
  - kubectl port-forward svc/jar-decompiler-svc 8443:443 -n jar-decompiler
  - Fixture JARs built: tests/fixtures/build_jars.sh

Run:
  K8S_BASE_URL=https://localhost:8443 pytest tests/k8s/test_scenario01_single_pod.py -v
"""
import pytest
from conftest import upload_jar, decompile_class, wait_for_index, wait_for_decompile


class TestUploadAndTree:
    def test_upload_returns_202(self, session, base_url, jar_paths):
        with open(jar_paths["java8"], "rb") as f:
            r = session.post(
                f"{base_url}/api/upload",
                files={"jar": ("java8.jar", f, "application/java-archive")},
            )
        assert r.status_code == 202
        assert "job_id" in r.json()

    def test_tree_returns_classes(self, session, base_url, jar_paths):
        job_id = upload_jar(session, base_url, jar_paths["java8"])
        r = session.get(f"{base_url}/api/tree/{job_id}")
        assert r.status_code == 200
        data = r.json()
        assert data["class_count"] > 0
        assert "tree" in data

    def test_tree_invalid_job_returns_404(self, session, base_url):
        r = session.get(f"{base_url}/api/tree/nonexistent-job-id")
        assert r.status_code == 404


class TestDecompile:
    def test_decompile_single_class(self, session, base_url, jar_paths):
        job_id = upload_jar(session, base_url, jar_paths["java8"])
        r = decompile_class(session, base_url, job_id, "com/test/java8/StreamDemo.class")
        assert r.status_code == 200
        data = r.json()
        assert "source" in data
        assert "StreamDemo" in data["source"]
        assert len(data["source"]) > 50

    def test_second_call_is_cached(self, session, base_url, jar_paths):
        job_id = upload_jar(session, base_url, jar_paths["java8"])
        # First call
        decompile_class(session, base_url, job_id, "com/test/java8/StreamDemo.class")
        # Second call
        r = decompile_class(session, base_url, job_id, "com/test/java8/StreamDemo.class")
        data = r.json()
        assert data.get("cached") is True

    def test_decompile_invalid_class(self, session, base_url, jar_paths):
        job_id = upload_jar(session, base_url, jar_paths["java8"])
        r = decompile_class(session, base_url, job_id, "nonexistent/Foo.class")
        assert r.status_code in (400, 404, 500)

    def test_decompile_invalid_job(self, session, base_url):
        r = decompile_class(session, base_url, "bad-job-id", "com/Foo.class")
        assert r.status_code == 404


class TestIndexAndSearch:
    def test_build_index(self, session, base_url, jar_paths):
        job_id = upload_jar(session, base_url, jar_paths["java8"])
        r = session.post(f"{base_url}/api/build-index/{job_id}")
        assert r.status_code in (200, 202)

    def test_index_completes(self, session, base_url, jar_paths):
        job_id = upload_jar(session, base_url, jar_paths["java8"])
        session.post(f"{base_url}/api/build-index/{job_id}")
        assert wait_for_index(session, base_url, job_id, timeout=30)

    def test_search_after_index(self, session, base_url, jar_paths):
        job_id = upload_jar(session, base_url, jar_paths["java8"])
        session.post(f"{base_url}/api/build-index/{job_id}")
        wait_for_index(session, base_url, job_id)
        r = session.get(f"{base_url}/api/search-methods/{job_id}?q=StreamDemo")
        assert r.status_code == 200


class TestFullDecompileAndZip:
    def test_start_decompile(self, session, base_url, jar_paths):
        job_id = upload_jar(session, base_url, jar_paths["java8"])
        r = session.post(f"{base_url}/api/start-decompile/{job_id}")
        assert r.status_code in (200, 202)

    def test_full_decompile_completes(self, session, base_url, jar_paths):
        job_id = upload_jar(session, base_url, jar_paths["java8"])
        session.post(f"{base_url}/api/start-decompile/{job_id}")
        assert wait_for_decompile(session, base_url, job_id, timeout=60)

    def test_zip_download(self, session, base_url, jar_paths):
        job_id = upload_jar(session, base_url, jar_paths["java8"])
        session.post(f"{base_url}/api/start-decompile/{job_id}")
        wait_for_decompile(session, base_url, job_id)
        r = session.get(f"{base_url}/api/download/{job_id}")
        assert r.status_code == 200
        assert len(r.content) > 100
        # ZIP files start with PK magic bytes
        assert r.content[:2] == b"PK"


class TestMultiVersionDecompilation:
    @pytest.mark.parametrize("version,class_path,expected_keyword", [
        ("java8", "com/test/java8/StreamDemo.class", "StreamDemo"),
        ("java8", "com/test/java8/LambdaHolder.class", "LambdaHolder"),
        ("java11", "com/test/java11/VarDemo.class", "VarDemo"),
        ("java17", "com/test/java17/PointRecord.class", "PointRecord"),
        ("java17", "com/test/java17/ShapeHierarchy.class", "ShapeHierarchy"),
        ("java21", "com/test/java21/ModernPatterns.class", "ModernPatterns"),
    ])
    def test_decompile_version(self, session, base_url, jar_paths,
                                version, class_path, expected_keyword):
        job_id = upload_jar(session, base_url, jar_paths[version])
        r = decompile_class(session, base_url, job_id, class_path)
        assert r.status_code == 200
        data = r.json()
        assert expected_keyword in data.get("source", ""), \
            f"Expected '{expected_keyword}' in decompiled source"
