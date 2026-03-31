'use client';

import { useState, useCallback, useEffect } from 'react';

const PRO_TOKEN_KEY = 'textcraft_pro_session';

export function useProStatus() {
  const [proToken, setToken] = useState<string | null>(null);

  useEffect(() => {
    try {
      const token = localStorage.getItem(PRO_TOKEN_KEY);
      setToken(token);
    } catch {
      setToken(null);
    }
  }, []);

  const setProToken = useCallback((sessionId: string) => {
    localStorage.setItem(PRO_TOKEN_KEY, sessionId);
    setToken(sessionId);
  }, []);

  const clearProToken = useCallback(() => {
    localStorage.removeItem(PRO_TOKEN_KEY);
    setToken(null);
  }, []);

  return {
    isPro: !!proToken,
    proToken,
    setProToken,
    clearProToken,
  };
}
