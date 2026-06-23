import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Cramly",
  description: "AI study companion for notes, quizzes, flashcards, and exam prep",
  icons: {
    icon: "/cramly-logo.png",
    apple: "/cramly-logo.png"
  }
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
