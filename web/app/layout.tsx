import type { Metadata } from "next";
import Link from "next/link";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin", "latin-ext"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin", "latin-ext"] });

export const metadata: Metadata = {
  title: "Ártrend-figyelő — Steam játékok",
  description:
    "Napi árkövetés 15 Steam-játékra, grafikonnal és AI-generált vásárlási verdikttel.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="hu"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col font-sans">
        <header className="border-b border-border-base">
          <div className="mx-auto w-full max-w-6xl px-5 py-4 flex items-baseline justify-between gap-4">
            <Link href="/" className="group">
              <span className="text-[15px] font-semibold tracking-tight">
                Ártrend-figyelő
              </span>
              <span className="ml-2 text-[13px] text-text-muted group-hover:text-text">
                Steam
              </span>
            </Link>
            <a
              href="https://github.com/"
              className="text-[13px] text-text-muted hover:text-text underline underline-offset-4 decoration-border-strong"
            >
              Forráskód
            </a>
          </div>
        </header>

        <main className="flex-1">{children}</main>

        <footer className="border-t border-border-base mt-16">
          <div className="mx-auto w-full max-w-6xl px-5 py-6 text-[13px] text-text-muted leading-relaxed">
            <p>
              Portfólió-projekt. Az árak a Steam publikus store API-jából
              származnak, címenként napi egy lekéréssel. Tájékoztató jellegűek —
              vásárlás előtt mindig ellenőrizd a boltban. Nem áll kapcsolatban a
              Valve Corporationnel.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
