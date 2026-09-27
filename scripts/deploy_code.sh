#!/usr/bin/env bash
# Fast path for routine code changes: rebuild the zip and push it directly
# via the Lambda API, bypassing `terraform apply` entirely. Mirrors the
# quote-lambda-tf-backend reference's deploy pattern (update-function-code
# -> publish-version -> update-alias "live", which API Gateway invokes).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FUNCTION_NAME="${LAMBDA_FUNCTION_NAME:-quote-aws-lambda-python}"
ALIAS_NAME="live"

"${ROOT_DIR}/scripts/build_lambda_package.sh"

echo "Updating function code for ${FUNCTION_NAME}..."
aws lambda update-function-code \
  --function-name "${FUNCTION_NAME}" \
  --zip-file "fileb://${ROOT_DIR}/build/lambda.zip" \
  >/dev/null

aws lambda wait function-updated --function-name "${FUNCTION_NAME}"

echo "Publishing new version..."
VERSION=$(aws lambda publish-version --function-name "${FUNCTION_NAME}" --query Version --output text)
echo "Published version ${VERSION}"

echo "Pointing alias '${ALIAS_NAME}' at version ${VERSION}..."
aws lambda update-alias \
  --function-name "${FUNCTION_NAME}" \
  --name "${ALIAS_NAME}" \
  --function-version "${VERSION}" \
  >/dev/null

echo "Done. ${FUNCTION_NAME}:${ALIAS_NAME} -> version ${VERSION}"
