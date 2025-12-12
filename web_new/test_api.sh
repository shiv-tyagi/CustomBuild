#!/bin/bash
# Simple API test script

set -e

API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"

echo "Testing CustomBuild API at $API_BASE_URL"
echo "=========================================="
echo ""

# Test 1: Health check
echo "1. Testing health check..."
curl -s -f "$API_BASE_URL/health" | jq '.'
echo "✓ Health check passed"
echo ""

# Test 2: Root endpoint
echo "2. Testing root endpoint..."
curl -s -f "$API_BASE_URL/" | jq '.'
echo "✓ Root endpoint passed"
echo ""

# Test 3: API docs
echo "3. Testing API docs endpoint..."
curl -s -f -o /dev/null "$API_BASE_URL/docs"
echo "✓ API docs accessible"
echo ""

# Test 4: List vehicles
echo "4. Testing vehicles list..."
curl -s -f "$API_BASE_URL/api/v1/vehicles" | jq '. | length'
echo "✓ Vehicles list passed"
echo ""

# Test 5: List builds
echo "5. Testing builds list..."
curl -s -f "$API_BASE_URL/api/v1/builds?limit=5" | jq '. | length'
echo "✓ Builds list passed"
echo ""

echo "=========================================="
echo "All tests passed! ✓"
