const brandAssetsRegion = (
  process.env.NEXT_PUBLIC_BRAND_ASSETS_REGION ||
  process.env.BRAND_ASSETS_REGION ||
  'global'
).toLowerCase();

const defaultBrandAssetsBaseUrl =
  brandAssetsRegion === 'zh'
    ? 'https://zh-brand-assets.re8ch.com'
    : 'https://zh-brand-assets.re8ch.com';

export const brandAssetsBaseUrl = (
  process.env.NEXT_PUBLIC_BRAND_ASSETS_BASE_URL ||
  process.env.BRAND_ASSETS_BASE_URL ||
  defaultBrandAssetsBaseUrl
).replace(/\/+$/, '');

export function brandAssetUrl(path: string, version?: string) {
  const url = `${brandAssetsBaseUrl}/${path.replace(/^\/+/, '')}`;
  return version ? `${url}?v=${encodeURIComponent(version)}` : url;
}
