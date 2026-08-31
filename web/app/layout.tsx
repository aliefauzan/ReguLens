import type { Metadata } from "next";
import "./globals.css";
import NavBar from "./_ui/NavBar";
import TopBar from "./_ui/TopBar";

export const metadata: Metadata = {
  title: "ReguLens",
  description:
    "Check whether your product is allowed to be sold in each market, and get told the moment a new rule changes the answer.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        {/* Fixed rail on large screens, bottom tab bar below that. */}
        <NavBar />
        {/* The work surface: everything that scrolls lives here. pb-24 leaves
            room for the mobile tab bar; the rail needs no room reserved
            because .shell-main pads for it at the same breakpoint. */}
        <div className="shell-main pb-24 lg:pb-0">
          <TopBar />
          {children}
        </div>
      </body>
    </html>
  );
}
