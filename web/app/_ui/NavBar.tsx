"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { COUNTS_CHANGED, listClauses, listConflicts } from "@/lib/api";
import Icon, { type IconName } from "./Icon";

// A console has a rail, not a header: the destinations stay on screen while
// the work scrolls, and a queue that is filling up is visible from every page
// instead of only from the page it belongs to.
//
// Below the rail's breakpoint the same destinations become a bottom tab bar,
// because a phone has no left margin to spare.
//
// Labels are tasks, not nouns from the data model — "Add rules", not "Ingest".
type Counted = "conflicts" | "review";

const TABS: {
  href: string;
  label: string;
  icon: IconName;
  testId: string;
  count?: Counted;
  // Five labels do not fit across a phone. The reference page is the one that
  // can be reached from the pages that mention it instead of costing a tab.
  onPhone: boolean;
}[] = [
  { href: "/", label: "Products", icon: "products", testId: "nav-products", onPhone: true },
  { href: "/rules", label: "Rules", icon: "rules", testId: "nav-rules", onPhone: false },
  { href: "/documents/new", label: "Add rules", icon: "add", testId: "nav-add-rules", onPhone: true },
  {
    href: "/conflicts",
    label: "Disagreements",
    icon: "conflicts",
    testId: "nav-conflicts",
    count: "conflicts",
    onPhone: true,
  },
  { href: "/review", label: "To check", icon: "review", testId: "nav-review", count: "review", onPhone: true },
];

export default function NavBar() {
  const pathname = usePathname();
  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  // Work waiting behind a destination is invisible until someone clicks it,
  // which means nobody clicks it. Re-read on navigation, because accepting a
  // clause or resolving a conflict changes these numbers.
  const [counts, setCounts] = useState<Record<Counted, number>>({ conflicts: 0, review: 0 });

  useEffect(() => {
    let cancelled = false;
    function read() {
      Promise.all([
        listClauses({ status: "needs_review" }).then((r) => r.clauses.length),
        listConflicts().then((r) => r.conflicts.length),
      ])
        .then(([review, conflicts]) => {
          if (!cancelled) setCounts({ review, conflicts });
        })
        // A queue we cannot read is not a queue of zero, but the rail is not
        // where that gets reported: the top bar says the service is down.
        .catch(() => {});
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
      {/* Rail — desktop and large tablet */}
      <aside className="rail z-30 hidden flex-col lg:flex" data-testid="nav-rail">
        <div className="flex h-14 items-center gap-2 px-4" style={{ borderBottom: "1px solid var(--separator)" }}>
          <Link href="/" className="flex items-center gap-2.5">
            <span
              className="flex h-7 w-7 items-center justify-center rounded-[7px]"
              style={{ background: "var(--accent)", color: "var(--accent-ink)" }}
              aria-hidden="true"
            >
              <svg width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="8.5" cy="8.5" r="4.8" />
                <path d="m12.2 12.2 4 4M6.4 8.5h4.2" />
              </svg>
            </span>
            <span className="t-headline tracking-tight">ReguLens</span>
          </Link>
        </div>

        <nav className="flex-1 overflow-y-auto p-3">
          <p className="t-eyebrow px-2 pb-2 pt-1">Workspace</p>
          <div className="grid gap-0.5">
            {TABS.map((tab) => (
              <Link
                key={tab.href}
                href={tab.href}
                data-testid={tab.testId}
                aria-current={isActive(tab.href) ? "page" : undefined}
                className="nav-item"
              >
                <span className="nav-glyph">
                  <Icon name={tab.icon} size={17} />
                </span>
                <span className="truncate">{tab.label}</span>
                {badge(tab) !== null ? (
                  <span className="nav-count" data-testid={`${tab.testId}-count`}>
                    {badge(tab)}
                  </span>
                ) : null}
              </Link>
            ))}
          </div>
        </nav>

      </aside>

      {/* Tab bar — phone and small tablet */}
      <nav
        className="material fixed inset-x-0 bottom-0 z-30 grid grid-cols-4 border-t lg:hidden"
        style={{ borderColor: "var(--separator)" }}
      >
        {TABS.filter((tab) => tab.onPhone).map((tab) => (
          <Link
            key={tab.href}
            href={tab.href}
            data-testid={`${tab.testId}-mobile`}
            aria-current={isActive(tab.href) ? "page" : undefined}
            className="flex flex-col items-center justify-center gap-1 py-2"
            style={{ color: isActive(tab.href) ? "var(--accent)" : "var(--secondary)", minHeight: "var(--tap)" }}
          >
            <span className="relative inline-flex leading-none">
              <Icon name={tab.icon} size={20} />
              {badge(tab) !== null ? (
                <span
                  className="absolute -right-2.5 -top-1.5"
                  style={{
                    background: "var(--accent)",
                    color: "var(--accent-ink)",
                    borderRadius: 999,
                    padding: "0 5px",
                    fontSize: 10,
                    fontWeight: 650,
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
