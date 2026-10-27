import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppLayout } from "./layout";
import { AuthGuard, RoleGuard } from "./guards";

/**
 * Routes. Actual pages come in the US P1 PRs; here we stub placeholders so the layout and
 * guards compile and the e2e scaffolding can navigate.
 */
export const router = createBrowserRouter([
  { path: "/", element: <Navigate to="/chat" replace /> },
  {
    path: "/login",
    lazy: async () => ({ Component: (await import("@/features/auth/LoginPage")).LoginPage }),
  },
  {
    path: "/register",
    lazy: async () => ({ Component: (await import("@/features/auth/RegisterPage")).RegisterPage }),
  },
  {
    path: "/verify",
    lazy: async () => ({ Component: (await import("@/features/auth/VerifyPage")).VerifyPage }),
  },
  {
    path: "/forgot",
    lazy: async () => ({ Component: (await import("@/features/auth/ForgotPage")).ForgotPage }),
  },
  {
    path: "/reset",
    lazy: async () => ({ Component: (await import("@/features/auth/ResetPage")).ResetPage }),
  },
  {
    path: "/invite",
    lazy: async () => ({
      Component: (await import("@/features/auth/AcceptInvitePage")).AcceptInvitePage,
    }),
  },
  {
    element: <AppLayout />,
    children: [
      {
        element: <AuthGuard />,
        children: [
          {
            element: <RoleGuard allow={["merchant"]} />,
            children: [
              {
                path: "/chat",
                lazy: async () => ({
                  Component: (await import("@/features/chat/ChatPage")).ChatPage,
                }),
              },
              {
                path: "/chat/:id",
                lazy: async () => ({
                  Component: (await import("@/features/chat/ChatPage")).ChatPage,
                }),
              },
              {
                path: "/history",
                lazy: async () => ({
                  Component: (await import("@/features/conversations/HistoryPage")).HistoryPage,
                }),
              },
              {
                path: "/privacy",
                lazy: async () => ({
                  Component: (await import("@/features/privacy/PrivacyPage")).PrivacyPage,
                }),
              },
            ],
          },
          {
            element: <RoleGuard allow={["operator", "admin"]} />,
            children: [
              {
                path: "/queue",
                lazy: async () => ({
                  Component: (await import("@/features/handoffs/QueuePage")).QueuePage,
                }),
              },
              {
                path: "/queue/:ticket_id",
                lazy: async () => ({
                  Component: (await import("@/features/handoffs/TicketPage")).TicketPage,
                }),
              },
            ],
          },
          {
            element: <RoleGuard allow={["admin"]} />,
            children: [
              {
                path: "/admin",
                lazy: async () => ({
                  Component: (await import("@/features/admin/AdminHome")).AdminHome,
                }),
              },
              {
                path: "/admin/accounts",
                lazy: async () => ({
                  Component: (await import("@/features/admin/AccountsPage")).AccountsPage,
                }),
              },
              {
                path: "/admin/merchants",
                lazy: async () => ({
                  Component: (await import("@/features/admin/MerchantLinkPage")).MerchantLinkPage,
                }),
              },
              {
                path: "/admin/queue",
                lazy: async () => ({
                  Component: (await import("@/features/admin/QueueOverviewPage")).QueueOverviewPage,
                }),
              },
              {
                path: "/admin/audit",
                lazy: async () => ({
                  Component: (await import("@/features/admin/AuditPage")).AuditPage,
                }),
              },
            ],
          },
        ],
      },
    ],
  },
  { path: "*", lazy: async () => ({ Component: (await import("./NotFound")).NotFound }) },
]);
