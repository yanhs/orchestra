import type { Metadata } from 'next';
import { Toaster } from 'react-hot-toast';
import './globals.css';

export const metadata: Metadata = {
  title: 'TextCraft AI — Transform Your Text with AI',
  description: 'AI-powered text processing: summarize, rewrite, and SEO optimize your content in seconds. Free tier available.',
  keywords: ['AI text processing', 'summarizer', 'rewriter', 'SEO optimizer', 'TextCraft'],
  openGraph: {
    title: 'TextCraft AI — Transform Your Text with AI',
    description: 'Summarize, rewrite, and SEO optimize your content with AI.',
    type: 'website',
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-surface-900 text-slate-100 antialiased">
        {/* Background orbs */}
        <div className="fixed inset-0 pointer-events-none overflow-hidden z-0" aria-hidden="true">
          <div className="absolute -top-40 -left-40 w-[600px] h-[600px] rounded-full bg-brand-500/[0.07] blur-[100px] animate-pulse-slow" />
          <div className="absolute top-1/3 -right-32 w-[500px] h-[500px] rounded-full bg-purple-500/[0.05] blur-[100px] animate-pulse-slow" style={{ animationDelay: '1.5s' }} />
          <div className="absolute -bottom-40 left-1/3 w-[400px] h-[400px] rounded-full bg-brand-400/[0.04] blur-[100px] animate-pulse-slow" style={{ animationDelay: '3s' }} />
        </div>

        <div className="relative z-10">
          {children}
        </div>

        <Toaster
          position="bottom-center"
          toastOptions={{
            style: {
              background: 'rgba(30, 41, 59, 0.95)',
              color: '#f1f5f9',
              border: '1px solid rgba(148, 163, 184, 0.15)',
              backdropFilter: 'blur(20px)',
              borderRadius: '12px',
              fontSize: '14px',
            },
            success: {
              iconTheme: {
                primary: '#0ea5e9',
                secondary: '#f1f5f9',
              },
            },
            error: {
              iconTheme: {
                primary: '#f87171',
                secondary: '#f1f5f9',
              },
            },
          }}
        />
      </body>
    </html>
  );
}
