export const productLocales = [
  'en', 'zh-CN', 'zh-TW', 'es', 'ar', 'hi', 'pt-BR', 'bn', 'ru', 'ja', 'fr', 'de', 'ko', 'id',
  'tr', 'vi', 'it', 'fa', 'ur', 'th', 'pl', 'nl', 'sw', 'ms', 'fil', 'uk', 'he',
] as const;

export type ProductLocale = typeof productLocales[number];

export const rtlLocales = new Set<ProductLocale>(['ar', 'fa', 'ur', 'he']);

export const languageOptions = [
  ['en', 'English'], ['zh-CN', '简体中文'], ['zh-TW', '繁體中文'], ['es', 'Español'], ['ar', 'العربية'],
  ['hi', 'हिन्दी'], ['pt-BR', 'Português'], ['bn', 'বাংলা'], ['ru', 'Русский'], ['ja', '日本語'],
  ['fr', 'Français'], ['de', 'Deutsch'], ['ko', '한국어'], ['id', 'Indonesia'], ['tr', 'Türkçe'],
  ['vi', 'Tiếng Việt'], ['it', 'Italiano'], ['fa', 'فارسی'], ['ur', 'اردو'], ['th', 'ไทย'],
  ['pl', 'Polski'], ['nl', 'Nederlands'], ['sw', 'Kiswahili'], ['ms', 'Melayu'], ['fil', 'Filipino'],
  ['uk', 'Українська'], ['he', 'עברית'],
] as const;

export const siteOrigin = 'https://anysiteonearth.re8ch.com';

export function normalizeLocale(value: string): ProductLocale {
  return productLocales.includes(value as ProductLocale) ? (value as ProductLocale) : 'en';
}

export function localizedPath(locale: ProductLocale, segment = '') {
  return segment ? `/${locale}/${segment}/` : `/${locale}/`;
}

export function absoluteUrl(locale: ProductLocale, segment = '') {
  return `${siteOrigin}${localizedPath(locale, segment)}`;
}

export function alternates(segment = '') {
  return Object.fromEntries([
    ...productLocales.map((locale) => [locale, absoluteUrl(locale, segment)]),
    ['x-default', absoluteUrl('en', segment)],
  ]);
}

export function navLanguageOptions(locale: ProductLocale, segment = '') {
  void locale;
  return languageOptions.map(([code, label]) => ({
    label,
    value: code,
    href: localizedPath(code as ProductLocale, segment),
  }));
}

const base = {
  title: 'Any Site on Earth | RE8CH',
  description: 'Any Site on Earth turns any coordinate into a reviewable geospatial product workspace with imagery context and a lightweight 3D scene.',
  workflow: 'Workflow',
  features: 'Features',
  workspace: 'Workspace',
  contact: 'Contact',
  eyebrow: 'Geospatial product',
  heading: 'Turn any coordinate into a product-ready site workspace.',
  lead: 'Any Site on Earth connects satellite imagery, bounds, coordinates, and a lightweight 3D scene into one localized product surface.',
  primary: 'Open workspace',
  secondary: 'Contact RE8CH',
  workflowTitle: 'From coordinate to scene in three steps.',
  workflowLead: 'Pick a place, generate imagery context, and move into a 3D-ready site view.',
  contactTitle: 'Visible as a standalone RE8CH sub-product.',
};

