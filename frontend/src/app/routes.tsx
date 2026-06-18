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
import { ProtectedRoute } from "./ProtectedRoute";

export const router = createBrowserRouter([
  {
    path: "/login",
    Component: LoginPage,
  },
  {
    path: "/",
    element: (
      <ProtectedRoute>
        <RootLayout />
      </ProtectedRoute>
    ),
    children: [
      { index: true, Component: DashboardPage },
      { path: "upload", Component: UploadPage },
      { path: "upload/result", Component: ProcessingSummaryPage },
      { path: "review", Component: ReviewQueuePage },
      { path: "review/:id", Component: ReviewDetailsPage },
      { path: "records", Component: RecordsPage },
      { path: "reports", Component: ReportsPage },
      { path: "alerts", Component: AlertsPage },
      { path: "audit", Component: AuditLogPage },
      { path: "config", Component: SystemConfigPage },
      { path: "chatbot", Component: ChatbotPage },
    ],
  },
]);
