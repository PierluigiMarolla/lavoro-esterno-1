const SIZE_CLASS = {
  14: "text-[14px]",
  15: "text-[15px]",
  16: "text-[16px]",
  18: "text-[18px]",
  20: "text-[20px]",
  24: "text-[24px]",
  28: "text-[28px]",
} as const;

export type IconSize = keyof typeof SIZE_CLASS;

// Wraps a locally bundled Material Symbols Outlined glyph without inline styles.
export default function Icon({
  name,
  className,
  size = 20,
}: {
  name: string;
  className?: string;
  size?: IconSize;
}) {
  return (
    <span className={cnIcon(SIZE_CLASS[size], className)} aria-hidden="true">
      {name}
    </span>
  );
}

function cnIcon(...classNames: Array<string | undefined>) {
  return ["material-symbols-outlined", ...classNames].filter(Boolean).join(" ");
}
