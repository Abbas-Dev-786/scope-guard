import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import AuthGate from "./auth-gate";
import SessionControls from "./session-controls";

export const metadata: Metadata = {
  title: "ScopeGuard",
  description: "Evidence-backed scope change management",
};

const navigation = [
  ["Overview", "/"],
  ["Clients", "/clients"],
  ["Projects", "/projects"],
  ["Proposals", "/proposals"],
  ["Integrations", "/integrations"],
  ["Preferences", "/settings"],
];

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <div className="shell">
          <aside className="sidebar">
            <Link className="brand" href="/">ScopeGuard</Link>
            <p className="eyebrow">Freelancer workspace</p>
            <nav aria-label="Primary navigation">
              {navigation.map(([label, href]) => <Link key={href} href={href}>{label}</Link>)}
            </nav>
            <div className="testBadge">Test mode</div><SessionControls />
          </aside>
          <main><AuthGate>{children}</AuthGate></main>
        </div>
      </body>
    </html>
  );
}
