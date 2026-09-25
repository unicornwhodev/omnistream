import type { CSSProperties } from "react";
export type IconName =
  | "settings"
  | "power"
  | "scene"
  | "play"
  | "pause"
  | "stop"
  | "monitor"
  | "debug"
  | "refresh"
  | "expand"
  | "back"
  | "next"
  | "reset"
  | "offline"
  | "info"
  | "close"
  | "check";
const paths: Record<IconName, string> = {
  settings: "M4 7h16M4 17h16M8 4v6M16 14v6",
  power: "M12 3v8M7 5a8 8 0 1 0 10 0",
  scene: "M12 3 3 8v9l9 5 9-5V8l-9-5ZM3 8l9 5 9-5M12 13v9",
  play: "m8 5 11 7-11 7V5Z",
  pause: "M8 5v14M16 5v14",
  stop: "M6 6h12v12H6z",
  monitor: "M3 4h18v13H3zM8 21h8M12 17v4M6 11h3l2-4 3 7 2-3h2",
  debug:
    "M8 8h8v9a4 4 0 0 1-8 0V8ZM10 8V6a2 2 0 0 1 4 0v2M4 10h4M16 10h4M4 15h4M16 15h4M5 21l3-3M16 18l3 3",
  refresh: "M20 10a8 8 0 1 0-1 8M20 4v6h-6",
  expand: "M8 3H3v5M16 3h5v5M21 16v5h-5M8 21H3v-5",
  back: "M5 5v14M18 5l-10 7 10 7V5Z",
  next: "M19 5v14M6 5l10 7-10 7V5Z",
  reset: "M4 10a8 8 0 1 1 1 8M4 4v6h6",
  offline: "M4 4h16v12H4zM8 20h8M12 16v4M9 8l6 4M15 8l-6 4",
  info: "M12 8h.01M12 11v6M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z",
  close: "m6 6 12 12M6 18 18 6",
  check: "m5 12 4 4L19 6",
};
export function Icon({
  name,
  className,
  style,
}: {
  name: IconName;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <svg
      className={className || "icon"}
      style={style}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.65"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name]} />
    </svg>
  );
}
