// src/app/hooks/useSessionTimeout.ts
import { useEffect, useRef, useCallback, useState } from "react";
import { useAuth } from "../context/AuthContext";
import { useNavigate } from "react-router";

export const WARNING_BEFORE_EXPIRY_MS = 5 * 60 * 1000; // show warning 5 mins before expiry
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
    `ACCESS_TOKEN_EXPIRE_MINUTES is missing or invalid — falling back to ${DEFAULT_SESSION_MINUTES} minutes. ` +
      "Set it to match the backend's ACCESS_TOKEN_EXPIRE_MINUTES or session timing will be wrong.",
  );
}

const SESSION_DURATION_MS = SESSION_DURATION_MINUTES * 60 * 1000;

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
  const lastResetRef = useRef(Date.now());

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
  }, [logout, navigate, clearAllTimers]);

  const startTimers = useCallback(() => {
    clearAllTimers();
    setShowWarning(false);
    lastResetRef.current = Date.now();

    warningTimerRef.current = setTimeout(() => {
      setShowWarning(true);
      setSecondsRemaining(WARNING_BEFORE_EXPIRY_MS / 1000);

      // Countdown display
      countdownRef.current = setInterval(() => {
        setSecondsRemaining((prev) => {
          if (prev <= 1) {
            clearInterval(countdownRef.current!);
            return 0;
          }
          return prev - 1;
        });
      }, 1000);

      // Final expiry
      expireTimerRef.current = setTimeout(
        handleExpire,
        WARNING_BEFORE_EXPIRY_MS,
      );
    }, SESSION_DURATION_MS - WARNING_BEFORE_EXPIRY_MS);
  }, [clearAllTimers, handleExpire]);

  // Reset timers on user activity
  const handleActivity = useCallback(() => {
    const now = Date.now();
    // Throttle to avoid resetting on every mouse move
    if (now - lastResetRef.current < 10_000) return;
    if (!showWarning) startTimers();
  }, [showWarning, startTimers]);

  const extendSession = useCallback(async () => {
    try {
      const res = await fetch(
        `${import.meta.env.VITE_API_URL ?? "http://localhost:8080"}/api/auth/refresh`,
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
      // Network error reaching the refresh endpoint — treat as expired
      // rather than silently keeping the client-side session alive.
      await handleExpire();
      return;
    }
    setShowWarning(false);
    startTimers();
  }, [startTimers, handleExpire]);

  useEffect(() => {
    startTimers();

    const events = [
      "mousemove",
      "keydown",
      "mousedown",
      "touchstart",
      "scroll",
    ];
    events.forEach((e) =>
      window.addEventListener(e, handleActivity, { passive: true }),
    );

    return () => {
      clearAllTimers();
      events.forEach((e) => window.removeEventListener(e, handleActivity));
    };
  }, [startTimers, handleActivity, clearAllTimers]);

  return { showWarning, secondsRemaining, extendSession, handleExpire };
}
