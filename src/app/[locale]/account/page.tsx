import { createElement } from 'react';
import type { Metadata } from 'next';
import SharedAccountPanel from '@/components/auth/SharedAccountPanel';
import {
  absoluteUrl,
  alternates,
  copy,
  localizedPath,
  navLanguageOptions,
  normalizeLocale,
  productLocales,
  rtlLocales,
} from '@/lib/productI18n';
import { brandAssetUrl } from '@/lib/brandAssets';

type Props = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return productLocales.map((locale) => ({ locale }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale: rawLocale } = await params;
  const locale = normalizeLocale(rawLocale);
  return {
    title: `Account | Any Site on Earth`,
    description: 'Shared RE8CH login for Any Site on Earth.',
    alternates: {
      canonical: absoluteUrl(locale, 'account'),
      languages: alternates('account'),
    },
  };
}

export default async function LocaleAccountPage({ params }: Props) {
  const { locale: rawLocale } = await params;
  const locale = normalizeLocale(rawLocale);
  const t = copy[locale];
  const languageOptions = navLanguageOptions(locale, 'account');
  const navLinks = [
    { label: t.workflow, href: `${localizedPath(locale)}#workflow` },
    { label: t.features, href: `${localizedPath(locale)}#features` },
    { label: t.workspace, href: localizedPath(locale, 'workspace') },
    { label: 'Account', href: localizedPath(locale, 'account') },
    { label: t.contact, href: `${localizedPath(locale)}#contact` },
  ];
  const extraActions = [
    {
      label: { zh: '登录', en: 'Sign in' },
      href: `https://api.re8ch.com/auth/start?service=anysite&return_to=${encodeURIComponent(`https://anysiteonearth.re8ch.com${localizedPath(locale, 'account')}`)}`,
    },
  ];

  return (
    <div className="site-shell" dir={rtlLocales.has(locale) ? 'rtl' : 'ltr'}>
      {createElement('re8ch-navigator', {
        product: 'anysite',
        locale,
        'home-href': localizedPath(locale),
        links: JSON.stringify(navLinks),
        'extra-actions': JSON.stringify(extraActions),
        'language-options': JSON.stringify(languageOptions),
        'language-mode': 'available',
        'max-width': '1280px',
        suppressHydrationWarning: true,
      })}
      <main>
        <SharedAccountPanel />
      </main>
      {createElement('re8ch-footer', {
        'active-product': 'anysite',
        locale,
        'language-options': JSON.stringify(languageOptions),
        'language-mode': 'available',
        'brand-logo': brandAssetUrl('/SVG/logo.svg'),
        suppressHydrationWarning: true,
      })}
    </div>
  );
}
