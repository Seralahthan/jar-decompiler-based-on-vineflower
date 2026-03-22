# K8s Integration Tests

## Prerequisites

1. **minikube** running with metrics-server addon:
   ```bash
   minikube start --driver=qemu --memory=8192 --cpus=4 --addons=metrics-server
   ```

2. **Deploy the app**:
   ```bash
   kubectl apply -f k8s/namespace.yaml
   kubectl apply -f k8s/redis-deployment.yaml -f k8s/redis-service.yaml
   kubectl apply -f k8s/app-deployment.yaml -f k8s/app-service.yaml
   kubectl apply -f k8s/hpa.yaml   # needed for Scenario 02
   ```

3. **Port-forward** (in a separate terminal):
   ```bash
   kubectl -n jar-decompiler port-forward svc/jar-decompiler-svc 8443:443
   ```

4. **Build fixture JARs** (one-time):
   ```bash
   cd tests/fixtures && ./build_jars.sh
   ```

5. **Install test dependencies**:
   ```bash
   pip install pytest requests urllib3
   ```

## Running Tests

### Scenario 01: Single Pod Functional Tests
```bash
pytest tests/k8s/test_scenario01_single_pod.py -v
```

### Scenario 02: HPA Auto-scaling
```bash
# Run with stdout visible (-s) to see scaling progress
pytest tests/k8s/test_scenario02_hpa_scaling.py -v -s
```

### Scenario 03: Full Suite (Dedup, Concurrency, Multi-version)
```bash
pytest tests/k8s/test_scenario03_full_suite.py -v
```

### Run All Scenarios
```bash
pytest tests/k8s/ -v -s
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `K8S_BASE_URL` | `https://localhost:8443` | App endpoint |
| `K8S_NAMESPACE` | `jar-decompiler` | K8s namespace |
| `LOAD_THREADS` | `8` | Threads for load generation (Scenario 02) |
| `LOAD_DURATION` | `90` | Load duration in seconds (Scenario 02) |
| `SCALE_UP_WAIT` | `120` | Max wait for scale-up (Scenario 02) |
| `SCALE_DOWN_WAIT` | `240` | Max wait for scale-down (Scenario 02) |

## Clean Up

```bash
kubectl delete namespace jar-decompiler
minikube stop
minikube delete   # removes VM entirely
```
