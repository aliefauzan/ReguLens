import type { Metadata } from "next";
import Link from "next/link";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({ variable: "--font-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "ReguLens",
  description: "Cross-jurisdiction regulatory compliance for food and beverage products",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${geistSans.variable} ${geistMono.variable}`}>
        <nav className="h-14 border-b px-6 flex items-center gap-8">
          <span className="font-semibold tracking-tight">ReguLens</span>
          <div className="flex gap-5 text-sm">
            <Link href="/" className="opacity-70 hover:opacity-100">Products</Link>
            <Link href="/documents/new" className="opacity-70 hover:opacity-100">Ingest</Link>
            <Link href="/conflicts" className="opacity-70 hover:opacity-100" data-testid="nav-conflicts">Conflicts</Link>
            <Link href="/review" className="opacity-70 hover:opacity-100" data-testid="nav-review">Review queue</Link>
          </div>
        </nav>
        {children}
      </body>
    </html>
  );
}
