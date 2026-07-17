import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { useAuth } from "../context/AuthContext";

const MAX_WARNING_BEFORE_EXPIRY_MS = 5 * 60 * 1000;
const DEFAULT_SESSION_MINUTES = 15;
const configuredMinutes = Number(
  import.meta.env.VITE_ACCESS_TOKEN_EXPIRE_MINUTES,
);

const SESSION_DURATION_MINUTES =
  Number.isFinite(configuredMinutes) && configuredMinutes > 0
    ? configuredMinutes
    : DEFAULT_SESSION_MINUTES;

if (!Number.isFinite(configuredMinutes) || configuredMinutes <= 0) {
  console.warn(
    `VITE_ACCESS_TOKEN_EXPIRE_MINUTES is missing or invalid; falling back to ${DEFAULT_SESSION_MINUTES} minutes. ` +
      "Set it to match the backend ACCESS_TOKEN_EXPIRE_MINUTES or session timing will be wrong.",
  );
}

const SESSION_DURATION_MS = SESSION_DURATION_MINUTES * 60 * 1000;
export const WARNING_BEFORE_EXPIRY_MS = Math.min(
  MAX_WARNING_BEFORE_EXPIRY_MS,
  Math.max(1000, Math.floor(SESSION_DURATION_MS / 2)),
);

export function useSessionTimeout() {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [showWarning, setShowWarning] = useState(false);
  const [secondsRemaining, setSecondsRemaining] = useState(
    WARNING_BEFORE_EXPIRY_MS / 1000,
  );

  const warningTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const expireTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastResetRef = useRef(0);
  const showWarningRef = useRef(false);

  const clearAllTimers = useCallback(() => {
    if (warningTimerRef.current) clearTimeout(warningTimerRef.current);
    if (expireTimerRef.current) clearTimeout(expireTimerRef.current);
    if (countdownRef.current) clearInterval(countdownRef.current);
  }, []);

  const handleExpire = useCallback(async () => {
    clearAllTimers();
    setShowWarning(false);
    await logout();
    navigate("/login", { state: { reason: "expired" }, replace: true });
  }, [clearAllTimers, logout, navigate]);

  const armTimers = useCallback(() => {
    clearAllTimers();
    lastResetRef.current = Date.now();

    warningTimerRef.current = setTimeout(() => {
      setShowWarning(true);
      setSecondsRemaining(WARNING_BEFORE_EXPIRY_MS / 1000);

      countdownRef.current = setInterval(() => {
        setSecondsRemaining((prev) => {
          if (prev <= 1) {
            if (countdownRef.current) clearInterval(countdownRef.current);
            return 0;
          }
          return prev - 1;
        });
      }, 1000);

      expireTimerRef.current = setTimeout(
        handleExpire,
        WARNING_BEFORE_EXPIRY_MS,
      );
    }, Math.max(0, SESSION_DURATION_MS - WARNING_BEFORE_EXPIRY_MS));
  }, [clearAllTimers, handleExpire]);

  const startTimers = useCallback(() => {
    setShowWarning(false);
    armTimers();
  }, [armTimers]);

  useEffect(() => {
    showWarningRef.current = showWarning;
  }, [showWarning]);

  const handleActivity = useCallback(() => {
    const now = Date.now();
    if (now - lastResetRef.current < 10_000) return;
    if (!showWarningRef.current) startTimers();
  }, [startTimers]);

  const extendSession = useCallback(async () => {
    try {
      const res = await fetch(
        `${import.meta.env.VITE_API_URL ?? "/api"}/auth/refresh`,
        {
          method: "POST",
          credentials: "include",
        },
      );
      if (!res.ok) {
        await handleExpire();
        return;
      }
    } catch {
      await handleExpire();
      return;
    }
    setShowWarning(false);
    startTimers();
  }, [handleExpire, startTimers]);

  useEffect(() => {
    armTimers();

    const events = [
      "mousemove",
      "keydown",
      "mousedown",
      "touchstart",
      "scroll",
    ];
    events.forEach((eventName) =>
      window.addEventListener(eventName, handleActivity, { passive: true }),
    );

    return () => {
      clearAllTimers();
      events.forEach((eventName) =>
        window.removeEventListener(eventName, handleActivity),
      );
    };
  }, [armTimers, clearAllTimers, handleActivity]);

  return { showWarning, secondsRemaining, extendSession, handleExpire };
}
