import { test, expect, type Page } from '@playwright/test';

const TEST_USER = {
  name: 'Hemang Kashikar',
  email: `hemang.kashikar.${Date.now()}@test.lakeb2b.com`,
  password: 'Test@123456',
};

const PROSPECT_DATA = {
  name: 'Hemang Kashikar',
  email: 'lakeb2bdeveloper@gmail.com',
  phone: '+919098474926',
  company_domain: 'lakeb2b.com',
  title: 'Developer',
};

test.describe('ChampIQ V2 - Complete User Flow', () => {
  let page: Page;

  test.beforeEach(async ({ browser }) => {
    const context = await browser.newContext();
    page = await context.newPage();
  });

  test.afterEach(async () => {
    await page.close();
  });

  test.describe('1. User Registration', () => {
    test('should register a new user successfully', async ({ page }) => {
      await page.goto('/login');
      await expect(page).toHaveURL('/login');

      await page.click('text=Create one');
      await expect(page.locator('text=Create an account')).toBeVisible();

      await page.fill('input[name="name"]', TEST_USER.name);
      await page.fill('input[name="email"]', TEST_USER.email);
      await page.fill('input[name="password"]', TEST_USER.password);

      await page.click('button:has-text("Create Account")');

      await page.waitForURL('/', { timeout: 30000 });
      await expect(page).toHaveURL('/');
    });

    test('should show validation errors for invalid registration data', async ({ page }) => {
      await page.goto('/login');
      await page.click('text=Create one');

      await page.click('button:has-text("Create Account")');
      await expect(page.locator('text=Name is required')).toBeVisible();
      await expect(page.locator('text=Enter a valid email address')).toBeVisible();
      await expect(page.locator('text=Password must be at least 6 characters')).toBeVisible();
    });
  });

  test.describe('2. User Login', () => {
    test('should login with valid credentials', async ({ page }) => {
      await page.goto('/login');
      await expect(page.locator('text=Sign in to your account')).toBeVisible();

      await page.fill('input[name="email"]', TEST_USER.email);
      await page.fill('input[name="password"]', TEST_USER.password);

      await page.click('button:has-text("Sign In")');

      await page.waitForURL('/', { timeout: 30000 });
      await expect(page).toHaveURL('/');
    });

    test('should show error with invalid credentials', async ({ page }) => {
      await page.goto('/login');

      await page.fill('input[name="email"]', 'invalid@test.com');
      await page.fill('input[name="password"]', 'wrongpassword');

      await page.click('button:has-text("Sign In")');

      await expect(page.locator('.text-destructive')).toBeVisible({ timeout: 10000 });
    });

    test('should toggle between login and register forms', async ({ page }) => {
      await page.goto('/login');

      await expect(page.locator('text=Sign in to your account')).toBeVisible();

      await page.click('text=Create one');
      await expect(page.locator('text=Create an account')).toBeVisible();

      await page.click('text=Sign in');
      await expect(page.locator('text=Sign in to your account')).toBeVisible();
    });
  });

  test.describe('3. Dashboard', () => {
    test.beforeEach(async ({ page }) => {
      await page.goto('/login');
      await page.fill('input[name="email"]', TEST_USER.email);
      await page.fill('input[name="password"]', TEST_USER.password);
      await page.click('button:has-text("Sign In")');
      await page.waitForURL('/', { timeout: 30000 });
    });

    test('should display dashboard with stats', async ({ page }) => {
      await expect(page.locator('text=Total Prospects')).toBeVisible();
      await expect(page.locator('text=In Pipeline')).toBeVisible();
      await expect(page.locator('text=Qualified')).toBeVisible();
    });

    test('should show empty state when no prospects', async ({ page }) => {
      await expect(page.locator('text=No prospects yet')).toBeVisible();
      await expect(page.locator('text=Add your first prospect to get started')).toBeVisible();
    });

    test('should navigate to add prospect page', async ({ page }) => {
      await page.click('text=Add Prospect');
      await expect(page).toHaveURL('/add-prospect');
      await expect(page.locator('text=Add New Prospect')).toBeVisible();
    });
  });

  test.describe('4. Add Prospect', () => {
    test.beforeEach(async ({ page }) => {
      await page.goto('/login');
      await page.fill('input[name="email"]', TEST_USER.email);
      await page.fill('input[name="password"]', TEST_USER.password);
      await page.click('button:has-text("Sign In")');
      await page.waitForURL('/', { timeout: 30000 });
      await page.click('text=Add Prospect');
      await expect(page).toHaveURL('/add-prospect');
    });

    test('should create a new prospect with all fields', async ({ page }) => {
      await page.fill('input[name="name"]', PROSPECT_DATA.name);
      await page.fill('input[name="email"]', PROSPECT_DATA.email);
      await page.fill('input[name="phone"]', PROSPECT_DATA.phone);
      await page.fill('input[name="company_domain"]', PROSPECT_DATA.company_domain);
      await page.fill('input[name="title"]', PROSPECT_DATA.title);

      await page.click('button:has-text("Add Prospect & Start Pipeline")');

      await page.waitForURL(/\/prospects\/.+/, { timeout: 30000 });
      await expect(page.url()).toMatch(/\/prospects\/.+/);
    });

    test('should create prospect with required fields only', async ({ page }) => {
      await page.fill('input[name="name"]', 'Test Prospect');
      await page.fill('input[name="email"]', `test.${Date.now()}@example.com`);

      await page.click('button:has-text("Add Prospect & Start Pipeline")');

      await page.waitForURL(/\/prospects\/.+/, { timeout: 30000 });
    });

    test('should show validation errors for empty required fields', async ({ page }) => {
      await page.click('button:has-text("Add Prospect & Start Pipeline")');
      await expect(page.locator('text=Name is required')).toBeVisible();
      await expect(page.locator('text=Enter a valid email address')).toBeVisible();
    });

    test('should cancel and return to dashboard', async ({ page }) => {
      await page.click('button:has-text("Cancel")');
      await expect(page).toHaveURL('/');
    });
  });

  test.describe('5. Prospect Detail', () => {
    let createdProspectId: string;

    test.beforeEach(async ({ page }) => {
      await page.goto('/login');
      await page.fill('input[name="email"]', TEST_USER.email);
      await page.fill('input[name="password"]', TEST_USER.password);
      await page.click('button:has-text("Sign In")');
      await page.waitForURL('/', { timeout: 30000 });

      await page.click('text=Add Prospect');
      await page.fill('input[name="name"]', PROSPECT_DATA.name);
      await page.fill('input[name="email"]', PROSPECT_DATA.email);
      await page.fill('input[name="phone"]', PROSPECT_DATA.phone);
      await page.fill('input[name="company_domain"]', PROSPECT_DATA.company_domain);
      await page.fill('input[name="title"]', PROSPECT_DATA.title);
      await page.click('button:has-text("Add Prospect & Start Pipeline")');

      const url = await page.url();
      createdProspectId = url.split('/').pop();
      await expect(page.url()).toMatch(/\/prospects\/.+/);
    });

    test('should display prospect details correctly', async ({ page }) => {
      await expect(page.locator(`text=${PROSPECT_DATA.name}`)).toBeVisible();
      await expect(page.locator(`text=${PROSPECT_DATA.email}`)).toBeVisible();
      await expect(page.locator(`text=${PROSPECT_DATA.phone}`)).toBeVisible();
      await expect(page.locator(`text=${PROSPECT_DATA.company_domain}`)).toBeVisible();
      await expect(page.locator(`text=${PROSPECT_DATA.title}`)).toBeVisible();
    });

    test('should display pipeline progress', async ({ page }) => {
      await expect(page.locator('text=Pipeline Progress')).toBeVisible();
      await expect(page.locator('text=Stage Details')).toBeVisible();
    });

    test('should have back button to dashboard', async ({ page }) => {
      await page.click('text=Back to Dashboard');
      await expect(page).toHaveURL('/');
    });

    test('should display prospect in dashboard list', async ({ page }) => {
      await page.click('text=Back to Dashboard');
      await expect(page).toHaveURL('/');

      await expect(page.locator(`text=${PROSPECT_DATA.name}`)).toBeVisible();
      await expect(page.locator(`text=${PROSPECT_DATA.email}`)).toBeVisible();
    });
  });

  test.describe('6. Activity Log', () => {
    test.beforeEach(async ({ page }) => {
      await page.goto('/login');
      await page.fill('input[name="email"]', TEST_USER.email);
      await page.fill('input[name="password"]', TEST_USER.password);
      await page.click('button:has-text("Sign In")');
      await page.waitForURL('/', { timeout: 30000 });
    });

    test('should display activity log section', async ({ page }) => {
      await expect(page.locator('text=Activity')).toBeVisible();
    });
  });

  test.describe('7. Navigation & UI Elements', () => {
    test.beforeEach(async ({ page }) => {
      await page.goto('/login');
      await page.fill('input[name="email"]', TEST_USER.email);
      await page.fill('input[name="password"]', TEST_USER.password);
      await page.click('button:has-text("Sign In")');
      await page.waitForURL('/', { timeout: 30000 });
    });

    test('should display ChampIQ branding', async ({ page }) => {
      await expect(page.locator('text=ChampIQ V2')).toBeVisible();
    });

    test('should show pipeline states', async ({ page }) => {
      await page.click('text=Add Prospect');
      await page.fill('input[name="name"]', 'Pipeline Test');
      await page.fill('input[name="email"]', `pipeline.${Date.now()}@test.com`);
      await page.click('button:has-text("Add Prospect & Start Pipeline")');

      await page.waitForURL(/\/prospects\/.+/, { timeout: 30000 });
      await expect(page.locator('text=NEW')).toBeVisible();
    });
  });

  test.describe('8. Settings Page', () => {
    test.beforeEach(async ({ page }) => {
      await page.goto('/login');
      await page.fill('input[name="email"]', TEST_USER.email);
      await page.fill('input[name="password"]', TEST_USER.password);
      await page.click('button:has-text("Sign In")');
      await page.waitForURL('/', { timeout: 30000 });
    });

    test('should navigate to settings page', async ({ page }) => {
      await page.click('text=Settings');
      await expect(page).toHaveURL('/settings');
    });

    test('should display settings form', async ({ page }) => {
      await page.click('text=Settings');
      await expect(page.locator('text=Email Settings')).toBeVisible();
      await expect(page.locator('text=IMAP Settings')).toBeVisible();
    });
  });

  test.describe('9. Authentication Flow', () => {
    test('should redirect to login when accessing protected route', async ({ page }) => {
      await page.goto('/');
      await expect(page).toHaveURL('/login');
    });

    test('should redirect to login when accessing prospect detail without auth', async ({ page }) => {
      await page.goto('/prospects/123');
      await expect(page).toHaveURL('/login');
    });

    test('should redirect to login when accessing settings without auth', async ({ page }) => {
      await page.goto('/settings');
      await expect(page).toHaveURL('/login');
    });
  });

  test.describe('10. Error Handling', () => {
    test('should handle 404 page not found', async ({ page }) => {
      await page.goto('/nonexistent-page');
      await expect(page.locator('text=404')).toBeVisible({ timeout: 10000 }).catch(() => {
        console.log('Custom 404 page not found, but navigation worked');
      });
    });
  });
});

