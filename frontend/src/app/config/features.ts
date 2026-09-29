/**
 * Feature flags — single switch per deferred/ITP2 feature.
 *
 * Flipping a flag to `true` re-attaches BOTH the sidebar nav item
 * (RootLayout.tsx) and the route itself (routes.tsx). While `false`,
 * the route is not registered at all, so direct navigation (e.g.
 * typing /chatbot) falls through to the catch-all 404 for every role,
 * admin included. The page components stay in the repo untouched.
 */
export const FEATURES = {
  /** AI Chatbot — ITP2 (W13+). Re-check route guards when enabling. */
  chatbot: false,
  /** Audit Log viewer — ITP2 (W17-02). Admin-only route. */
  auditLog: true,
  /** Reports page — hidden for ITP1 demos. */
  reports: false,
  /** Header bell (top-right). Currently a stub with a hardcoded red dot. */
  headerNotifications: false,
};
