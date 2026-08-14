import { expect, test } from '@playwright/test';

const validResult = {
  result: {
    email: 'person@example.com',
    status: 'Valid',
    reason: 'OK',
    mailbox_provider: 'Google Workspace',
    is_role_account: false,
    mx_records: ['aspmx.l.google.com'],
    smtp_code: 250,
    verified_at: '2026-08-13T20:00:00+00:00',
  },
  cache: { status: 'miss' },
};

async function fulfillJson(route, status, body) {
  await route.fulfill({
    body: JSON.stringify(body),
    contentType: 'application/json',
    status,
  });
}

test('keyboard submission renders a successful neutral result', async ({ page }) => {
  const externalRequests = [];
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.hostname !== '127.0.0.1') externalRequests.push(request.url());
  });
  await page.route('**/api/v1/verify', (route) =>
    fulfillJson(route, 200, validResult),
  );
  await page.goto('/');

  await page.getByLabel('Email address').fill('Person@Example.com');
  await page.getByLabel('Email address').press('Enter');

  await expect(page.getByRole('heading', { name: 'person@example.com' })).toBeVisible();
  await expect(page.locator('#result-status')).toHaveText('Valid');
  await expect(page.locator('#result-provider')).toHaveText('Google Workspace');
  await expect(page.locator('#request-state')).toHaveText('Verification complete.');
  expect(externalRequests).toEqual([]);
});

test('browser validation blocks malformed input before a request', async ({ page }) => {
  let apiRequests = 0;
  await page.route('**/api/v1/verify', async (route) => {
    apiRequests += 1;
    await fulfillJson(route, 500, {});
  });
  await page.goto('/');

  await page.getByLabel('Email address').fill('not-an-email');
  await page.getByRole('button', { name: 'Verify address' }).click();

  await expect(page.locator('#request-state')).toHaveText(
    'Enter one complete email address.',
  );
  expect(apiRequests).toBe(0);
});

test('unknown remains explicitly inconclusive rather than invalid', async ({ page }) => {
  await page.route('**/api/v1/verify', (route) =>
    fulfillJson(route, 200, {
      ...validResult,
      result: {
        ...validResult.result,
        status: 'Unknown',
        reason: 'Timeout',
        smtp_code: null,
      },
    }),
  );
  await page.goto('/');
  await page.getByLabel('Email address').fill('person@example.com');
  await page.getByRole('button', { name: 'Verify address' }).click();

  await expect(page.locator('#result-status')).toHaveText('Unknown');
  await expect(page.locator('#result-summary')).toContainText('inconclusive');
  await expect(page.locator('#result-summary')).not.toContainText('invalid');
});

for (const scenario of [
  {
    name: 'timeout',
    status: 504,
    code: 'request_timeout',
    message: 'The verification timed out. Try again later.',
  },
  {
    name: 'server failure',
    status: 503,
    code: 'verification_failed',
    message: 'The verification could not be completed.',
  },
]) {
  test(`${scenario.name} is rendered as a safe recoverable state`, async ({ page }) => {
    await page.route('**/api/v1/verify', (route) =>
      fulfillJson(route, scenario.status, {
        error: { code: scenario.code, message: scenario.message },
      }),
    );
    await page.goto('/');
    await page.getByLabel('Email address').fill('person@example.com');
    await page.getByRole('button', { name: 'Verify address' }).click();

    await expect(page.locator('#request-state')).toHaveText(scenario.message);
    await expect(page.locator('#request-state')).toHaveAttribute('data-state', 'error');
    await expect(page.getByRole('button', { name: 'Verify address' })).toBeEnabled();
  });
}
