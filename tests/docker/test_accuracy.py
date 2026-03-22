"""Decompilation accuracy tests — semantic checks against known source code."""

import pytest

from conftest import decompile_class, upload_jar

# Expected semantic elements per class. The decompiler may rename local
# variables or rewrite syntactic sugar, but class names, method signatures,
# field names, and key API calls must survive decompilation.
EXPECTED = {
    "java8": {
        "com/test/java8/StreamDemo.class": {
            "class_name": "StreamDemo",
            "methods": ["getUpperNames", "sumLengths"],
            "fields": ["names"],
            "patterns": ["stream()", "filter(", "map(", "collect(", "Function"],
        },
        "com/test/java8/LambdaHolder.class": {
            "class_name": "LambdaHolder",
            "methods": ["apply"],
            "fields": ["BY_LENGTH"],
            "patterns": ["Transformer", "Comparator"],
        },
    },
    "java11": {
        "com/test/java11/VarDemo.class": {
            "class_name": "VarDemo",
            "methods": ["processText"],
            "fields": [],
            "patterns": ["strip()", "repeat(", "isBlank()", "collect("],
        },
        "com/test/java11/HttpExample.class": {
            "class_name": "HttpExample",
            "methods": ["findValue", "orDefault"],
            "fields": [],
            "patterns": ["Optional"],
        },
    },
    "java17": {
        "com/test/java17/PointRecord.class": {
            "class_name": "PointRecord",
            "methods": ["distance"],
            "fields": ["x", "y"],
            "patterns": ["Math.sqrt"],
        },
        "com/test/java17/ShapeHierarchy.class": {
            "class_name": "ShapeHierarchy",
            "methods": ["describe"],
            "fields": [],
            "patterns": ["Circle", "Rect", "instanceof"],
        },
    },
    "java21": {
        "com/test/java21/ModernPatterns.class": {
            "class_name": "ModernPatterns",
            "methods": ["categorize", "firstKey"],
            "fields": [],
            "patterns": ["switch", "firstEntry"],
        },
        "com/test/java21/VirtualThreadDemo.class": {
            "class_name": "VirtualThreadDemo",
            "methods": ["runTasks"],
            "fields": [],
            "patterns": ["newVirtualThreadPerTaskExecutor", "ExecutorService"],
        },
    },
}


def _flatten_params():
    """Flatten EXPECTED into pytest parametrize tuples."""
    params = []
    for version, classes in EXPECTED.items():
        for class_path, checks in classes.items():
            test_id = f"{version}/{class_path.rsplit('/', 1)[-1]}"
            params.append(pytest.param(version, class_path, checks, id=test_id))
    return params


@pytest.mark.parametrize("version,class_path,checks", _flatten_params())
class TestDecompileAccuracy:

    def test_class_name_present(self, session, base_url, jar_paths,
                                version, class_path, checks):
        job_id = upload_jar(session, base_url, jar_paths[version])
        source, _ = decompile_class(session, base_url, job_id, class_path)
        assert checks["class_name"] in source, (
            f"Class name '{checks['class_name']}' not found in decompiled source"
        )

    def test_methods_present(self, session, base_url, jar_paths,
                             version, class_path, checks):
        job_id = upload_jar(session, base_url, jar_paths[version])
        source, _ = decompile_class(session, base_url, job_id, class_path)
        for method in checks["methods"]:
            assert method in source, (
                f"Method '{method}' not found in decompiled {class_path}"
            )

    def test_fields_present(self, session, base_url, jar_paths,
                            version, class_path, checks):
        if not checks["fields"]:
            pytest.skip("No fields to check")
        job_id = upload_jar(session, base_url, jar_paths[version])
        source, _ = decompile_class(session, base_url, job_id, class_path)
        for field in checks["fields"]:
            assert field in source, (
                f"Field '{field}' not found in decompiled {class_path}"
            )

    def test_patterns_present(self, session, base_url, jar_paths,
                              version, class_path, checks):
        job_id = upload_jar(session, base_url, jar_paths[version])
        source, _ = decompile_class(session, base_url, job_id, class_path)
        for pattern in checks["patterns"]:
            assert pattern in source, (
                f"Pattern '{pattern}' not found in decompiled {class_path}"
            )
