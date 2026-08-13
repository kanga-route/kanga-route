(() => {
  'use strict';

  const form = document.querySelector('#verify-form');
  const emailInput = document.querySelector('#email');
  const refreshInput = document.querySelector('#refresh-cache');
  const submitButton = document.querySelector('#submit-button');
  const requestState = document.querySelector('#request-state');
  const resultPanel = document.querySelector('#result-panel');

  const summaries = Object.freeze({
    Valid: 'The mailbox accepted the verification probe.',
    Invalid: 'The verifier found explicit evidence that this address is invalid.',
    'Catch-All': 'The domain accepts arbitrary recipients, so this mailbox cannot be confirmed.',
    Unknown: 'The available evidence was inconclusive or temporarily unavailable.',
  });

  function setText(selector, value) {
    const element = document.querySelector(selector);
    element.textContent = value;
  }

  function setRequestState(state, message) {
    requestState.dataset.state = state;
    requestState.textContent = message;
    requestState.hidden = false;
  }

  function isString(value, maximumLength) {
    return typeof value === 'string' && value.length > 0 && value.length <= maximumLength;
  }

  function parseResponse(value) {
    if (value === null || typeof value !== 'object' || Array.isArray(value)) {
      throw new Error('invalid-response');
    }
    const result = value.result;
    const cache = value.cache;
    const statuses = new Set(['Valid', 'Invalid', 'Catch-All', 'Unknown']);
    if (
      result === null || typeof result !== 'object' || Array.isArray(result) ||
      cache === null || typeof cache !== 'object' || Array.isArray(cache) ||
      !isString(result.email, 254) || !statuses.has(result.status) ||
      !isString(result.reason, 80) || !isString(result.mailbox_provider, 120) ||
      typeof result.is_role_account !== 'boolean' || !Array.isArray(result.mx_records) ||
      !result.mx_records.every((host) => isString(host, 253)) ||
      (result.smtp_code !== null && !Number.isInteger(result.smtp_code)) ||
      !isString(result.verified_at, 80) ||
      !new Set(['hit', 'miss', 'bypassed']).has(cache.status)
    ) {
      throw new Error('invalid-response');
    }
    return { result, cache };
  }

  function renderResult(payload) {
    const { result, cache } = payload;
    setText('#result-email', result.email);
    setText('#result-status', result.status);
    setText('#result-summary', summaries[result.status]);
    setText('#result-reason', result.reason.replaceAll('_', ' '));
    setText('#result-provider', result.mailbox_provider);
    setText('#result-role', result.is_role_account ? 'Yes' : 'No');
    setText('#result-cache', cache.status === 'hit' ? 'Cached result' : cache.status === 'bypassed' ? 'Fresh check' : 'New result');
    setText('#result-smtp', result.smtp_code === null ? 'Not available' : String(result.smtp_code));

    const verifiedAt = new Date(result.verified_at);
    setText('#result-time', Number.isNaN(verifiedAt.valueOf()) ? result.verified_at : verifiedAt.toLocaleString());

    const status = document.querySelector('#result-status');
    status.dataset.status = result.status;

    const mxList = document.querySelector('#result-mx');
    mxList.replaceChildren();
    const hosts = result.mx_records.length === 0 ? ['None reported'] : result.mx_records;
    for (const host of hosts) {
      const item = document.createElement('li');
      item.textContent = host;
      mxList.append(item);
    }

    resultPanel.hidden = false;
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    resultPanel.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
  }

  async function requestVerification(email, cachePolicy, signal) {
    const response = await fetch('/api/v1/verify', {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        accept: 'application/json',
        'content-type': 'application/json',
      },
      body: JSON.stringify({ email, cache_policy: cachePolicy }),
      signal,
    });

    let body;
    try {
      body = await response.json();
    } catch {
      throw new Error('The appliance returned an unreadable response.');
    }

    if (!response.ok) {
      const message = body?.error?.message;
      throw new Error(isString(message, 180) ? message : 'The verification could not be completed.');
    }
    return parseResponse(body);
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    resultPanel.hidden = true;

    if (!emailInput.checkValidity()) {
      emailInput.reportValidity();
      setRequestState('error', 'Enter one complete email address.');
      return;
    }

    submitButton.disabled = true;
    emailInput.disabled = true;
    refreshInput.disabled = true;
    setRequestState('working', 'Checking syntax, DNS, and recipient-server evidence…');

    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 50_000);
    try {
      const payload = await requestVerification(
        emailInput.value,
        refreshInput.checked ? 'refresh' : 'use',
        controller.signal,
      );
      renderResult(payload);
      setRequestState('complete', 'Verification complete.');
    } catch (error) {
      const message = error?.name === 'AbortError'
        ? 'The browser stopped waiting for the verification. Try again later.'
        : error?.message || 'The verification could not be completed.';
      setRequestState('error', message);
    } finally {
      window.clearTimeout(timeout);
      submitButton.disabled = false;
      emailInput.disabled = false;
      refreshInput.disabled = false;
      emailInput.focus();
    }
  });
})();
