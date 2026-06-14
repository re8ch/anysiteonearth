import {
  Box,
  Crosshair,
  Database,
  ExternalLink,
  Globe2,
  Layers3,
  Satellite,
  Sparkles,
} from 'lucide-react';
import AnysiteLogoMotion from '@/components/AnysiteLogoMotion';
import AnysiteExperience from '@/components/AnysiteExperience';

const productName = 'Any Site on Earth';

const workflow = [
  {
    icon: <Crosshair size={18} />,
    zhTitle: '选取地球上的任意位置',
    enTitle: 'Pick any place on Earth',
    zhCopy: '从城市、山谷、海岸线到无人区，把一个地理坐标变成可复核的项目起点。',
    enCopy: 'Turn a city block, valley, coastline, or remote coordinate into a reviewable project start.',
  },
  {
    icon: <Satellite size={18} />,
    zhTitle: '生成影像上下文',
    enTitle: 'Generate imagery context',
    zhCopy: '把卫星影像、范围框、坐标和地表线索整理到同一个工作面里。',
    enCopy: 'Bring satellite imagery, bounds, coordinates, and surface cues into one workspace.',
  },
  {
    icon: <Box size={18} />,
    zhTitle: '进入三维场景',
    enTitle: 'Move into a 3D scene',
    zhCopy: '为后续的地形、建筑、选址或叙事可视化准备一个轻量三维底座。',
    enCopy: 'Prepare a lightweight 3D base for terrain, buildings, site work, or visual storytelling.',
  },
];

const features = [
  {
    icon: <Globe2 size={19} />,
    zhTitle: '全球坐标优先',
    enTitle: 'Coordinate-first',
    zhCopy: '围绕经纬度、范围和地理上下文组织，而不是从传统文件夹或项目名开始。',
    enCopy: 'Organized around latitude, longitude, bounds, and geographic context instead of folders first.',
  },
  {
    icon: <Layers3 size={19} />,
    zhTitle: '影像到场景',
    enTitle: 'Imagery to scene',
    zhCopy: '把影像视图、地形线索和三维预览串成一个清晰、可演示的流程。',
    enCopy: 'Connect imagery, terrain cues, and 3D preview into a clear, presentable flow.',
  },
  {
    icon: <Database size={19} />,
    zhTitle: '可部署子产品',
    enTitle: 'Deployable product',
    zhCopy: '作为 RE8CH 产品网络中的独立站点存在，可单独发布、介绍和迭代。',
    enCopy: 'Lives as a standalone RE8CH product site that can be shipped, explained, and iterated independently.',
  },
];

