"""End-to-end workflow tests and error case validation."""

import io
import time
import zipfile

from conftest import (
    decompile_class,
    poll_index_until,
    poll_status_until,
    upload_jar,
)


# ── Happy-path workflows ────────────────────────────────────────────────


class TestUploadTreeDecompile:
    """Primary user flow: upload → tree → decompile classes."""

    def test_upload_returns_202(self, session, base_url, jar_paths):
        job_id = upload_jar(session, base_url, jar_paths["java8"])
        assert len(job_id) == 32  # uuid4 hex

    def test_tree_structure(self, session, base_url, jar_paths):
        job_id = upload_jar(session, base_url, jar_paths["java8"])
        resp = session.get(f"{base_url}/api/tree/{job_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["jar_name"] == "java8-fixtures.jar"
        assert data["class_count"] >= 2
        assert "tree" in data

    def test_decompile_single_class(self, session, base_url, jar_paths, clean_cache):
        job_id = upload_jar(session, base_url, jar_paths["java8"])
        source, cached = decompile_class(
            session, base_url, job_id, "com/test/java8/StreamDemo.class",
        )
        assert "StreamDemo" in source
        assert "getUpperNames" in source
        assert cached is False

    def test_decompile_second_call_is_cached(self, session, base_url, jar_paths, clean_cache):
        job_id = upload_jar(session, base_url, jar_paths["java8"])
        source1, cached1 = decompile_class(
            session, base_url, job_id, "com/test/java8/StreamDemo.class",
        )
        source2, cached2 = decompile_class(
            session, base_url, job_id, "com/test/java8/StreamDemo.class",
        )
        assert cached1 is False
        assert cached2 is True
        assert source1 == source2


class TestFullDecompileZip:
    """Build ZIP flow: start-decompile → poll → download."""

    def test_start_decompile_and_download_zip(self, session, base_url, jar_paths):
        job_id = upload_jar(session, base_url, jar_paths["java11"])

        # Start full decompilation (retry once if pool is temporarily saturated)
        resp = session.post(f"{base_url}/api/start-decompile/{job_id}")
        if resp.status_code == 503:
            time.sleep(5)
            resp = session.post(f"{base_url}/api/start-decompile/{job_id}")
        assert resp.status_code == 202

        # Poll until done
        status = poll_status_until(session, base_url, job_id)
        assert status["progress"] == 100
        assert "Done" in status["message"]

        # Download ZIP
        resp = session.get(f"{base_url}/api/download/{job_id}")
        assert resp.status_code == 200

        # Verify ZIP contents
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            names = zf.namelist()
            java_files = [n for n in names if n.endswith(".java")]
            assert len(java_files) >= 2
            var_demo = [n for n in java_files if "VarDemo.java" in n]
            assert len(var_demo) == 1
            content = zf.read(var_demo[0]).decode("utf-8")
            assert "class VarDemo" in content


class TestBuildIndexAndSearch:
    """Index flow: build-index → poll → search."""

    def test_build_index_and_search_methods(self, session, base_url, jar_paths, clean_cache):
        job_id = upload_jar(session, base_url, jar_paths["java17"])

        # Build index
        resp = session.post(f"{base_url}/api/build-index/{job_id}")
        assert resp.status_code == 202

        # Poll until done
        poll_index_until(session, base_url, job_id)

        # Search for "distance" method
        resp = session.get(
            f"{base_url}/api/search-methods/{job_id}", params={"q": "distance"},
        )
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) >= 1
        assert any(r["method"] == "distance" for r in results)

    def test_search_for_area(self, session, base_url, jar_paths):
        job_id = upload_jar(session, base_url, jar_paths["java17"])
        resp = session.post(f"{base_url}/api/build-index/{job_id}")
        poll_index_until(session, base_url, job_id)

        resp = session.get(
            f"{base_url}/api/search-methods/{job_id}", params={"q": "area"},
        )
        results = resp.json()["results"]
        assert len(results) >= 1

    def test_short_query_returns_empty(self, session, base_url, jar_paths):
        job_id = upload_jar(session, base_url, jar_paths["java17"])
        resp = session.post(f"{base_url}/api/build-index/{job_id}")
        poll_index_until(session, base_url, job_id)

        resp = session.get(
            f"{base_url}/api/search-methods/{job_id}", params={"q": "a"},
        )
        assert resp.json()["results"] == []


# ── Error cases ──────────────────────────────────────────────────────────


class TestErrorCases:

    def test_nonexistent_job_status(self, session, base_url):
        resp = session.get(f"{base_url}/api/status/nonexistent_id")
        assert resp.status_code == 404

    def test_nonexistent_job_tree(self, session, base_url):
        resp = session.get(f"{base_url}/api/tree/nonexistent_id")
        assert resp.status_code == 404

    def test_nonexistent_job_decompile(self, session, base_url):
        resp = session.post(
            f"{base_url}/api/decompile-class/nonexistent_id",
            json={"class_path": "com/Foo.class"},
        )
        assert resp.status_code == 404

    def test_nonexistent_job_download(self, session, base_url):
        resp = session.get(f"{base_url}/api/download/nonexistent_id")
        assert resp.status_code == 404

    def test_upload_non_jar_returns_400(self, session, base_url):
        resp = session.post(
            f"{base_url}/api/upload",
            files={"jar": ("test.txt", b"hello", "text/plain")},
        )
        assert resp.status_code == 400
        assert "Only .jar" in resp.json()["error"]

    def test_upload_no_file_returns_400(self, session, base_url):
        resp = session.post(f"{base_url}/api/upload")
        assert resp.status_code == 400

    def test_decompile_invalid_class_path(self, session, base_url, jar_paths):
        job_id = upload_jar(session, base_url, jar_paths["java8"])
        resp = session.post(
            f"{base_url}/api/decompile-class/{job_id}",
            json={"class_path": "NotAClass.txt"},
        )
        assert resp.status_code == 400

    def test_decompile_path_traversal_rejected(self, session, base_url, jar_paths):
        job_id = upload_jar(session, base_url, jar_paths["java8"])
        resp = session.post(
            f"{base_url}/api/decompile-class/{job_id}",
            json={"class_path": "../../etc/passwd.class"},
        )
        assert resp.status_code == 400

    def test_decompile_nonexistent_class(self, session, base_url, jar_paths):
        job_id = upload_jar(session, base_url, jar_paths["java8"])
        resp = session.post(
            f"{base_url}/api/decompile-class/{job_id}",
            json={"class_path": "com/test/DoesNotExist.class"},
        )
        assert resp.status_code == 404

    def test_start_decompile_twice_returns_400(self, session, base_url, jar_paths):
        job_id = upload_jar(session, base_url, jar_paths["java8"])
        resp1 = session.post(f"{base_url}/api/start-decompile/{job_id}")
        if resp1.status_code == 503:
            time.sleep(5)
            resp1 = session.post(f"{base_url}/api/start-decompile/{job_id}")
        assert resp1.status_code == 202
        resp2 = session.post(f"{base_url}/api/start-decompile/{job_id}")
        assert resp2.status_code == 400

    def test_download_before_done_returns_400(self, session, base_url, jar_paths):
        job_id = upload_jar(session, base_url, jar_paths["java8"])
        resp = session.get(f"{base_url}/api/download/{job_id}")
        assert resp.status_code == 400

    def test_search_before_index_returns_400(self, session, base_url, jar_paths):
        job_id = upload_jar(session, base_url, jar_paths["java8"])
        resp = session.get(
            f"{base_url}/api/search-methods/{job_id}", params={"q": "test"},
        )
        assert resp.status_code == 400
