#!/bin/bash
set -e

# Build and Push Docker Image for sumii-mobile-api with Semantic Versioning
# Usage: ./scripts/build-and-push.sh [patch|minor|major]
# Default: patch

REGION="eu-central-1"
ACCOUNT_ID="437799327678"
REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
IMAGE_NAME="sumii-mobile-api"

# Get script directory (sumii-mobile-api root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VERSION_FILE="${PROJECT_ROOT}/VERSION"

cd "${PROJECT_ROOT}"

# Determine bump type (patch, minor, major)
BUMP_TYPE="${1:-patch}"
if [[ ! "$BUMP_TYPE" =~ ^(patch|minor|major)$ ]]; then
  echo "❌ Error: Invalid bump type '$BUMP_TYPE'. Use: patch, minor, or major"
  exit 1
fi

# Read current version from VERSION file
if [[ ! -f "${VERSION_FILE}" ]]; then
  echo "❌ Error: VERSION file not found at ${VERSION_FILE}"
  exit 1
fi

CURRENT_VERSION=$(cat "${VERSION_FILE}" | tr -d '[:space:]')
echo "📋 Current version: ${CURRENT_VERSION}"

# Parse version components
IFS='.' read -ra VERSION_PARTS <<< "${CURRENT_VERSION}"
MAJOR="${VERSION_PARTS[0]}"
MINOR="${VERSION_PARTS[1]}"
PATCH="${VERSION_PARTS[2]}"

# Bump version based on type
case "$BUMP_TYPE" in
  patch)
    PATCH=$((PATCH + 1))
    ;;
  minor)
    MINOR=$((MINOR + 1))
    PATCH=0
    ;;
  major)
    MAJOR=$((MAJOR + 1))
    MINOR=0
    PATCH=0
    ;;
esac

NEW_VERSION="${MAJOR}.${MINOR}.${PATCH}"
IMAGE_TAG="v${NEW_VERSION}"

echo "🚀 Bumping ${BUMP_TYPE} version: ${CURRENT_VERSION} → ${NEW_VERSION}"
echo "🏷️  Image tag: ${IMAGE_TAG}"

# Update VERSION file
echo "📝 Updating VERSION file..."
echo "${NEW_VERSION}" > "${VERSION_FILE}"
echo "✅ Updated VERSION file to ${NEW_VERSION}"

# Authenticate with ECR
echo "🔐 Authenticating with ECR..."
aws ecr get-login-password --region ${REGION} | \
  docker login --username AWS --password-stdin ${REGISTRY}

# Build Docker image
echo "📦 Building ${IMAGE_NAME} (linux/amd64)..."
docker build --platform linux/amd64 -t ${IMAGE_NAME}:latest .

# Tag image with sem-ver
echo "🏷️  Tagging image as ${IMAGE_TAG}..."
docker tag ${IMAGE_NAME}:latest ${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}

# Push to ECR
echo "📤 Pushing image to ECR..."
docker push ${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}

echo "✅ Image pushed successfully!"
echo "📝 Version: ${NEW_VERSION}"
echo "🏷️  Image tag: ${IMAGE_TAG}"
echo ""
echo "💡 Next steps:"
echo "   1. Update Terraform: cd infrastructure && terraform apply -var='image_tag=${IMAGE_TAG}'"
echo "   2. Commit changes: git add VERSION && git commit -m 'chore: bump version to ${NEW_VERSION}'"
