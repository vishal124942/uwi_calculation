import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "UWI Pipeline Explorer",
  description:
    "Step-by-step view of the self-employed income reconstruction engine: every transaction, calculation and decision from bank statement to underwriting income.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // Browser extensions (dark mode, translators, password managers) add attributes to <html> before hydration.
    <html lang="en" suppressHydrationWarning className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full font-sans">{children}</body>
    </html>
  );
}
