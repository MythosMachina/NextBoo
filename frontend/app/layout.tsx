import "./globals.css";
import type { Metadata } from "next";
import { ReactNode } from "react";
import { AppShell } from "./components/app-shell";
import { AuthProvider } from "./components/auth";
import { TagContextMenuProvider } from "./components/tag-context-menu";

export const metadata: Metadata = {
  title: "NextBoo",
  description: "Self-hosted AI-powered booru gallery"
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              (function () {
                try {
                  var stored = localStorage.getItem("nextboo-theme");
                  var prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
                  var theme = stored || (prefersDark ? "dark" : "light");
                  document.documentElement.dataset.theme = theme;
                } catch (e) {}
              })();
            `
          }}
        />
        <AuthProvider>
          <TagContextMenuProvider>
            <AppShell>{children}</AppShell>
          </TagContextMenuProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
