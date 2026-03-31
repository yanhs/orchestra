const STORAGE_KEY = 'textcraft_usage';
const FREE_LIMIT = 5;

export interface UsageData {
  count: number;
  date: string;
}

export function getTodayKey(): string {
  return new Date().toISOString().split('T')[0];
}

export function getUsage(): UsageData {
  const today = getTodayKey();
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) return { count: 0, date: today };
    const data: UsageData = JSON.parse(stored);
    if (data.date !== today) return { count: 0, date: today };
    return data;
  } catch {
    return { count: 0, date: today };
  }
}

export function incrementUsage(): UsageData {
  const today = getTodayKey();
  const current = getUsage();
  const updated: UsageData = {
    count: current.date === today ? current.count + 1 : 1,
    date: today,
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
  return updated;
}

export function canUseFreeTier(): boolean {
  return getUsage().count < FREE_LIMIT;
}

export function getRemaining(): number {
  return Math.max(0, FREE_LIMIT - getUsage().count);
}

export { FREE_LIMIT };