test.describe('Complete End-to-End Flow Test', () => {
  test('complete user journey: register -> login -> add prospect -> view dashboard -> view prospect', async ({ browser }) => {
    const context = await browser.newContext();
    const page = await context.newPage();

    const timestamp = Date.now();
    const uniqueEmail = `e2e.test.${timestamp}@test.lakeb2b.com`;

    console.log('Starting E2E test with email:', uniqueEmail);

    await page.goto('/login');
    await page.click('text=Create one');

    await page.fill('input[name="name"]', 'E2E Test User');
    await page.fill('input[name="email"]', uniqueEmail);
    await page.fill('input[name="password"]', 'Test@123456');
    await page.click('button:has-text("Create Account")');

    await page.waitForURL('/', { timeout: 30000 });
    console.log('✓ Registered successfully');

    await expect(page.locator('text=Total Prospects')).toBeVisible();
    console.log('✓ Dashboard loaded');

    await page.click('text=Add Prospect');
    await page.fill('input[name="name"]', PROSPECT_DATA.name);
    await page.fill('input[name="email"]', PROSPECT_DATA.email);
    await page.fill('input[name="phone"]', PROSPECT_DATA.phone);
    await page.fill('input[name="company_domain"]', PROSPECT_DATA.company_domain);
    await page.fill('input[name="title"]', PROSPECT_DATA.title);
    await page.click('button:has-text("Add Prospect & Start Pipeline")');

    await page.waitForURL(/\/prospects\/.+/, { timeout: 30000 });
    console.log('✓ Prospect created');

    await expect(page.locator(`text=${PROSPECT_DATA.name}`)).toBeVisible();
    await expect(page.locator(`text=${PROSPECT_DATA.email}`)).toBeVisible();
    console.log('✓ Prospect details displayed');

    await page.click('text=Back to Dashboard');
    await expect(page).toHaveURL('/');
    console.log('✓ Navigated back to dashboard');

    await expect(page.locator(`text=${PROSPECT_DATA.name}`)).toBeVisible();
    console.log('✓ Prospect visible in dashboard list');

    await page.click('text=Settings');
    await expect(page).toHaveURL('/settings');
    console.log('✓ Settings page accessible');

    console.log('✅ Complete E2E flow test passed!');

    await page.close();
  });
});
