'use client';

import { useState, useCallback, useEffect } from 'react';

const STORAGE_KEY = 'textcraft_usage';
const FREE_LIMIT = 5;

interface UsageData {
  count: number;
  date: string;
}

function getTodayStr(): string {
  return new Date().toISOString().split('T')[0];
}

function readUsage(): UsageData {
  const today = getTodayStr();
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

export function useUsage() {
  const [usage, setUsage] = useState<UsageData>({ count: 0, date: getTodayStr() });

  useEffect(() => {
    setUsage(readUsage());
  }, []);

  const incrementUsage = useCallback(() => {
    const today = getTodayStr();
    const current = readUsage();
    const updated: UsageData = {
      count: current.date === today ? current.count + 1 : 1,
      date: today,
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
    setUsage(updated);
    return updated.count;
  }, []);

  return {
    usedToday: usage.count,
    limit: FREE_LIMIT,
    remaining: Math.max(0, FREE_LIMIT - usage.count),
    canUse: usage.count < FREE_LIMIT,
    incrementUsage,
  };
}
