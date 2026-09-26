import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Blast Radius",
  description: "AWS IAM access-review agent",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
