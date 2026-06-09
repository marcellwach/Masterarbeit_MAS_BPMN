/**
 * Root-Layout – gemeinsames HTML-Grundgerüst für alle Seiten.
 *
 * Lädt die Geist-Schriftfamilie (Variable Fonts: GeistVF + GeistMonoVF) und
 * setzt globale CSS-Klassen. `overflow-hidden` verhindert Doppel-Scrollbars,
 * da alle Seiten ein `fixed inset-0`-Layout verwenden.
 *
 * Metadaten:
 *   title:       "MAS BPMN Generator" (erscheint im Browser-Tab)
 *   description: Für Suchmaschinen und OpenGraph-Previews
 */

import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";

const geistSans = localFont({
  src: "./fonts/GeistVF.woff",
  variable: "--font-geist-sans",
  weight: "100 900",
});
const geistMono = localFont({
  src: "./fonts/GeistMonoVF.woff",
  variable: "--font-geist-mono",
  weight: "100 900",
});

export const metadata: Metadata = {
  title: "MAS BPMN Generator",
  description: "Multi-Agenten-System zur KI-gestützten BPMN-Generierung",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased h-full overflow-hidden`}
      >
        {children}
      </body>
    </html>
  );
}
