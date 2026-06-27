import type { Metadata } from 'next'
import './globals.css'
import { brandAssetUrl } from '@/lib/brandAssets'

const brandAssetsOrigin = brandAssetUrl('/').replace(/\/$/, '')

export const metadata: Metadata = {
  title: 'Any Site on Earth | RE8CH',
  description: 'Any Site on Earth 是 RE8CH 的地理空间产品入口：从坐标连接卫星影像、地形上下文和三维场景。',
  icons: { icon: brandAssetUrl('/PRODUCTS/anysiteonearth/SVG/icon.svg') },
  alternates: {
    canonical: 'https://anysiteonearth.re8ch.com/',
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="zh-CN" data-lang="zh">
      <head>
        <meta name="brand-assets-base-url" content={brandAssetsOrigin} />
        <link rel="stylesheet" href={`${brandAssetsOrigin}/dist/re8ch-navigator.css`} />
        <link rel="stylesheet" href={`${brandAssetsOrigin}/dist/re8ch-footer.css`} />
        <script src={`${brandAssetsOrigin}/dist/re8ch-navigator.js`} defer></script>
        <script src={`${brandAssetsOrigin}/dist/re8ch-footer.js`} defer></script>
        <script async src="https://www.googletagmanager.com/gtag/js?id=G-Z0X8KS7NNX"></script>
        <script
          dangerouslySetInnerHTML={{
            __html: `
            window.dataLayer = window.dataLayer || [];
            function gtag(){dataLayer.push(arguments);}
            gtag('js', new Date());
            gtag('config', 'G-Z0X8KS7NNX');
          `,
          }}
        />
      </head>
      <body className="antialiased">
        {children}
      </body>
    </html>
  )
}
