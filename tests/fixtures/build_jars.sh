#!/usr/bin/env bash
# Compiles Java fixture sources into JARs using Docker containers with
# the appropriate JDK version. Output goes to tests/fixtures/jars/.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT_DIR="$SCRIPT_DIR/jars"
mkdir -p "$OUTPUT_DIR"

build_jar() {
    local version="$1"
    local jdk_image="$2"
    local jar_name="${version}-fixtures.jar"
    local src_dir="$SCRIPT_DIR/${version}/src"

    echo "Building $jar_name with $jdk_image ..."
    docker run --rm \
        -v "$src_dir:/src:ro" \
        -v "$OUTPUT_DIR:/out" \
        "$jdk_image" \
        bash -c "mkdir -p /build && javac -d /build \$(find /src -name '*.java') && cd /build && jar cf /out/$jar_name com/"

    echo "  -> $jar_name ($(du -h "$OUTPUT_DIR/$jar_name" | cut -f1))"
}

build_jar java8  eclipse-temurin:8-jdk
build_jar java11 eclipse-temurin:11-jdk
build_jar java17 eclipse-temurin:17-jdk
build_jar java21 eclipse-temurin:21-jdk

echo ""
echo "All JARs built successfully:"
ls -la "$OUTPUT_DIR"/*.jar
