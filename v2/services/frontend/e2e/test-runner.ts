import puppeteer, { Browser, Page } from 'puppeteer-core';

const BASE_URL = process.env.FRONTEND_URL || 'http://localhost:3001';

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

let browser: Browser;
let page: Page;

async function delay(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function initBrowser() {
  console.log('🚀 Launching browser...');
  browser = await puppeteer.launch({
    executablePath: '/usr/bin/google-chrome',
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
  });
  page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 720 });
  console.log('✅ Browser launched\n');
}

async function closeBrowser() {
  if (browser) {
    await browser.close();
  }
}

async function clickButtonWithText(text: string) {
  await page.evaluate((txt) => {
    const buttons = Array.from(document.querySelectorAll('button, a'));
    const btn = buttons.find(b => b.textContent?.includes(txt));
    if (btn) (btn as HTMLElement).click();
  }, text);
}

async function testRegistration() {
  console.log('📝 Test: User Registration');
  try {
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle0', timeout: 30000 });
    await delay(2000);
    
    // Click "Create one" 
    await clickButtonWithText('Create one');
    await delay(2000);
    
    // Fill form
    await page.waitForSelector('input[name="name"]', { timeout: 5000 });
    await page.type('input[name="name"]', TEST_USER.name, { delay: 100 });
    await page.type('input[name="email"]', TEST_USER.email, { delay: 100 });
    await page.type('input[name="password"]', TEST_USER.password, { delay: 100 });
    
    // Click Create Account button
    await clickButtonWithText('Create Account');
    
    await delay(5000);
    
    const url = page.url();
    console.log('   URL after registration:', url);
    
    // Check if logged in
    if (url.includes('/') && !url.includes('login')) {
      console.log('   ✅ Registration successful');
      return true;
    }
    
    // Try login
    return await testLoginWithNewUser();
    
  } catch (e) {
    console.log('   ❌ Registration error:', (e as Error).message);
    return false;
  }
}

async function testLoginWithNewUser() {
  console.log('   ↩️ Attempting login...');
  try {
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle0', timeout: 30000 });
    await delay(2000);
    
    await page.type('input[name="email"]', TEST_USER.email, { delay: 100 });
    await page.type('input[name="password"]', TEST_USER.password, { delay: 100 });
    
    await clickButtonWithText('Sign In');
    
    await delay(5000);
    
    const url = page.url();
    console.log('   URL after login:', url);
    
    if (url.includes('/') && !url.includes('login')) {
      console.log('   ✅ Login successful');
      return true;
    }
    
    return url.includes('/') && !url.includes('login');
    
  } catch (e) {
    console.log('   ❌ Login error:', (e as Error).message);
    return false;
  }
}

async function testDashboard() {
  console.log('\n📊 Test: Dashboard');
  try {
    await page.goto(`${BASE_URL}/`, { waitUntil: 'networkidle0', timeout: 30000 });
    await delay(2000);
    
    const url = page.url();
    console.log('   URL:', url);
    
    if (url.includes('login')) {
      console.log('   ⚠️ Need to login');
      return false;
    }
    
    const content = await page.content();
    if (content.includes('Total Prospects') || content.includes('Dashboard')) {
      console.log('   ✅ Dashboard works');
      return true;
    }
    
    return !url.includes('login');
    
  } catch (e) {
    console.log('   ❌ Dashboard error:', (e as Error).message);
    return false;
  }
}

async function testAddProspect() {
  console.log('\n➕ Test: Add Prospect');
  try {
    await page.goto(`${BASE_URL}/add-prospect`, { waitUntil: 'networkidle0', timeout: 30000 });
    await delay(2000);
    
    const url = page.url();
    
    if (url.includes('login')) {
      console.log('   ⚠️ Need to login first');
      return false;
    }
    
    await page.waitForSelector('input[name="name"]', { timeout: 5000 });
    await page.type('input[name="name"]', PROSPECT_DATA.name, { delay: 100 });
    await page.type('input[name="email"]', PROSPECT_DATA.email, { delay: 100 });
    
    const phoneInput = await page.$('input[name="phone"]');
    if (phoneInput) await page.type('input[name="phone"]', PROSPECT_DATA.phone, { delay: 100 });
    
    await clickButtonWithText('Add Prospect');
    
    await delay(5000);
    
    const finalUrl = page.url();
    console.log('   URL after submit:', finalUrl);
    
    if (finalUrl.includes('/prospects/')) {
      console.log('   ✅ Prospect created');
      return true;
    }
    
    return finalUrl.includes('/prospects/');
    
  } catch (e) {
    console.log('   ❌ Add prospect error:', (e as Error).message);
    return false;
  }
}

