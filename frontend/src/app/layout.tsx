import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TenderIQ — Procurement Intelligence, Built Around Evidence",
  description: "Structure tender requirements, verify vendor evidence, and enable explainable procurement decisions.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
