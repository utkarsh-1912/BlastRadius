import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Sidebar from "@/components/Sidebar";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: "Blast Radius",
  description: "AWS IAM access-review agent",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="flex h-screen overflow-hidden bg-slate-50 font-sans antialiased">
        <Sidebar />
        <div className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-5xl">{children}</div>
        </div>
      </body>
    </html>
  );
}
