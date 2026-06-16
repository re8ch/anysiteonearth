# Any Site on Earth (RE8CH 子站)

Static site for `anysiteonearth.re8ch.com`，归属于 RE8CH 网站家族的地理空间子项目。

- Source/output: `dist/`
- Base domain: `anysiteonearth.re8ch.com`
- Recommended: 与 `ledger-site` 一致，保留构建产物便于静态部署
- Brand asset source of truth: `https://brand-assets.re8ch.com`

## 部署

```bash
npm install
npm run build   # 产出 dist/（基于 next export）
wrangler pages deploy dist --project-name=anysiteonearth
```

或直接执行：

```bash
npm run deploy
```

## 脚本

```bash
npm run dev      # 本地开发（Next.js）
npm run build    # 生成 dist/
npm run lint     # ESLint
npm run dist:clean  # 清理 out/ 与 dist/
```

## 品牌资产

产品图标由 `brand-assets` 统一治理，本仓库不保存长期 logo 源文件。

默认使用全球资产域：

```text
https://brand-assets.re8ch.com/PRODUCTS/anysiteonearth/SVG/icon.svg
```

中国区构建可设置：

```bash
NEXT_PUBLIC_BRAND_ASSETS_REGION=zh
NEXT_PUBLIC_BRAND_ASSETS_BASE_URL=https://zh-brand-assets.re8ch.com
```

## 代码与说明

本仓库保留了原始页面源码（`src/`）与静态交付产物（`dist/`）：
- `src/`: Next.js 源码（交互地图、地形生成、3D 渲染）
- `dist/`: 部署到 RE8CH 子站的静态文件

## Product Site Design Compliance

- Next static export emits 27 locale routes for `/<locale>/` and
  `/<locale>/workspace/`; `/en/` is `x-default`.
- Each localized route generates canonical metadata, 27 language alternates plus
  `x-default`, and is included in `/sitemap.xml`.
- `/robots.txt` points to `https://anysiteonearth.re8ch.com/sitemap.xml`.
- IndexNow verification is published at
  `/4790e3784bdc45bf85e11ff304b3868f.txt`; run
  `npm run indexnow:submit` after deployment to submit sitemap URLs.
- Shared CDN navigator/footer receive matching `locale`, `language-options`, and
  `language-mode="available"` so footer language follows navigator language.
- The root path is a compatibility entry to `/en/`; query-string language
  switching is no longer canonical.
