import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "NLP Leaderboard",
  description: "Course project submissions and leaderboard"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}

