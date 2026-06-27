import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "divbr — renda passiva na B3",
  description:
    "Inteligência de renda passiva na B3 (ações e FIIs) a partir de dados oficiais da CVM. " +
    "Isto paga, e vai continuar pagando?",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
