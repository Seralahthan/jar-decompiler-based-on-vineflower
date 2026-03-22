import re
import zipfile
from pathlib import Path


def build_tree(jar_path: Path) -> dict:
    """Parse a JAR's .class entries into a nested tree structure."""
    root: dict = {}
    class_count = 0
    resource_count = 0

    with zipfile.ZipFile(jar_path, "r") as zf:
        for entry in zf.namelist():
            if entry.endswith("/"):
                continue
            parts = entry.split("/")
            filename = parts[-1]
            if not filename:
                continue
            if not filename.endswith(".class"):
                resource_count += 1
                continue

            class_count += 1
            node = root
            for part in parts[:-1]:
                if part not in node:
                    node[part] = {"type": "package", "name": part, "children": {}}
                node = node[part]["children"]

            stem = filename[:-6]  # strip .class
            is_inner = "$" in stem
            is_anon = bool(re.search(r'\$\d+$', stem))
            node[filename] = {
                "type": "class",
                "name": filename,
                "path": entry,
                "isInner": is_inner,
                "isAnonymous": is_anon,
            }

    def dict_to_list(d: dict) -> list:
        packages, classes = [], []
        for name, val in sorted(d.items()):
            if val.get("type") == "package":
                packages.append({
                    "type": "package",
                    "name": name,
                    "children": dict_to_list(val["children"]),
                })
            else:
                classes.append(val)
        return packages + classes

    return {
        "tree": dict_to_list(root),
        "class_count": class_count,
        "resource_count": resource_count,
    }
