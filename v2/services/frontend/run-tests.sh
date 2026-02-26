#!/bin/bash
# Test runner script for local E2E testing
# Usage: ./run-tests.sh [options]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}Starting ChampIQ V2 E2E Tests${NC}"

# Check if services are running
check_service() {
    local url=$1
    local name=$2
    if curl -s -o /dev/null -w "%{http_code}" "$url" | grep -q "200\|301\|302"; then
        echo -e "${GREEN}✓${NC} $name is running"
        return 0
    else
        echo -e "${RED}✗${NC} $name is NOT running"
        return 1
    fi
}

# Check prerequisites
echo -e "\n${YELLOW}Checking prerequisites...${NC}"

# Check Node.js
if command -v node &> /dev/null; then
    echo -e "${GREEN}✓${NC} Node.js: $(node --version)"
else
    echo -e "${RED}✗${NC} Node.js not found"
    exit 1
fi

# Check Chrome
if command -v google-chrome &> /dev/null; then
    echo -e "${GREEN}✓${NC} Google Chrome: $(google-chrome --version)"
elif command -v chromium &> /dev/null; then
    echo -e "${GREEN}✓${NC} Chromium found"
else
    echo -e "${RED}✗${NC} No Chrome/Chromium found"
    exit 1
fi

# Check services (optional - tests will warn if not running)
echo -e "\n${YELLOW}Checking services...${NC}"
check_service "http://localhost:3001" "Frontend" || true
check_service "http://localhost:4001" "Gateway" || true

# Install dependencies if needed
if [ ! -d "node_modules" ]; then
    echo -e "\n${YELLOW}Installing dependencies...${NC}"
    npm install
fi

# Parse command line arguments
TEST_ARGS="${@:-e2e}"

echo -e "\n${GREEN}Running tests...${NC}"
echo -e "Test args: $TEST_ARGS\n"

# Run tests
if npx playwright test $TEST_ARGS; then
    echo -e "\n${GREEN}✓ All tests passed!${NC}"
    exit 0
else
    echo -e "\n${RED}✗ Some tests failed${NC}"
    exit 1
fi
