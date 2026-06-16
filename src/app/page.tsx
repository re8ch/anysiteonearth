import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Any Site on Earth | RE8CH',
  alternates: {
    canonical: 'https://anysiteonearth.re8ch.com/en/',
  },
};

export default function RootRedirectPage() {
  return (
    <main style={{ minHeight: '100svh', display: 'grid', placeItems: 'center' }}>
      <meta httpEquiv="refresh" content="0; url=/en/" />
      <link rel="canonical" href="https://anysiteonearth.re8ch.com/en/" />
      <link rel="sitemap" type="application/xml" title="Sitemap" href="https://anysiteonearth.re8ch.com/sitemap.xml" />
      <p>
        <a href="/en/">Any Site on Earth</a>
      </p>
    </main>
  );
}
