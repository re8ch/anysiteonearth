#!/usr/bin/env node

import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const INDEXNOW_KEY = process.env.INDEXNOW_KEY || '4790e3784bdc45bf85e11ff304b3868f';
const DEFAULT_ENDPOINTS = [
  'https://api.indexnow.org/indexnow',
  'https://www.bing.com/indexnow',
];

const args = new Map(
  process.argv
    .slice(2)
    .filter((arg) => arg.startsWith('--') && arg.includes('='))
    .map((arg) => {
      const [key, ...value] = arg.slice(2).split('=');
      return [key, value.join('=')];
    })
);

const dryRun = process.argv.includes('--dry-run');
const live = process.argv.includes('--live');
const siteUrl = (args.get('site-url') || process.env.INDEXNOW_SITE_URL || process.env.SITE_URL || '').replace(/\/+$/, '');

if (!siteUrl) {
  console.error('Set SITE_URL, INDEXNOW_SITE_URL, or pass --site-url=https://example.com.');
  process.exit(1);
}

const host = new URL(siteUrl).host;
const endpoints = (process.env.INDEXNOW_ENDPOINTS || DEFAULT_ENDPOINTS.join(','))
  .split(',')
  .map((endpoint) => endpoint.trim())
  .filter(Boolean);

function decodeXml(value) {
  return value
    .replaceAll('&amp;', '&')
    .replaceAll('&lt;', '<')
    .replaceAll('&gt;', '>')
    .replaceAll('&quot;', '"')
    .replaceAll('&apos;', "'");
}

async function readSitemap() {
  if (args.get('sitemap-url')) {
    const response = await fetch(args.get('sitemap-url'));
    if (!response.ok) throw new Error(`Failed to fetch sitemap: ${response.status} ${response.statusText}`);
    return response.text();
  }

  if (live) {
    const response = await fetch(`${siteUrl}/sitemap.xml`);
    if (!response.ok) throw new Error(`Failed to fetch live sitemap: ${response.status} ${response.statusText}`);
    return response.text();
  }

  const sitemapFile = args.get('sitemap-file') || process.env.INDEXNOW_SITEMAP_FILE;
  const candidates = sitemapFile
    ? [sitemapFile]
    : ['dist/sitemap.xml', 'out/sitemap.xml', 'public/sitemap.xml'];
  const found = candidates.find((candidate) => existsSync(join(process.cwd(), candidate)));
  if (!found) {
    const response = await fetch(`${siteUrl}/sitemap.xml`);
    if (!response.ok) throw new Error(`No local sitemap found and live sitemap failed: ${response.status} ${response.statusText}`);
    return response.text();
  }
  return readFileSync(join(process.cwd(), found), 'utf8');
}

function urlsFromSitemap(xml) {
  return [...new Set(
    [...xml.matchAll(/<loc>\s*([^<]+?)\s*<\/loc>/g)]
      .map((match) => decodeXml(match[1].trim()))
      .filter((url) => {
        try {
          return new URL(url).host === host;
        } catch {
          return false;
        }
      })
  )];
}

function chunk(values, size) {
  const chunks = [];
  for (let index = 0; index < values.length; index += size) {
    chunks.push(values.slice(index, index + size));
  }
  return chunks;
}

const sitemap = await readSitemap();
const urlList = urlsFromSitemap(sitemap);

if (urlList.length === 0) {
  console.error(`No sitemap URLs matched host ${host}.`);
  process.exit(1);
}

for (const endpoint of endpoints) {
  for (const urls of chunk(urlList, 10000)) {
    const payload = { host, key: INDEXNOW_KEY, urlList: urls };
    if (process.env.INDEXNOW_KEY_LOCATION) payload.keyLocation = process.env.INDEXNOW_KEY_LOCATION;
    if (dryRun) {
      console.log(`[dry-run] ${endpoint}: ${urls.length} URLs for ${host}`);
      continue;
    }
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: { 'content-type': 'application/json; charset=utf-8' },
      body: JSON.stringify(payload),
    });
    if (![200, 202].includes(response.status)) {
      const body = await response.text().catch(() => '');
      throw new Error(`${endpoint} rejected ${host}: ${response.status} ${response.statusText} ${body}`.trim());
    }
    console.log(`${endpoint}: submitted ${urls.length} URLs for ${host} (${response.status})`);
  }
}
