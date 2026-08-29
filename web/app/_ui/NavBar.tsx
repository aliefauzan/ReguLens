"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { COUNTS_CHANGED, listClauses, listConflicts } from "@/lib/api";

// HIG: a tab bar on small screens, a translucent navigation bar on large ones.
// Labels are tasks, not nouns from the data model — "Add rules", not "Ingest".
type Counted = "conflicts" | "review";

const TABS: {
  href: string;
  label: string;
  glyph: string;
  testId: string;
  count?: Counted;
  // Five labels do not fit across a phone. The reference page is the one that
  // can be reached from the pages that mention it instead of costing a tab.
  onPhone: boolean;
}[] = [
  { href: "/", label: "Products", glyph: "▤", testId: "nav-products", onPhone: true },
  { href: "/rules", label: "Rules", glyph: "▦", testId: "nav-rules", onPhone: false },
  // The watch list is the difference between "a checker" and "a monitor", so it
  // gets a tab rather than living behind a link on another page. Off the phone
  // bar for the same reason the reference page is: five labels do not fit, and
  // this one is set up once and then read occasionally.
  { href: "/sources", label: "Watching", glyph: "◎", testId: "nav-sources", onPhone: false },
  { href: "/documents/new", label: "Add rules", glyph: "＋", testId: "nav-add-rules", onPhone: true },
  {
    href: "/conflicts",
    label: "Disagreements",
    glyph: "⚖",
    testId: "nav-conflicts",
    count: "conflicts",
    onPhone: true,
  },
  { href: "/review", label: "To check", glyph: "☑", testId: "nav-review", count: "review", onPhone: true },
];

export default function NavBar() {
  const pathname = usePathname();
  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  // Work waiting behind a tab is invisible until someone clicks it, which
  // means nobody clicks it. Re-read on navigation, because accepting a clause
  // or resolving a conflict changes these numbers.
  const [counts, setCounts] = useState<Record<Counted, number>>({ conflicts: 0, review: 0 });
  useEffect(() => {
    let cancelled = false;
    function read() {
      Promise.all([
        listClauses({ status: "needs_review" }).then((r) => r.clauses.length).catch(() => 0),
        listConflicts().then((r) => r.conflicts.length).catch(() => 0),
      ]).then(([review, conflicts]) => {
        if (!cancelled) setCounts({ review, conflicts });
      });
    }
    read();
    // Accepting or ignoring a clause happens without leaving the page.
    window.addEventListener(COUNTS_CHANGED, read);
    return () => {
      cancelled = true;
      window.removeEventListener(COUNTS_CHANGED, read);
    };
  }, [pathname]);

  const badge = (tab: (typeof TABS)[number]) =>
    tab.count && counts[tab.count] > 0 ? counts[tab.count] : null;

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
                {badge(tab) !== null ? (
                  <span
                    className="ml-1.5 t-caption"
                    style={{
                      background: "var(--accent)",
                      color: "var(--accent-ink)",
                      borderRadius: 999,
                      padding: "1px 7px",
                      fontWeight: 600,
                    }}
                    data-testid={`${tab.testId}-count`}
                  >
                    {badge(tab)}
                  </span>
                ) : null}
              </Link>
            ))}
          </div>
        </nav>
      </header>

      {/* Mobile tab bar */}
      <nav className="material fixed inset-x-0 bottom-0 z-30 grid grid-cols-4 border-t sm:hidden"
           style={{ borderColor: "var(--separator)" }}>
        {TABS.filter((tab) => tab.onPhone).map((tab) => (
          <Link
            key={tab.href}
            href={tab.href}
            data-testid={`${tab.testId}-mobile`}
            aria-current={isActive(tab.href) ? "page" : undefined}
            className="flex flex-col items-center justify-center gap-1 py-2 t-caption"
            style={{ color: isActive(tab.href) ? "var(--accent)" : "var(--secondary)", minHeight: "var(--tap)" }}
          >
            <span aria-hidden="true" className="relative text-lg leading-none">
              {tab.glyph}
              {badge(tab) !== null ? (
                <span
                  className="absolute -right-3 -top-1 t-caption"
                  style={{
                    background: "var(--accent)",
                    color: "var(--accent-ink)",
                    borderRadius: 999,
                    padding: "0 5px",
                    fontWeight: 600,
                  }}
                  data-testid={`${tab.testId}-count-mobile`}
                >
                  {badge(tab)}
                </span>
              ) : null}
            </span>
            <span className="w-full truncate px-0.5 text-center" style={{ fontSize: 11 }}>
              {tab.label}
            </span>
          </Link>
        ))}
      </nav>
    </>
  );
}
