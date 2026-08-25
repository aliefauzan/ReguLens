"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

// HIG: a tab bar on small screens, a translucent navigation bar on large ones.
// Labels are tasks, not nouns from the data model — "Add rules", not "Ingest".
const TABS = [
  { href: "/", label: "Products", glyph: "▤", testId: "nav-products" },
  { href: "/documents/new", label: "Add rules", glyph: "＋", testId: "nav-add-rules" },
  { href: "/conflicts", label: "Disagreements", glyph: "⚖", testId: "nav-conflicts" },
  { href: "/review", label: "To check", glyph: "☑", testId: "nav-review" },
];

export default function NavBar() {
  const pathname = usePathname();
  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <>
      {/* Desktop / tablet */}
      <header className="material hairline sticky top-0 z-30 hidden sm:block">
        <nav className="mx-auto flex h-14 max-w-5xl items-center gap-6 px-6">
          <Link href="/" className="t-headline tracking-tight">
            ReguLens
          </Link>
          <div className="flex items-center gap-1">
            {TABS.map((tab) => (
              <Link
                key={tab.href}
                href={tab.href}
                data-testid={tab.testId}
                aria-current={isActive(tab.href) ? "page" : undefined}
                className="rounded-[10px] px-3 py-1.5 t-subhead"
                style={
                  isActive(tab.href)
                    ? { background: "var(--fill)", fontWeight: 600 }
                    : { color: "var(--secondary)" }
                }
              >
                {tab.label}
              </Link>
            ))}
          </div>
        </nav>
      </header>

      {/* Mobile tab bar */}
      <nav className="material fixed inset-x-0 bottom-0 z-30 grid grid-cols-4 border-t sm:hidden"
           style={{ borderColor: "var(--separator)" }}>
        {TABS.map((tab) => (
          <Link
            key={tab.href}
            href={tab.href}
            data-testid={`${tab.testId}-mobile`}
            aria-current={isActive(tab.href) ? "page" : undefined}
            className="flex flex-col items-center justify-center gap-1 py-2 t-caption"
            style={{ color: isActive(tab.href) ? "var(--accent)" : "var(--secondary)", minHeight: "var(--tap)" }}
          >
            <span aria-hidden="true" className="text-lg leading-none">{tab.glyph}</span>
            {tab.label}
          </Link>
        ))}
      </nav>
    </>
  );
}
