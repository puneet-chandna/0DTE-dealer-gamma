import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import { QueryProvider } from '@/providers/QueryProvider';

const inter = Inter({
  variable: '--font-inter',
  subsets: ['latin'],
  display: 'swap',
});

export const metadata: Metadata = {
  title: '0DTE GEX Monitor | Dealer Gamma Exposure Dashboard',
  description:
    'Real-time monitoring of Dealer Gamma Exposure (GEX) for SPX 0DTE options. Track Net GEX, Zero Gamma Level, and market regimes.',
  keywords: [
    '0DTE',
    'options',
    'gamma exposure',
    'GEX',
    'SPX',
    'dealer positioning',
    'zero gamma',
    'volatility',
  ],
  authors: [{ name: '0DTE GEX Team' }],
  openGraph: {
    title: '0DTE GEX Monitor',
    description: 'Real-time Dealer Gamma Exposure Analysis',
    type: 'website',
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className={`${inter.variable} font-sans antialiased`}
        suppressHydrationWarning
      >
        <QueryProvider>{children}</QueryProvider>
      </body>
    </html>
  );
}
