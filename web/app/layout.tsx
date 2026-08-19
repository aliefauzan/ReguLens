import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ReguLens",
  description: "Cross-jurisdiction regulatory compliance for food and beverage products",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
