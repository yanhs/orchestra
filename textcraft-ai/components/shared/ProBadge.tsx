import { cn } from '@/lib/utils';
import { Crown } from 'lucide-react';

interface ProBadgeProps {
  className?: string;
}

export default function ProBadge({ className }: ProBadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold',
        'bg-gradient-to-r from-amber-400/20 to-orange-400/20 text-amber-300 border border-amber-400/20',
        className
      )}
    >
      <Crown className="w-3 h-3" />
      PRO
    </span>
  );
}
