"""
Scenario 02: HPA auto-scaling under load.

Generates sustained load to push CPU above the HPA threshold (60%),
verifies that new pods are spawned, then stops load and verifies
pods are terminated as usage drops.

Prerequisites:
  - minikube running with metrics-server addon
  - HPA applied: kubectl apply -f k8s/hpa.yaml
  - kubectl port-forward svc/jar-decompiler-svc 8443:443 -n jar-decompiler
  - Fixture JARs built: tests/fixtures/build_jars.sh

Run:
  K8S_BASE_URL=https://localhost:8443 pytest tests/k8s/test_scenario02_hpa_scaling.py -v -s
"""
import os
import json
import time
import threading
import subprocess
import pytest
import requests
import urllib3

urllib3.disable_warnings()

BASE_URL = os.environ.get("K8S_BASE_URL", "https://localhost:8443")
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures", "jars")
NAMESPACE = os.environ.get("K8S_NAMESPACE", "jar-decompiler")

# Load test parameters
LOAD_THREADS = int(os.environ.get("LOAD_THREADS", "8"))
LOAD_DURATION = int(os.environ.get("LOAD_DURATION", "90"))
SCALE_UP_WAIT = int(os.environ.get("SCALE_UP_WAIT", "120"))
SCALE_DOWN_WAIT = int(os.environ.get("SCALE_DOWN_WAIT", "240"))


def kubectl(*args):
    """Run a kubectl command and return stdout."""
    cmd = ["kubectl", "-n", NAMESPACE] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return result.stdout.strip()


def get_pod_count():
    """Return the number of jar-decompiler pods."""
    output = kubectl("get", "pods", "-l", "app.kubernetes.io/name=jar-decompiler",
                     "--no-headers")
    if not output:
        return 0
    return len([line for line in output.split("\n") if line.strip()])


def get_hpa_cpu():
    """Return current CPU utilization from HPA (as string like '45%' or '<unknown>')."""
    output = kubectl("get", "hpa", "jar-decompiler-hpa",
                     "-o", "jsonpath={.status.currentMetrics[?(@.resource.name=='cpu')].resource.current.averageUtilization}")
    return output


class TestHPAScaling:
    """Test that HPA scales pods up under load and back down when load stops."""

    def test_initial_state(self):
        """Verify we start with the expected number of pods."""
        count = get_pod_count()
        assert count >= 1, f"Expected at least 1 pod, got {count}"
        print(f"\n  Initial pod count: {count}")

    def test_scale_up_under_load(self):
        """Generate load and verify HPA creates additional pods."""
        initial_count = get_pod_count()
        print(f"\n  Initial pods: {initial_count}")

        # Start load generator
        stop_event = threading.Event()
        cycle_count = {"value": 0}
        lock = threading.Lock()

        def load_worker():
            s = requests.Session()
            s.verify = False
            jar_path = os.path.join(FIXTURES_DIR, "java8-fixtures.jar")
            while not stop_event.is_set():
                try:
                    with open(jar_path, "rb") as f:
                        r = s.post(f"{BASE_URL}/api/upload",
                                   files={"jar": ("load.jar", f)})
                    if r.status_code != 202:
                        continue
                    job_id = r.json()["job_id"]

                    # Decompile classes (triggers JVM work)
                    for cls in ["com/test/java8/StreamDemo.class",
                                "com/test/java8/LambdaHolder.class"]:
                        s.post(f"{BASE_URL}/api/decompile-class/{job_id}",
                               json={"class_path": cls})

                    # Full decompile (heavy JVM)
                    s.post(f"{BASE_URL}/api/start-decompile/{job_id}")

                    # Build index
                    s.post(f"{BASE_URL}/api/build-index/{job_id}")

                    with lock:
                        cycle_count["value"] += 1
                except Exception:
                    pass

        print(f"  Starting {LOAD_THREADS} load threads for {LOAD_DURATION}s...")
        threads = []
        for _ in range(LOAD_THREADS):
            t = threading.Thread(target=load_worker, daemon=True)
            t.start()
            threads.append(t)

        # Run load for the configured duration
        time.sleep(LOAD_DURATION)

        # Stop load
        stop_event.set()
        for t in threads:
            t.join(timeout=10)
        print(f"  Load stopped. Completed {cycle_count['value']} cycles.")

        # Check if pods scaled up
        # HPA may take up to 30s to react + time to start pods
        max_pods_seen = initial_count
        print(f"  Waiting up to {SCALE_UP_WAIT}s for scale-up...")
        deadline = time.time() + SCALE_UP_WAIT
        while time.time() < deadline:
            count = get_pod_count()
            max_pods_seen = max(max_pods_seen, count)
            cpu = get_hpa_cpu()
            print(f"    Pods: {count}, CPU: {cpu}%")
            if count > initial_count:
                print(f"  Scale-up detected! {initial_count} → {count}")
                break
            time.sleep(15)

        assert max_pods_seen > initial_count, \
            f"HPA did not scale up. Max pods seen: {max_pods_seen}, initial: {initial_count}"
        print(f"  PASS: Scaled from {initial_count} to {max_pods_seen} pods")

    def test_scale_down_after_load(self):
        """After load stops, verify HPA removes excess pods."""
        current_count = get_pod_count()
        if current_count <= 1:
            pytest.skip("Only 1 pod running — scale-down not applicable")

        print(f"\n  Current pods: {current_count}")
        print(f"  Waiting up to {SCALE_DOWN_WAIT}s for scale-down...")

        min_pods_seen = current_count
        deadline = time.time() + SCALE_DOWN_WAIT
        while time.time() < deadline:
            count = get_pod_count()
            min_pods_seen = min(min_pods_seen, count)
            cpu = get_hpa_cpu()
            print(f"    Pods: {count}, CPU: {cpu}%")
            if count < current_count:
                print(f"  Scale-down detected! {current_count} → {count}")
                break
            time.sleep(30)

        assert min_pods_seen < current_count, \
            f"HPA did not scale down. Min pods seen: {min_pods_seen}, was: {current_count}"
        print(f"  PASS: Scaled down from {current_count} to {min_pods_seen} pods")


class TestHPAConfiguration:
    """Verify HPA is configured correctly."""

    def test_hpa_exists(self):
        output = kubectl("get", "hpa", "jar-decompiler-hpa", "--no-headers")
        assert "jar-decompiler-hpa" in output, "HPA not found"

    def test_hpa_targets_deployment(self):
        output = kubectl("get", "hpa", "jar-decompiler-hpa",
                         "-o", "jsonpath={.spec.scaleTargetRef.name}")
        assert output == "jar-decompiler"

    def test_hpa_metrics_available(self):
        """Verify metrics-server is reporting CPU/memory."""
        output = kubectl("top", "pod", "-l", "app.kubernetes.io/name=jar-decompiler",
                         "--no-headers")
        assert output, "No metrics available — is metrics-server addon enabled?"
        print(f"\n  Pod metrics:\n  {output}")
