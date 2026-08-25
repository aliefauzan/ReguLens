import type { Metadata } from "next";
import "./globals.css";
import NavBar from "./_ui/NavBar";

export const metadata: Metadata = {
  title: "ReguLens",
  description:
    "Check whether your product is allowed to be sold in each market, and get told the moment a new rule changes the answer.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      {/* pb-24 leaves room for the mobile tab bar; the desktop nav is sticky. */}
      <body className="min-h-screen pb-24 sm:pb-0">
        <NavBar />
        {children}
      </body>
    </html>
  );
}
