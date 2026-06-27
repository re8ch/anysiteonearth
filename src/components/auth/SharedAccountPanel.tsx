'use client';

import { useEffect, useState } from 'react';

type Identity = {
  subject?: string;
  email?: string;
  name?: string;
  preferredUsername?: string;
  provider?: string;
  sessionId?: string;
  expiresAt?: string;
};

type AuthMeResponse = {
  identity?: Identity | null;
};

const authBase = 'https://api.re8ch.com/auth';
const cacheKey = 're8ch.auth.identity.v1';

type IdentityCache = {
  identity: Identity;
  cachedAt: number | string;
  expiresAt?: string;
};

function display(value: string | undefined) {
  return value && value.trim() ? value : '--';
}

function cachedIdentity() {
  try {
    const raw = window.localStorage.getItem(cacheKey);
    if (!raw) return null;
    const cached = JSON.parse(raw) as IdentityCache;
    if (!cached.identity?.subject) return null;
    const expiresAt = Date.parse(cached.identity.expiresAt || cached.expiresAt || '');
    const cachedAt = Date.parse(String(cached.cachedAt || '')) || Number(cached.cachedAt) || Date.now();
    const fallbackExpiresAt = cachedAt + 15 * 60 * 1000;
    if (Date.now() > (Number.isFinite(expiresAt) ? expiresAt : fallbackExpiresAt) - 30 * 1000) {
      window.localStorage.removeItem(cacheKey);
      notifyAuthChange(null);
      return null;
    }
    return cached.identity;
  } catch {
    return null;
  }
}

function notifyAuthChange(nextIdentity: Identity | null) {
  try {
    window.dispatchEvent(new CustomEvent('re8ch-auth-change', { detail: { identity: nextIdentity } }));
  } catch {
    // Older or restricted browser contexts can ignore the live navigator refresh.
  }
}

function writeIdentityCache(nextIdentity: Identity | null) {
  try {
    if (!nextIdentity?.subject) {
      window.localStorage.removeItem(cacheKey);
      notifyAuthChange(null);
      return;
    }
    window.localStorage.setItem(cacheKey, JSON.stringify({
      identity: nextIdentity,
      cachedAt: new Date().toISOString(),
      expiresAt: nextIdentity.expiresAt || '',
    }));
    notifyAuthChange(nextIdentity);
  } catch {
    // Storage can be disabled in private contexts; the HttpOnly SSO cookie remains authoritative.
  }
}

function decodeIdentityParam(value: string) {
  try {
    let padded = value.replace(/-/g, '+').replace(/_/g, '/');
    while (padded.length % 4) padded += '=';
    const raw = window.atob(padded);
    const json = decodeURIComponent(Array.from(raw, (char) => `%${char.charCodeAt(0).toString(16).padStart(2, '0')}`).join(''));
    const identity = JSON.parse(json) as Identity;
    return identity?.subject ? identity : null;
  } catch {
    return null;
  }
}

function readReturnIdentity() {
  try {
    const url = new URL(window.location.href);
    const encoded = url.searchParams.get('re8ch_identity');
    if (!encoded) return null;
    url.searchParams.delete('re8ch_identity');
    window.history.replaceState(null, '', `${url.pathname}${url.search}${url.hash}`);
    const identity = decodeIdentityParam(encoded);
    if (!identity) return null;
    writeIdentityCache(identity);
    return identity;
  } catch {
    return null;
  }
}

export default function SharedAccountPanel() {
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [loading, setLoading] = useState(true);
  const [returnTo, setReturnTo] = useState('https://anysiteonearth.re8ch.com/en/account/');

  useEffect(() => {
    const returned = readReturnIdentity();
    const cached = returned || cachedIdentity();
    setReturnTo(window.location.href);
    if (cached) {
      setIdentity(cached);
      setLoading(false);
    }
    let active = true;
    fetch(`${authBase}/me`, { credentials: 'include', cache: 'no-store' })
      .then((response) => response.json() as Promise<AuthMeResponse>)
      .then((payload) => {
        if (!active) return;
        const nextIdentity = payload.identity || null;
        if (!nextIdentity && cached) return;
        writeIdentityCache(nextIdentity);
        setIdentity(nextIdentity);
      })
      .catch(() => {
        if (active && !cached) setIdentity(null);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  async function signOut() {
    writeIdentityCache(null);
    await fetch(`${authBase}/logout`, { method: 'POST', credentials: 'include' }).catch(() => undefined);
    window.location.reload();
  }

  return (
    <section className="account-page" aria-labelledby="account-title">
      <div className="account-inner">
        <p className="eyebrow">RE8CH Account</p>
        <h1 id="account-title">Any Site on Earth account</h1>
        <p className="account-lead">Use one RE8CH login across product sites. Any Site on Earth does not have service-local user records yet, so this page only links shared identity for now.</p>
        <div className="account-grid">
          <article className="account-card">
            <h2>Identity</h2>
            <dl className="account-kv">
              <div><dt>Status</dt><dd>{loading ? 'Checking session' : identity ? 'Signed in' : 'Not signed in'}</dd></div>
              <div><dt>Email</dt><dd>{display(identity?.email)}</dd></div>
              <div><dt>Name</dt><dd>{display(identity?.name || identity?.preferredUsername)}</dd></div>
              <div><dt>Provider</dt><dd>{display(identity?.provider)}</dd></div>
              <div><dt>Subject</dt><dd>{display(identity?.subject)}</dd></div>
            </dl>
            <div className="account-actions">
              {!identity && <a className="button primary" href={`${authBase}/start?service=anysite&return_to=${encodeURIComponent(returnTo)}`}>Sign in with RE8CH</a>}
              {identity && <button className="button" type="button" onClick={signOut}>Sign out</button>}
            </div>
          </article>
          <aside className="account-card">
            <h2>Service Link</h2>
            <dl className="account-kv">
              <div><dt>Service</dt><dd>anysite</dd></div>
              <div><dt>Product Data</dt><dd>No service-local user data yet</dd></div>
              <div><dt>Boundary</dt><dd>Future site workspaces will link by shared subject</dd></div>
            </dl>
            <p className="account-note">Shared identity is ready. Product records will stay inside the Any Site on Earth service when that data model is enabled.</p>
          </aside>
        </div>
      </div>
    </section>
  );
}
