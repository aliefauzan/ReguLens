"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { health } from "@/lib/api";

/**
 * The bar above the work surface.
 *
 * It answers two things and nothing else: is the service actually answering
 * right now, and what are the two actions worth having on every page. The page
 * title is not repeated here — each page states its own, and chrome that
 * echoes the heading underneath it is a row of pixels spent twice.
 */
export default function TopBar() {
  const pathname = usePathname();
  const [reachable, setReachable] = useState<boolean | null>(null);

  // Re-checked on navigation rather than polled: an operator wants to know the
  // service was up when this page loaded, and a timer would spend a request
  // every few seconds to say the same thing.
  useEffect(() => {
    let cancelled = false;
    health()
      .then(() => !cancelled && setReachable(true))
      .catch(() => !cancelled && setReachable(false));
    return () => {
      cancelled = true;
    };
  }, [pathname]);

  const tone =
    reachable === null ? "var(--tertiary)" : reachable ? "var(--good)" : "var(--danger)";

  return (
    <header className="topbar material" data-testid="topbar">
      <div className="mx-auto flex h-full max-w-[1400px] items-center gap-3 px-5 sm:px-7">
        {/* On a phone the rail is gone, so the mark comes back here. */}
        <Link href="/" className="t-headline tracking-tight lg:hidden">
          ReguLens
        </Link>

        <span className="flex items-center gap-2" data-testid="service-status">
          <span className={`dot ${reachable ? "dot-live" : ""}`} style={{ color: tone }} />
          <span className="t-caption hidden sm:inline">
            {reachable === null
              ? "Checking the service…"
              : reachable
                ? "Service connected"
                : "Service unreachable"}
          </span>
        </span>

        <div className="ml-auto flex items-center gap-2">
          <Link href="/documents/new" className="btn btn-secondary btn-small" data-testid="topbar-add-rules">
            Add rules
          </Link>
          <Link href="/products/new" className="btn btn-primary btn-small" data-testid="new-product-link">
            Add a product
          </Link>
        </div>
      </div>
    </header>
  );
}
