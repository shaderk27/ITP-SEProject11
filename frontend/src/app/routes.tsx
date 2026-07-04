import { createBrowserRouter, Link } from "react-router";
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
    path: "/reset-password",//used to enforce password reset when logging in with temp pw
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
      {
        path: "reports",
        element: (
          <ProtectedRoute requiredPermissions={["reports:view"]}>
            <ReportsPage />
          </ProtectedRoute>
        ),
      },
      {
        path: "alerts",
        element: (
          <ProtectedRoute requiredPermissions={["alerts:view"]}>
            <AlertsPage />
          </ProtectedRoute>
        ),
      },
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
      {
        path: "chatbot",
        Component: ChatbotPage, // Open to all logged-in roles
      },
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
]);