export const copy: Record<ProductLocale, typeof base> = {
  en: base,
  'zh-CN': { ...base, title: 'Any Site on Earth | RE8CH', description: 'Any Site on Earth 把任意坐标变成可复核的地理空间产品工作台，包含影像上下文和轻量三维场景。', workflow: '工作流', features: '能力', workspace: '工作台', contact: '联系', eyebrow: '地理空间产品', heading: '把任意坐标变成可产品化的站点工作台。', lead: 'Any Site on Earth 将卫星影像、范围、坐标和轻量三维场景连接到一个本地化产品界面。', primary: '打开工作台', secondary: '联系 RE8CH', workflowTitle: '从坐标到场景，三步成型。', workflowLead: '选择位置，生成影像上下文，并进入可三维化的站点视图。', contactTitle: '作为独立 RE8CH 子产品被看见。' },
  'zh-TW': { ...base, title: 'Any Site on Earth | RE8CH', description: 'Any Site on Earth 把任意座標變成可複核的地理空間產品工作台，包含影像上下文和輕量三維場景。', workflow: '工作流', features: '能力', workspace: '工作台', contact: '聯絡', eyebrow: '地理空間產品', heading: '把任意座標變成可產品化的站點工作台。', lead: 'Any Site on Earth 將衛星影像、範圍、座標和輕量三維場景連接到一個在地化產品介面。', primary: '開啟工作台', secondary: '聯絡 RE8CH', workflowTitle: '從座標到場景，三步成型。', workflowLead: '選擇位置，生成影像上下文，並進入可三維化的站點視圖。', contactTitle: '作為獨立 RE8CH 子產品被看見。' },
  es: { ...base, title: 'Any Site on Earth | RE8CH', description: 'Convierte cualquier coordenada en un workspace geoespacial con imágenes y escena 3D ligera.', workflow: 'Flujo', features: 'Funciones', workspace: 'Workspace', contact: 'Contacto', eyebrow: 'Producto geoespacial', heading: 'Convierte cualquier coordenada en un workspace de sitio.', lead: 'Conecta imágenes satelitales, límites, coordenadas y una escena 3D ligera.', primary: 'Abrir workspace', secondary: 'Contactar RE8CH', workflowTitle: 'De coordenada a escena en tres pasos.', workflowLead: 'Elige un lugar, genera contexto y entra a la vista 3D.', contactTitle: 'Visible como subproducto independiente de RE8CH.' },
  ar: { ...base, heading: 'حوّل أي إحداثية إلى مساحة عمل جاهزة للمنتج.', lead: 'يربط المنتج صور الأقمار الصناعية والحدود والإحداثيات ومشهدا ثلاثي الأبعاد خفيفا.', primary: 'افتح مساحة العمل', secondary: 'اتصل بـ RE8CH' },
  hi: { ...base, heading: 'किसी भी coordinate को product-ready site workspace बनाएं.', lead: 'Satellite imagery, bounds, coordinates और lightweight 3D scene को एक workspace में जोड़ता है.', primary: 'Workspace खोलें', secondary: 'RE8CH से संपर्क' },
  'pt-BR': { ...base, heading: 'Transforme qualquer coordenada em um workspace de site.', lead: 'Conecta imagens, limites, coordenadas e cena 3D leve em uma superfície localizada.', primary: 'Abrir workspace', secondary: 'Contatar RE8CH' },
  bn: { ...base, heading: 'যে কোনো coordinate-কে product-ready site workspace বানান।', lead: 'Satellite imagery, bounds, coordinates ও lightweight 3D scene একসাথে আনে।', primary: 'Workspace খুলুন', secondary: 'RE8CH-এ যোগাযোগ' },
  ru: { ...base, heading: 'Преобразуйте любую координату в site workspace.', lead: 'Соединяет спутниковые снимки, границы, координаты и легкую 3D-сцену.', primary: 'Открыть workspace', secondary: 'Связаться с RE8CH' },
  ja: { ...base, heading: '任意の座標を製品向けサイトワークスペースへ。', lead: '衛星画像、範囲、座標、軽量 3D シーンを一つの画面に接続します。', primary: 'ワークスペースを開く', secondary: 'RE8CH に連絡' },
  fr: { ...base, heading: 'Transformez toute coordonnée en workspace de site.', lead: 'Relie images satellite, limites, coordonnées et scène 3D légère.', primary: 'Ouvrir le workspace', secondary: 'Contacter RE8CH' },
  de: { ...base, heading: 'Machen Sie jede Koordinate zum Site-Workspace.', lead: 'Verbindet Satellitenbilder, Grenzen, Koordinaten und eine leichte 3D-Szene.', primary: 'Workspace öffnen', secondary: 'RE8CH kontaktieren' },
  ko: { ...base, heading: '어떤 좌표든 제품형 사이트 워크스페이스로 만드세요.', lead: '위성 이미지, 범위, 좌표, 가벼운 3D 장면을 연결합니다.', primary: '워크스페이스 열기', secondary: 'RE8CH 문의' },
  id: { ...base, heading: 'Ubah koordinat apa pun menjadi workspace situs.', lead: 'Menghubungkan citra satelit, batas, koordinat, dan scene 3D ringan.', primary: 'Buka workspace', secondary: 'Hubungi RE8CH' },
  tr: { ...base, heading: 'Her koordinatı site workspace’e dönüştürün.', lead: 'Uydu görüntüsü, sınırlar, koordinatlar ve hafif 3D sahneyi bağlar.', primary: 'Workspace aç', secondary: 'RE8CH ile iletişim' },
  vi: { ...base, heading: 'Biến mọi tọa độ thành workspace địa điểm.', lead: 'Kết nối ảnh vệ tinh, bounds, tọa độ và scene 3D nhẹ.', primary: 'Mở workspace', secondary: 'Liên hệ RE8CH' },
  it: { ...base, heading: 'Trasforma ogni coordinata in un workspace sito.', lead: 'Collega immagini satellitari, limiti, coordinate e scena 3D leggera.', primary: 'Apri workspace', secondary: 'Contatta RE8CH' },
  fa: { ...base, heading: 'هر مختصات را به workspace سایت آماده محصول تبدیل کنید.', lead: 'تصاویر ماهواره‌ای، محدوده، مختصات و صحنه سه‌بعدی سبک را وصل می‌کند.', primary: 'باز کردن workspace', secondary: 'تماس با RE8CH' },
  ur: { ...base, heading: 'کسی بھی coordinate کو product-ready site workspace بنائیں۔', lead: 'Satellite imagery، bounds، coordinates اور lightweight 3D scene کو جوڑتا ہے۔', primary: 'Workspace کھولیں', secondary: 'RE8CH سے رابطہ' },
  th: { ...base, heading: 'เปลี่ยนพิกัดใดก็ได้เป็น site workspace', lead: 'เชื่อมภาพดาวเทียม ขอบเขต พิกัด และฉาก 3D น้ำหนักเบา', primary: 'เปิด workspace', secondary: 'ติดต่อ RE8CH' },
  pl: { ...base, heading: 'Zmień dowolną współrzędną w site workspace.', lead: 'Łączy obrazy satelitarne, granice, współrzędne i lekką scenę 3D.', primary: 'Otwórz workspace', secondary: 'Kontakt z RE8CH' },
  nl: { ...base, heading: 'Maak van elke coördinaat een site workspace.', lead: 'Verbindt satellietbeelden, grenzen, coördinaten en een lichte 3D-scene.', primary: 'Open workspace', secondary: 'Neem contact op' },
  sw: { ...base, heading: 'Geuza coordinate yoyote kuwa site workspace.', lead: 'Huunganisha picha za satelaiti, mipaka, coordinate na scene nyepesi ya 3D.', primary: 'Fungua workspace', secondary: 'Wasiliana na RE8CH' },
  ms: { ...base, heading: 'Tukar sebarang koordinat menjadi site workspace.', lead: 'Menghubungkan imej satelit, bounds, koordinat dan scene 3D ringan.', primary: 'Buka workspace', secondary: 'Hubungi RE8CH' },
  fil: { ...base, heading: 'Gawing site workspace ang kahit anong coordinate.', lead: 'Pinag-uugnay ang satellite imagery, bounds, coordinates, at magaang 3D scene.', primary: 'Buksan ang workspace', secondary: 'Kontakin ang RE8CH' },
  uk: { ...base, heading: 'Перетворіть будь-яку координату на site workspace.', lead: 'Поєднує супутникові знімки, межі, координати й легку 3D-сцену.', primary: 'Відкрити workspace', secondary: 'Зв’язатися з RE8CH' },
  he: { ...base, heading: 'הפכו כל קואורדינטה ל-site workspace.', lead: 'מחבר תמונות לוויין, גבולות, קואורדינטות וסצנת 3D קלה.', primary: 'פתחו workspace', secondary: 'צרו קשר עם RE8CH' },
};
