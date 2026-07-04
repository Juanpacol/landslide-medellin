import type { Metadata } from 'next'
import { Bricolage_Grotesque, Hanken_Grotesk } from 'next/font/google'
import './globals.css'

const bricolage = Bricolage_Grotesque({
  variable: '--font-bricolage',
  subsets: ['latin'],
  weight: ['400', '600', '700', '800'],
})

const hanken = Hanken_Grotesk({
  variable: '--font-hanken',
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
})

export const metadata: Metadata = {
  title: 'Sistema de Análisis de Riesgo de Deslizamientos - Medellín',
  description: 'Dashboard de monitoreo y análisis de riesgo de deslizamientos para las comunas de Medellín, Colombia',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="es" className={`${bricolage.variable} ${hanken.variable}`}>
      <body className="font-sans bg-background">
        {children}
      </body>
    </html>
  )
}
