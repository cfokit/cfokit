// The few icons the components need, drawn as the design system's README asks: a 1.5px stroke
// in the color of the text beside it, with the mark's square ends and right angles. No icon set
// is chosen; add one here only where a word will not do.

interface IconProps {
  size?: 16 | 24;
  className?: string;
}

function Icon({ size = 16, className, d }: IconProps & { d: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="square"
      strokeLinejoin="miter"
      aria-hidden="true"
      className={["shrink-0", className].filter(Boolean).join(" ")}
    >
      <path d={d} />
    </svg>
  );
}

export function CheckIcon(props: IconProps) {
  return <Icon {...props} d="M3.5 8.25 L6.75 11.5 L12.5 4.5" />;
}

export function FileIcon(props: IconProps) {
  return <Icon {...props} d="M4 2 H9.25 L12 4.75 V14 H4 Z M9.25 2 V4.75 H12" />;
}
