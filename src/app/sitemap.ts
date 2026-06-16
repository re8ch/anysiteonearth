import type { MetadataRoute } from 'next';
import { absoluteUrl, alternates, productLocales } from '@/lib/productI18n';

export const dynamic = 'force-static';

const segments = ['', 'workspace'] as const;

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  return segments.flatMap((segment) =>
    productLocales.map((locale) => ({
      url: absoluteUrl(locale, segment),
      lastModified: now,
      changeFrequency: 'weekly' as const,
      priority: segment ? 0.7 : 0.9,
      alternates: {
        languages: alternates(segment),
      },
    }))
  );
}
