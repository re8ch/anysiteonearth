import { createElement } from 'react';
import type { Metadata } from 'next';
import { Box, Crosshair, Satellite, Sparkles } from 'lucide-react';
import AnysiteExperience from '@/components/AnysiteExperience';
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
  const t = copy[locale];
  return {
    title: t.title,
    description: t.description,
    alternates: {
      canonical: absoluteUrl(locale),
      languages: alternates(),
    },
  };
}

export default async function LocaleHomePage({ params }: Props) {
  const { locale: rawLocale } = await params;
  const locale = normalizeLocale(rawLocale);
  const t = copy[locale];
  const languageOptions = navLanguageOptions(locale);
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
  const dir = rtlLocales.has(locale) ? 'rtl' : 'ltr';

  return (
    <div className="site-shell" dir={dir}>
      {createElement('re8ch-navigator', {
        product: 'anysite',
        locale,
        'home-href': localizedPath(locale),
        links: JSON.stringify(navLinks),
        'extra-actions': JSON.stringify(extraActions),
        'language-options': JSON.stringify(languageOptions),
        'language-mode': 'available',
        'max-width': '1280px',
      })}

      <main>
        <AnysiteExperience productName="Any Site on Earth" />

        <section className="workflow-band" id="workflow" aria-labelledby="workflow-title">
          <div className="section-inner">
            <div className="section-heading">
              <span className="eyebrow">{t.eyebrow}</span>
              <h2 id="workflow-title">{t.workflowTitle}</h2>
              <p>{t.workflowLead}</p>
            </div>
            <div className="workflow-grid">
              {[
                [Crosshair, t.workflow],
                [Satellite, t.features],
                [Box, t.workspace],
              ].map(([Icon, label], index) => {
                const LucideIcon = Icon as typeof Crosshair;
                return (
                  <article className="info-card" key={String(label)}>
                    <div className="card-index">{String(index + 1).padStart(2, '0')}</div>
                    <div className="card-icon"><LucideIcon size={18} /></div>
                    <h3>{String(label)}</h3>
                    <p>{t.lead}</p>
                  </article>
                );
              })}
            </div>
          </div>
        </section>

        <section className="contact-band" id="contact" aria-labelledby="contact-title">
          <div className="section-inner contact-inner">
            <div>
              <span className="eyebrow">RE8CH product network</span>
              <h2 id="contact-title">{t.contactTitle}</h2>
            </div>
            <a className="button primary" href="mailto:contact@re8ch.com?subject=Any%20Site%20on%20Earth%20Access">
              <Sparkles size={16} />
              {t.secondary}
            </a>
          </div>
        </section>
      </main>

      {createElement('re8ch-footer', {
        'active-product': 'anysite',
        locale,
        'language-options': JSON.stringify(languageOptions),
        'language-mode': 'available',
        'brand-logo': brandAssetUrl('/SVG/logo.svg'),
      })}
    </div>
  );
}
