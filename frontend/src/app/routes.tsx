import { createBrowserRouter } from "react-router";
import { RootLayout } from "./components/layouts/RootLayout";
import { LoginPage } from "./pages/LoginPage";
import { DashboardPage } from "./pages/DashboardPage";
import { UploadPage } from "./pages/UploadPage";
import { ProcessingSummaryPage } from "./pages/ProcessingSummaryPage";
import { ReviewQueuePage } from "./pages/ReviewQueuePage";
import { ReviewDetailsPage } from "./pages/ReviewDetailsPage";
import { RecordsPage } from "./pages/RecordsPage";
import { ReportsPage } from "./pages/ReportsPage";
import { AlertsPage } from "./pages/AlertsPage";
import { AuditLogPage } from "./pages/AuditLogPage";
import { SystemConfigPage } from "./pages/SystemConfigPage";
import { ChatbotPage } from "./pages/ChatbotPage";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { FEATURES } from "./config/features";
import { CreateUserPage } from "./pages/CreateUserPage";
import { AccessDenied } from "./pages/error/AccessDenied";
import { NotFound } from "./pages/error/NotFound";
import { ForgotPasswordPage } from "./pages/ForgotPasswordPage";
import { ResetPasswordPage } from "./pages/ResetPasswordPage";

export const router = createBrowserRouter([
  {
    path: "/login",
    Component: LoginPage,
  },
  {
    path: "/forgot-password",
    Component: ForgotPasswordPage,
  },
  {
    path: "/reset-password",
    Component: ResetPasswordPage,
  },
  {
    path: "/403",
    element: <AccessDenied />,
  },
  {
    path: "/404",
    element: <NotFound />,
  },
  {
    path: "/",
    element: (
      <ProtectedRoute>
        <RootLayout />
      </ProtectedRoute>
    ),
    errorElement: <NotFound />,
    children: [
      {
        index: true,
        Component: DashboardPage,
      },
      {
        path: "upload",
        element: (
          <ProtectedRoute requiredPermissions={["upload:create"]}>
            <UploadPage />
          </ProtectedRoute>
        ),
      },
      {
        path: "upload/result",
        element: (
          <ProtectedRoute requiredPermissions={["upload:create"]}>
            <ProcessingSummaryPage />
          </ProtectedRoute>
        ),
      },
      {
        path: "review",
        element: (
          <ProtectedRoute requiredPermissions={["review:view"]}>
            <ReviewQueuePage />
          </ProtectedRoute>
        ),
      },
      {
        path: "review/:id",
        element: (
          <ProtectedRoute requiredPermissions={["review:view"]}>
            <ReviewDetailsPage />
          </ProtectedRoute>
        ),
      },
      {
        path: "records",
        element: (
          <ProtectedRoute requiredPermissions={["records:view"]}>
            <RecordsPage />
          </ProtectedRoute>
        ),
      },
      // Reports — detached for ITP1 (flip FEATURES.reports to re-attach).
      // While off, /reports is unregistered → catch-all 404, even for admin.
      ...(FEATURES.reports
        ? [
            {
              path: "reports",
              element: (
                <ProtectedRoute requiredPermissions={["reports:view"]}>
                  <ReportsPage />
                </ProtectedRoute>
              ),
            },
          ]
        : []),
      {
        path: "alerts",
        element: (
          <ProtectedRoute requiredPermissions={["alerts:view"]}>
            <AlertsPage />
          </ProtectedRoute>
        ),
      },
      // Audit Log — detached until ITP2 (flip FEATURES.auditLog to re-attach).
      ...(FEATURES.auditLog
        ? [
            {
              path: "audit",
              element: (
                // Strictly locked to Admins using your allowedRoles logic
                <ProtectedRoute
                  allowedRoles={["admin"]}
                  requiredPermissions={["audit:view"]}
                >
                  <AuditLogPage />
                </ProtectedRoute>
              ),
            },
          ]
        : []),
      {
        path: "config",
        element: (
          <ProtectedRoute
            allowedRoles={["admin"]}
            requiredPermissions={["config:view"]}
          >
            <SystemConfigPage />
          </ProtectedRoute>
        ),
      },
      // AI Chatbot — detached until ITP2 (flip FEATURES.chatbot to re-attach).
      // Open to all logged-in roles (parent ProtectedRoute enforces login);
      // re-check whether role restrictions are needed when enabling (W15-01).
      ...(FEATURES.chatbot
        ? [
            {
              path: "chatbot",
              Component: ChatbotPage,
            },
          ]
        : []),
      {
        path: "users/create",
        element: (
          <ProtectedRoute
            allowedRoles={["admin"]}
            requiredPermissions={["user:create"]}
          >
            <CreateUserPage />
          </ProtectedRoute>
        ),
      },
    ],
  },
  {
    path: "*",
    element: <NotFound />,
  },
]);
