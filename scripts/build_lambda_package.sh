#!/usr/bin/env bash
# Builds build/lambda.zip: application code + runtime dependencies,
# targeting the Lambda runtime's platform explicitly so wheels with
# native extensions (e.g. cryptography, used by PyJWT[crypto]) match the
# Lambda execution environment rather than the build machine.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_VERSION="3.12"
PLATFORM="manylinux2014_aarch64" # matches infrastructure/variables.tf lambda_architecture default (arm64)

rm -rf build
mkdir -p build/package

echo "Installing runtime dependencies for ${PLATFORM} / python${PYTHON_VERSION}..."
# boto3 is preinstalled in the Lambda Python runtime - excluding it keeps
# the zip small. Everything else the app imports at runtime must be here.
pip install \
  --platform "${PLATFORM}" \
  --implementation cp \
  --python-version "${PYTHON_VERSION}" \
  --only-binary=:all: \
  --target build/package \
  flask apig-wsgi "pyjwt[crypto]" requests

echo "Copying application code..."
cp -r app build/package/app
find build/package/app -name "__pycache__" -type d -exec rm -rf {} +

echo "Zipping..."
(cd build/package && zip -q -r ../lambda.zip .)

echo "Built build/lambda.zip ($(du -h build/lambda.zip | cut -f1))"
