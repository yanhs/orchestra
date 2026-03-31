'use client';

import { X, Zap, Check } from 'lucide-react';
import { useState } from 'react';
import toast from 'react-hot-toast';

interface UpgradeModalProps {
  open: boolean;
  onClose: () => void;
}

const features = [
  'Unlimited daily uses',
  'All 3 AI tools included',
  'Priority processing speed',
  'Early access to new tools',
  'Email support',
];

export default function UpgradeModal({ open, onClose }: UpgradeModalProps) {
  const [loading, setLoading] = useState(false);

  if (!open) return null;

  const handleUpgrade = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/stripe/checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });

      if (!res.ok) throw new Error('Failed to create checkout session');

      const data = await res.json();
      window.location.href = data.checkoutUrl;
    } catch {
      toast.error('Failed to start checkout. Please try again.');
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative glass rounded-2xl max-w-md w-full p-8 animate-slide-up">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-1 text-white/40 hover:text-white transition-colors"
          aria-label="Close"
        >
          <X className="w-5 h-5" />
        </button>

        <div className="text-center mb-6">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-amber-400/20 to-orange-500/20 flex items-center justify-center mx-auto mb-4">
            <Zap className="w-7 h-7 text-amber-400" />
          </div>
          <h2 className="text-2xl font-bold text-white mb-2">
            Upgrade to Pro
          </h2>
          <p className="text-white/60 text-sm">
            You&apos;ve used all 5 free uses today. Unlock unlimited access.
          </p>
        </div>

        <div className="space-y-3 mb-8">
          {features.map((feature) => (
            <div key={feature} className="flex items-center gap-3 text-sm">
              <div className="w-5 h-5 rounded-full bg-brand-500/20 flex items-center justify-center flex-shrink-0">
                <Check className="w-3 h-3 text-brand-400" />
              </div>
              <span className="text-white/80">{feature}</span>
            </div>
          ))}
        </div>

        <div className="text-center mb-6">
          <div className="flex items-baseline justify-center gap-1">
            <span className="text-4xl font-bold text-white">$9</span>
            <span className="text-white/40 text-sm">/month</span>
          </div>
        </div>

        <button
          onClick={handleUpgrade}
          disabled={loading}
          className="w-full btn-primary !py-3 text-base flex items-center justify-center gap-2 disabled:opacity-50"
        >
          {loading ? (
            <>
              <div className="w-4 h-4 rounded-full border-2 border-white/20 border-t-white animate-spin" />
              Redirecting...
            </>
          ) : (
            <>
              <Zap className="w-4 h-4" />
              Upgrade Now
            </>
          )}
        </button>

        <p className="text-center text-xs text-white/30 mt-4">
          Cancel anytime. Powered by Stripe.
        </p>
      </div>
    </div>
  );
}
