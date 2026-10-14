import "./globals.css";
import type { Metadata } from "next";
export const metadata: Metadata = {
  title: "Horário Inteligente",
  description: "Gestão de organizações, escolas, docentes e disponibilidades",
};
export default function RootLayout({ children }: Readonly<{children: React.ReactNode}>) {
  return <html lang="pt-BR"><body>{children}</body></html>;
}
