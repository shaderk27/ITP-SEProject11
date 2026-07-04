// src/app/context/SessionTimeoutProvider.tsx
//
// Owns session-timeout tracking and the "your session is expiring" modal.
// Deliberately takes isAuthenticated/logout as props rather than calling
// useAuth() itself — this keeps it decoupled from any specific auth
// implementation and avoids a circular import with AuthContext (which
// renders this provider).
import type { ReactNode } from "react";
import { Bell } from "lucide-react";
import {
  useSessionTimeout,
  WARNING_BEFORE_EXPIRY_MS,
} from "../services/useSessionTimeout";

interface SessionTimeoutProviderProps {
  children: ReactNode;
  isAuthenticated: boolean;
  logout: () => Promise<void>;
}

export function SessionTimeoutProvider({
  children,
  isAuthenticated,
  logout,
}: SessionTimeoutProviderProps) {
  const { showWarning, secondsRemaining, extendSession, handleExpire } =
    useSessionTimeout({ isAuthenticated, logout });

  return (
    <>
      {children}

      {/* SESSION TIMEOUT WARNING MODAL */}
      {showWarning && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 backdrop-blur-sm px-4">
          <div className="bg-white w-full max-w-sm rounded-xl shadow-xl overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-100 bg-amber-50">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-full bg-amber-100">
                  <Bell className="h-5 w-5 text-amber-600" />
                </div>
                <h3 className="text-lg font-semibold text-gray-800">
                  Session Expiring
                </h3>
              </div>
            </div>

            <div className="p-6 space-y-4">
              <p className="text-sm text-gray-600">
                Your session will expire in{" "}
                <span className="font-semibold text-amber-600">
                  {Math.floor(secondsRemaining / 60)}:
                  {String(secondsRemaining % 60).padStart(2, "0")}
                </span>
                . Would you like to stay logged in?
              </p>

              {/* Countdown bar */}
              <div className="w-full bg-gray-100 rounded-full h-1.5">
                <div
                  className="bg-amber-500 h-1.5 rounded-full transition-all duration-1000"
                  style={{
                    width: `${(secondsRemaining / (WARNING_BEFORE_EXPIRY_MS / 1000)) * 100}%`,
                  }}
                />
              </div>

              <div className="flex gap-3 pt-2">
                <button
                  onClick={handleExpire}
                  className="flex-1 px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
                >
                  Sign Out
                </button>
                <button
                  onClick={extendSession}
                  className="flex-1 px-4 py-2 text-sm font-medium text-white bg-[#1e3a8a] rounded-lg hover:bg-[#1e40af] transition-colors"
                >
                  Stay Logged In
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