export default function Home() {
  return (
    <div className="site-shell">
      <header className="nav">
        <a className="brand" href="/" aria-label="Any Site on Earth home">
          <AnysiteLogoMotion size="sm" motion="idle" />
          <span>{productName}</span>
        </a>

        <nav className="nav-links" aria-label="Product navigation">
          <a href="#workflow">
            <span className="copy-zh">工作流</span>
            <span className="copy-en">Workflow</span>
          </a>
          <a href="#features">
            <span className="copy-zh">能力</span>
            <span className="copy-en">Features</span>
          </a>
          <a href="#experience">
            <span className="copy-zh">功能展示</span>
            <span className="copy-en">Workspace</span>
          </a>
          <a href="#contact">
            <span className="copy-zh">联系</span>
            <span className="copy-en">Contact</span>
          </a>
        </nav>

        <div className="lang-switch" aria-label="Language">
          <a href="?lang=zh" data-lang-option="zh" aria-current="true">
            中文
          </a>
          <a href="?lang=en" data-lang-option="en" aria-current="false">
            EN
          </a>
        </div>
      </header>

      <main>
        <AnysiteExperience productName={productName} />

        <section className="workflow-band" id="workflow" aria-labelledby="workflow-title">
          <div className="section-inner">
            <div className="section-heading">
              <span className="eyebrow">Product flow</span>
              <h2 id="workflow-title">
                <span className="copy-zh">从坐标到场景，三步成型。</span>
                <span className="copy-en">From coordinate to scene in three steps.</span>
              </h2>
              <p className="copy-zh">它不只是一个地图 demo，而是一个可以被介绍、售卖和继续打磨的产品入口。</p>
              <p className="copy-en">It is no longer just a map demo; it is a product entry that can be explained, sold, and refined.</p>
            </div>

            <div className="workflow-grid">
              {workflow.map((item, index) => (
                <article className="info-card" key={item.zhTitle}>
                  <div className="card-index">{String(index + 1).padStart(2, '0')}</div>
                  <div className="card-icon">{item.icon}</div>
                  <h3>
                    <span className="copy-zh">{item.zhTitle}</span>
                    <span className="copy-en">{item.enTitle}</span>
                  </h3>
                  <p>
                    <span className="copy-zh">{item.zhCopy}</span>
                    <span className="copy-en">{item.enCopy}</span>
                  </p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="features-band" id="features" aria-labelledby="features-title">
          <div className="section-inner split">
            <div className="section-heading compact">
              <span className="eyebrow">What it does</span>
              <h2 id="features-title">
                <span className="copy-zh">一个独立产品页该讲清楚的事。</span>
                <span className="copy-en">What a standalone product page needs to make clear.</span>
              </h2>
            </div>

            <div className="feature-list">
              {features.map((item) => (
                <article className="feature-row" key={item.zhTitle}>
                  <div className="feature-icon">{item.icon}</div>
                  <div>
                    <h3>
                      <span className="copy-zh">{item.zhTitle}</span>
                      <span className="copy-en">{item.enTitle}</span>
                    </h3>
                    <p>
                      <span className="copy-zh">{item.zhCopy}</span>
                      <span className="copy-en">{item.enCopy}</span>
                    </p>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="contact-band" id="contact" aria-labelledby="contact-title">
          <div className="section-inner contact-inner">
            <div>
              <span className="eyebrow">RE8CH product network</span>
              <h2 id="contact-title">
                <span className="copy-zh">和 Ledger 一样，作为独立子产品被看见。</span>
                <span className="copy-en">Visible as a standalone sub-product, like Ledger.</span>
              </h2>
            </div>
            <a className="button primary" href="mailto:contact@re8ch.com?subject=Any%20Site%20on%20Earth%20Access">
              <Sparkles size={16} />
              <span className="copy-zh">讨论下一步</span>
              <span className="copy-en">Discuss next steps</span>
            </a>
          </div>
        </section>
      </main>

      <footer className="site-footer">
        <div className="footer-inner">
          <div className="footer-brand">
            <AnysiteLogoMotion size="sm" motion="pulse" />
            <div>
              <strong>{productName}</strong>
              <span className="copy-zh">锐奇创想 RE8CH 地理空间产品网络</span>
              <span className="copy-en">A RE8CH geospatial product in the company network</span>
            </div>
          </div>

          <div className="footer-grid">
            <section className="footer-block">
              <h2>
                <span className="copy-zh">产品互链</span>
                <span className="copy-en">Product links</span>
              </h2>
              <div className="footer-links">
                <a href="/">Any Site on Earth 首页</a>
                <a href="/workspace">
                  <span className="copy-zh">功能展示工作台</span>
                  <span className="copy-en">Live workspace</span>
                </a>
                <a href="https://re8ch.com/zh/home">锐奇创想 RE8CH</a>
                <a href="https://ledger.re8ch.com">理账 Ledger</a>
              </div>
            </section>

            <section className="footer-block">
              <h2>
                <span className="copy-zh">联系</span>
                <span className="copy-en">Contact</span>
              </h2>
              <p>contact@re8ch.com</p>
              <p>career@re8ch.com</p>
              <p className="copy-zh">湖南省娄底市涟源市杨市镇锐奇软件开发工作室</p>
              <p className="copy-en">RE8CH software development studio, Lianyuan, Hunan</p>
            </section>

            <section className="footer-block">
              <h2>
                <span className="copy-zh">外部核验</span>
                <span className="copy-en">External verification</span>
              </h2>
              <div className="trust-links">
                <a className="trust-link" href="https://www.linkedin.com/company/107777110" target="_blank" rel="noopener noreferrer">
                  <span style={{ background: '#2f6fed' }}>in</span>
                  <span>LinkedIn</span>
                  <ExternalLink size={13} />
                </a>
                <a className="trust-link" href="https://www.crunchbase.com/organization/re8ch" target="_blank" rel="noopener noreferrer">
                  <span style={{ background: '#1463ff' }}>CB</span>
                  <span>Crunchbase</span>
                  <ExternalLink size={13} />
                </a>
                <a className="trust-link" href="https://www.dnb.com/duns-number/lookup.html" target="_blank" rel="noopener noreferrer">
                  <span style={{ background: '#6d48d8' }}>D&B</span>
                  <span>D-U-N-S</span>
                  <ExternalLink size={13} />
                </a>
                <a className="trust-link" href="https://www.gsxt.gov.cn/index.html" target="_blank" rel="noopener noreferrer">
                  <span style={{ background: '#d94343' }}>信</span>
                  <span>China Credit</span>
                  <ExternalLink size={13} />
                </a>
              </div>
            </section>
          </div>

          <div className="footer-bottom">
            <div>
              <span className="copy-zh">© 2026 锐奇创想经济咨询. All rights reserved.</span>
              <span className="copy-en">© 2026 Reachieve LLC. All rights reserved.</span>
              <a href="https://beian.miit.gov.cn" target="_blank" rel="noopener noreferrer">
                湘ICP备2025130798号-4
              </a>
            </div>
            <div className="stack-strip" aria-hidden="true">
              <span>Anysite</span>
              <span>RE8CH</span>
              <span>Ledger</span>
              <span>Cloudflare</span>
              <span>OpenAI</span>
            </div>
          </div>
        </div>
      </footer>

      <script
        dangerouslySetInnerHTML={{
          __html: `
(() => {
  const root = document.documentElement;
  const links = Array.from(document.querySelectorAll('[data-lang-option]'));
  const params = new URLSearchParams(window.location.search);
  const saved = window.localStorage.getItem('anysite-lang');
  const initial = params.get('lang') === 'en' || params.get('lang') === 'zh' ? params.get('lang') : saved || 'zh';

  function setLang(lang, replaceUrl) {
    const next = lang === 'en' ? 'en' : 'zh';
    root.dataset.lang = next;
    root.lang = next === 'zh' ? 'zh-CN' : 'en';
    links.forEach((link) => link.setAttribute('aria-current', link.dataset.langOption === next ? 'true' : 'false'));
    window.localStorage.setItem('anysite-lang', next);
    if (replaceUrl) {
      const url = new URL(window.location.href);
      url.searchParams.set('lang', next);
      window.history.replaceState({}, '', url);
    }
  }

  links.forEach((link) => {
    link.addEventListener('click', (event) => {
      event.preventDefault();
      setLang(link.dataset.langOption, true);
    });
  });

  setLang(initial, false);
})();
          `,
        }}
      />
    </div>
  );
}
