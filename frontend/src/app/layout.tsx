import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TenderIQ",
  description: "Intelligent Procurement Platform",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
