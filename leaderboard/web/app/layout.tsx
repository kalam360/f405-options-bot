import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "F405 Options Bot — Live Leaderboard",
  description:
    "Live risk-adjusted standings for the IBA F405 BTC weekly-options bot competition.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
