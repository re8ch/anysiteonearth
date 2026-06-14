import { brandAssetUrl } from '@/lib/brandAssets';

type AnysiteLogoMotionProps = {
  className?: string;
  label?: string;
  motion?: 'enter' | 'idle' | 'launch' | 'loader' | 'pulse' | 'reveal';
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl';
  variant?: 'outline' | 'flat' | 'inverse';
};

export default function AnysiteLogoMotion({
  className = '',
  label = 'Any Site on Earth logo',
  motion = 'idle',
  size = 'md',
  variant = 'outline',
}: AnysiteLogoMotionProps) {
  const iconPath =
    variant === 'flat'
      ? '/PRODUCTS/anysiteonearth/SVG/icon-flat.svg'
      : variant === 'inverse'
        ? '/PRODUCTS/anysiteonearth/SVG/icon-inverse.svg'
        : '/PRODUCTS/anysiteonearth/SVG/icon.svg';

  return (
    <img
      className={`anysite-logo anysite-logo-${size} anysite-logo-${variant} anysite-logo-${motion} ${className}`}
      src={brandAssetUrl(iconPath)}
      alt={label}
      decoding="async"
    />
  );
}