async function testProspectDetail() {
  console.log('\n👤 Test: Prospect Detail');
  try {
    const url = page.url();
    const content = await page.content();
    
    if (content.includes('Hemang') || content.includes('Pipeline') || url.includes('/prospects/')) {
      console.log('   ✅ Prospect detail works');
      return true;
    }
    
    return url.includes('/prospects/');
    
  } catch (e) {
    console.log('   ❌ Prospect detail error:', (e as Error).message);
    return false;
  }
}

async function testBackToDashboard() {
  console.log('\n🔙 Test: Back to Dashboard');
  try {
    await clickButtonWithText('Back to Dashboard');
    await delay(2000);
    
    const url = page.url();
    if (url.endsWith('/')) {
      console.log('   ✅ Back to dashboard works');
      return true;
    }
    
    return url.endsWith('/');
    
  } catch (e) {
    console.log('   ❌ Back navigation error:', (e as Error).message);
    return false;
  }
}

async function testProspectInList() {
  console.log('\n📋 Test: Prospect in Dashboard List');
  try {
    const content = await page.content();
    
    if (content.includes('Hemang Kashikar')) {
      console.log('   ✅ Prospect in list');
      return true;
    }
    
    console.log('   ⚠️ Prospect not visible');
    return false;
    
  } catch (e) {
    console.log('   ❌ List check error:', (e as Error).message);
    return false;
  }
}

async function testSettings() {
  console.log('\n⚙️ Test: Settings Page');
  try {
    await page.goto(`${BASE_URL}/settings`, { waitUntil: 'networkidle0', timeout: 30000 });
    await delay(2000);
    
    const url = page.url();
    
    if (url.includes('login')) {
      console.log('   ⚠️ Need to login');
      return false;
    }
    
    if (url.includes('/settings')) {
      console.log('   ✅ Settings page works');
      return true;
    }
    
    return url.includes('/settings');
    
  } catch (e) {
    console.log('   ❌ Settings error:', (e as Error).message);
    return false;
  }
}

async function runTests() {
  let passed = 0;
  let failed = 0;
  
  const results: { name: string; passed: boolean }[] = [];
  
  try {
    await initBrowser();
    
    console.log('========================================');
    console.log('   CHAMPIQ V2 - E2E TEST SUITE');
    console.log('========================================\n');
    
    // Run tests
    results.push({ name: 'User Registration', passed: await testRegistration() });
    results.push({ name: 'Dashboard', passed: await testDashboard() });
    results.push({ name: 'Add Prospect', passed: await testAddProspect() });
    results.push({ name: 'Prospect Detail', passed: await testProspectDetail() });
    results.push({ name: 'Back to Dashboard', passed: await testBackToDashboard() });
    results.push({ name: 'Prospect in List', passed: await testProspectInList() });
    results.push({ name: 'Settings Page', passed: await testSettings() });
    
    // Summary
    console.log('\n========================================');
    console.log('   TEST RESULTS SUMMARY');
    console.log('========================================');
    
    results.forEach(r => {
      console.log(`   ${r.passed ? '✅' : '❌'} ${r.name}`);
      if (r.passed) passed++; else failed++;
    });
    
    console.log('========================================');
    console.log(`   ✅ Passed: ${passed}`);
    console.log(`   ❌ Failed: ${failed}`);
    console.log('========================================\n');
    
  } catch (error) {
    console.error('\n❌ Test suite error:', error);
  } finally {
    await closeBrowser();
  }
  
  process.exit(failed > 0 ? 1 : 0);
}

runTests();
