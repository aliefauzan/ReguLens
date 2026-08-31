// One stroke weight, one grid, one file. Icons are drawn inline rather than
// pulled from a package: the set is eight glyphs, and a dependency that ships
// a thousand of them would cost more to keep alive than it saves.
//
// Every icon is decorative — the label next to it carries the meaning — so
// they are all aria-hidden and never the only thing naming a control.

export type IconName =
  | "products"
  | "rules"
  | "add"
  | "conflicts"
  | "review"
  | "arrow"
  | "search"
  | "activity"
  | "watching";

const PATHS: Record<IconName, React.ReactNode> = {
  // A box on a shelf: the product.
  products: (
    <>
      <path d="M3 7.5 10 4l7 3.5v5L10 16l-7-3.5v-5Z" />
      <path d="M3 7.5 10 11l7-3.5M10 11v5" />
    </>
  ),
  // A page with lines: the regulation as it was written.
  rules: (
    <>
      <path d="M5 3h6l4 4v10a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" />
      <path d="M11 3v4h4M7 11h6M7 14h4" />
    </>
  ),
  add: <path d="M10 4.5v11M4.5 10h11" />,
  // Scales: two limits weighed against each other.
  conflicts: (
    <>
      <path d="M10 4v13M5 7h10M4 17h12" />
      <path d="M5 7 3 12h4L5 7ZM15 7l-2 5h4l-2-5Z" />
    </>
  ),
  // A ticked box: the queue a person has to clear.
  review: (
    <>
      <path d="M4 4.8A.8.8 0 0 1 4.8 4h10.4a.8.8 0 0 1 .8.8v10.4a.8.8 0 0 1-.8.8H4.8a.8.8 0 0 1-.8-.8V4.8Z" />
      <path d="m7 10 2.2 2.2L13.5 8" />
    </>
  ),
  arrow: <path d="M4 10h11m-4.5-4.5L15 10l-4.5 4.5" />,
  search: (
    <>
      <circle cx="9" cy="9" r="5" />
      <path d="m13 13 3.5 3.5" />
    </>
  ),
  // A pulse line: something changed without being asked.
  activity: <path d="M2.5 10h3.2l2-5 3.4 10 2.2-5h4.2" />,
  // A radar sweep: an address being re-read on a schedule, whether or not
  // anything has come back from it yet.
  watching: (
    <>
      <circle cx="10" cy="10" r="6.5" />
      <circle cx="10" cy="10" r="2.4" />
      <path d="M10 3.5v2.2M10 14.3v2.2M3.5 10h2.2M14.3 10h2.2" />
    </>
  ),
};

export default function Icon({
  name,
  size = 18,
  className,
}: {
  name: IconName;
  size?: number;
  className?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={className}
    >
      {PATHS[name]}
    </svg>
  );
}
