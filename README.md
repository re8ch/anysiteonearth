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
- `services/scale/`: Scale v1 FastAPI + PostGIS 推理服务；`/scale/` 为 RoveMap 杨市镇演示

## Scale v1

Scale v1 使用 OpenStreetMap 已知道路与免费的 Sentinel-2 L2A 数据，为杨市镇
约 24×24 km 试点区生成徒步、Gravel Bike、普通汽车和四驱车适应性评分。
它明确工作在 10 m 环境分析尺度，不把 Sentinel-2 插值结果表述为窄小路检测。

本地启动方式见 [`services/scale/README.md`](services/scale/README.md)；前端通过
`NEXT_PUBLIC_SCALE_API_BASE` 指向 Scale API。

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

## Product Resource Isolation

`infra/product-resources.yaml` records Any Site on Earth's independent Pigsty
database, Harbor project, Observable space, K3S namespace, and product-local
account store. Email and phone login stay on the shared RE8CH auth backend.
From the workspace root, verify all product declarations with:

```bash
node ops/product-platform/verify-product-tenants.mjs
```
