import type { ReactNode, SVGProps } from "react";

export type IconName =
  | "home"
  | "create"
  | "history"
  | "star"
  | "profile"
  | "image"
  | "video"
  | "arrow"
  | "wallet"
  | "bell"
  | "language"
  | "settings"
  | "support"
  | "check"
  | "download"
  | "share"
  | "repeat"
  | "upscale";

const paths: Record<IconName, ReactNode> = {
  home: (
    <>
      <path d="m3.5 10.8 8.5-7 8.5 7" />
      <path d="M5.8 9.4v10h12.4v-10M9.3 19.4v-5.8h5.4v5.8" />
    </>
  ),
  create: (
    <>
      <path d="M12 3.2v17.6M3.2 12h17.6" />
      <path d="M5.2 5.2h2.5M16.3 18.8h2.5" opacity=".55" />
    </>
  ),
  history: (
    <>
      <rect x="4" y="4" width="16" height="16" rx="2" />
      <path d="M8 8h8M8 12h8M8 16h5" />
    </>
  ),
  star: (
    <path d="m12 3.4 2.45 5 5.5.8-3.98 3.88.94 5.48L12 15.98l-4.91 2.58.94-5.48L4.05 9.2l5.5-.8L12 3.4Z" />
  ),
  profile: (
    <>
      <circle cx="12" cy="8.2" r="3.2" />
      <path d="M5.4 20c.5-4 2.7-6 6.6-6s6.1 2 6.6 6" />
    </>
  ),
  image: (
    <>
      <rect x="3.5" y="4.5" width="17" height="15" rx="2" />
      <circle cx="9" cy="9.5" r="1.5" />
      <path d="m5.5 17 4.1-4 2.7 2.5 2.3-2 3.9 3.5" />
    </>
  ),
  video: (
    <>
      <rect x="3.5" y="5.5" width="13" height="13" rx="2" />
      <path d="m16.5 10 4-2v8l-4-2M9.5 9v6l4-3-4-3Z" />
    </>
  ),
  arrow: <path d="M4 12h15M14 6l6 6-6 6" />,
  wallet: (
    <>
      <path d="M4 7.5h15.5v11H4a2 2 0 0 1-2-2v-11a2 2 0 0 1 2-2h12.5" />
      <path d="M15 11h6v4h-6a2 2 0 0 1 0-4Z" />
    </>
  ),
  bell: (
    <>
      <path d="M6 17h12l-1.4-2.2V10a4.6 4.6 0 0 0-9.2 0v4.8L6 17Z" />
      <path d="M10 20h4" />
    </>
  ),
  language: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M3.5 12h17M12 3c2.2 2.5 3.3 5.5 3.3 9S14.2 18.5 12 21c-2.2-2.5-3.3-5.5-3.3-9S9.8 5.5 12 3Z" />
    </>
  ),
  settings: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="m19 13.7 1.4 1-.9 2.2-1.7-.2a8 8 0 0 1-1.6 1.6l.2 1.7-2.2.9-1-1.4a8 8 0 0 1-2.4 0l-1 1.4-2.2-.9.2-1.7a8 8 0 0 1-1.6-1.6l-1.7.2-.9-2.2 1.4-1a8 8 0 0 1 0-2.4l-1.4-1 .9-2.2 1.7.2a8 8 0 0 1 1.6-1.6l-.2-1.7 2.2-.9 1 1.4a8 8 0 0 1 2.4 0l1-1.4 2.2.9-.2 1.7a8 8 0 0 1 1.6 1.6l1.7-.2.9 2.2-1.4 1a8 8 0 0 1 0 2.4Z" />
    </>
  ),
  support: (
    <>
      <path d="M4 14v-2a8 8 0 0 1 16 0v2" />
      <path d="M4 13h2.5v5H5a1 1 0 0 1-1-1v-4ZM20 13h-2.5v5H19a1 1 0 0 0 1-1v-4ZM17.5 18c0 1.7-1.2 2.5-3.5 2.5" />
    </>
  ),
  check: <path d="m4.5 12.5 4.5 4 10.5-10" />,
  download: (
    <>
      <path d="M12 3v12M7.5 10.5 12 15l4.5-4.5M4 20h16" />
    </>
  ),
  share: (
    <>
      <circle cx="18" cy="5" r="2.2" />
      <circle cx="6" cy="12" r="2.2" />
      <circle cx="18" cy="19" r="2.2" />
      <path d="m8 11 8-5M8 13l8 5" />
    </>
  ),
  repeat: (
    <>
      <path d="M20 7h-9a6 6 0 0 0-6 6v1" />
      <path d="m17 4 3 3-3 3M4 17h9a6 6 0 0 0 6-6v-1M7 20l-3-3 3-3" />
    </>
  ),
  upscale: (
    <>
      <path d="M9 4H4v5M15 4h5v5M9 20H4v-5M15 20h5v-5" />
      <path d="m4 9 5-5M20 9l-5-5M4 15l5 5M20 15l-5 5" />
    </>
  ),
};

export function Icon({
  name,
  ...props
}: SVGProps<SVGSVGElement> & { name: IconName }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      {paths[name]}
    </svg>
  );
}
