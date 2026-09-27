#!/usr/bin/env bash
# Rare/one-off: build the zip once and run Terraform. For routine code-only
# deploys after the stack already exists, use deploy_code.sh instead.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

"${ROOT_DIR}/scripts/build_lambda_package.sh"

cd "${ROOT_DIR}/infrastructure"
terraform init
terraform plan
read -r -p "Apply the plan above? [y/N] " confirm
if [[ "${confirm}" =~ ^[Yy]$ ]]; then
  terraform apply
else
  echo "Aborted."
fi
