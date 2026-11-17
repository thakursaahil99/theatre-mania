import type { Metadata, Viewport } from "next";
import { Bebas_Neue, Outfit } from "next/font/google";

import { CustomCursor } from "@/components/layout/CustomCursor";
import { Footer } from "@/components/layout/Footer";
import { MobileNav } from "@/components/layout/MobileNav";
import { Navbar } from "@/components/layout/Navbar";
import { AuthProvider } from "@/components/providers/AuthProvider";
import { MorphProvider } from "@/components/providers/MorphProvider";
import { PreviewProvider } from "@/components/providers/PreviewProvider";
import { SmoothScroll } from "@/components/providers/SmoothScroll";

import "./globals.css";

const body = Outfit({ subsets: ["latin"], variable: "--font-body", display: "swap" });
const display = Bebas_Neue({ subsets: ["latin"], weight: "400", variable: "--font-display-face", display: "swap" });

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"),
  title: { default: "Theatre Mania — Stream timeless cinema", template: "%s · Theatre Mania" },
  description:
    "Stream public-domain classics free, with no ads. Discover trailers, cast and where to watch every other film legally.",
  openGraph: { type: "website", siteName: "Theatre Mania" },
};

export const viewport: Viewport = {
  themeColor: "#05060b",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${body.variable} ${display.variable}`}>
      <body className="min-h-svh overflow-x-clip bg-ink-950 antialiased">
        <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[200] focus:rounded-lg focus:bg-white focus:px-4 focus:py-2 focus:text-ink-950">
          Skip to content
        </a>
        <AuthProvider>
          <SmoothScroll>
            <MorphProvider>
              <PreviewProvider>
                <Navbar />
                <main id="main">{children}</main>
                <Footer />
                <MobileNav />
                <CustomCursor />
              </PreviewProvider>
            </MorphProvider>
          </SmoothScroll>
        </AuthProvider>
      </body>
    </html>
  );
}
