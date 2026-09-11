import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Clip AI Beta",
  description: "Local-first AI clipping, reframing, captions and ready-to-post Shorts",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
