# ChampIQ V2 - End-to-End Testing Guide

## Overview

This directory contains Playwright-based E2E tests for ChampIQ V2. The tests cover the complete user flow from registration through prospect management.

## Test Coverage

### Authentication Tests
- User Registration
- User Login
- Form Validation
- Protected Route Access

### Dashboard Tests
- Dashboard Loading
- Stats Display
- Empty State
- Navigation

### Prospect Management Tests
- Create Prospect (Full Form)
- Create Prospect (Required Fields Only)
- Prospect Validation
- Prospect Detail View
- Dashboard Prospect List

### Settings Tests
- Settings Page Access
- Settings Form Display

### Complete E2E Flow
- Full user journey test combining all features

## Prerequisites

1. **Node.js 20+** installed
2. **Google Chrome** or **Chromium** browser
3. **Services Running**:
   - Frontend: `http://localhost:3001`
   - Gateway: `http://localhost:4001`
   - PostgreSQL, Redis, Neo4j (via docker-compose)

## Quick Start

### 1. Install Dependencies

```bash
cd v2/services/frontend
npm install
npx playwright install chromium
```

### 2. Start Services

```bash
# Start infrastructure services
cd v2 && docker compose -f docker-compose.v2.yml up -d redis postgres neo4j

# Start gateway
cd v2/services/gateway
npm run start:dev

# Start frontend (in another terminal)
cd v2/services/frontend
npm run dev
```

### 3. Run Tests

```bash
# Run all tests
npm run test:e2e

# Run with UI mode
npm run test:e2e:ui

# Run with visible browser
npm run test:e2e:headed

# Run specific test file
npx playwright test e2e/champaign-flow.spec.ts

# Run specific test by name
npx playwright test e2e/champaign-flow.spec.ts -g "User Registration"
```

## Running Tests in CI/CD

### GitHub Actions

The workflow file `.github/workflows/e2e-tests.yml` runs tests automatically on:

- Every push to any branch
- Every pull request to main/develop
- Manual trigger via workflow_dispatch

### Docker-based Testing

```bash
# Start test environment
docker compose -f docker-compose.test.yml up test-runner
```

## Test Configuration

See `playwright.config.ts` for configuration options:

- Base URL: `http://localhost:3001`
- Test directory: `./e2e`
- Browser: Chromium (Chrome channel)
- Trace: On first retry
- Screenshots: On failure only
- Video: On failure only

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| VITE_API_URL | http://localhost:4001 | API Gateway URL |
| CI | false | Running in CI mode |
| PLAYWRIGHT_BROWSERS_PATH | system default | Browser install path |

## Test Data

Tests use dynamic data with timestamps to avoid conflicts:

- **User Email**: `hemang.kashikar.{timestamp}@test.lakeb2b.com`
- **Prospect Email**: `lakeb2bdeveloper@gmail.com`
- **Phone**: +919098474926
- **Name**: Hemang Kashikar

## Debugging Failed Tests

### View Traces

```bash
npx playwright show-trace playwright-report/trace.zip
```

### View Screenshots

Screenshots are saved to `test-results/` on failure.

### Run Single Test

```bash
npx playwright test e2e/champaign-flow.spec.ts:40 --debug
```

## Common Issues

### Tests Timeout

- Check that all services are running
- Increase timeout in playwright.config.ts

### Authentication Fails

- Ensure database is running and migrated
- Check JWT_SECRET matches between services

### Port Already in Use

- Kill existing processes: `pkill -f vite`
- Change port in vite.config.ts

## Adding New Tests

1. Add test in `e2e/champaign-flow.spec.ts`
2. Follow naming convention: `describe('Feature', () => { test('should...', async () => {...}) })`
3. Use existing page objects and helpers
4. Add appropriate beforeEach/afterEach hooks

## Report Generation

Reports are generated in multiple formats:

- **HTML Report**: `playwright-report/index.html`
- **JUnit XML**: `playwright-report/results.xml`
- **Console Output**: Via `--reporter=list`

## Contact

For issues with E2E tests, check:
1. Service logs (gateway, frontend)
2. Playwright trace in `playwright-report/`
3. Screenshots in `test-results/`
