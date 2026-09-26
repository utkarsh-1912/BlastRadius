import type { Metadata } from "next";
import "./globals.css";
import SiteHeader from "@/components/SiteHeader";

export const metadata: Metadata = {
  title: "Blast Radius",
  description: "AWS IAM access-review agent",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-50 antialiased">
        <SiteHeader />
        <div className="mx-auto max-w-6xl">{children}</div>
      </body>
    </html>
  );
}
