"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  Activity,
  Brain,
  BookOpen,
  Calendar,
  ChevronsLeft,
  ChevronsRight,
  History,
  Image as ImageIcon,
  Instagram,
  LayoutDashboard,
  LogOut,
  MessageSquare,
  Radio,
  Telescope,
  User as UserIcon,
  Users,
  X,
  Youtube,
} from "lucide-react";
import { api, HealthResponse } from "@/lib/api";
import { useAuth } from "@/lib/auth/AuthContext";
import SidebarTooltip from "./SidebarTooltip";

export interface NavItem {
  href: string;
  label: string;
  subLabel?: string;
  icon: React.ComponentType<{ className?: string }>;
}

export const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Nexus", subLabel: "Command Center", icon: LayoutDashboard },
  { href: "/history", label: "History", subLabel: "Pipeline Runs & Logs", icon: History },
  { href: "/assistant", label: "Assistant", subLabel: "AI Schedule & Strategy", icon: MessageSquare },
  { href: "/topics", label: "Topics", subLabel: "Research Backlog", icon: BookOpen },
  { href: "/planner", label: "Planner", subLabel: "Cross-Platform Pipeline", icon: Calendar },
  { href: "/image-studio", label: "Image Studio", subLabel: "Prompt to Image", icon: ImageIcon },
  { href: "/youtube-analysis", label: "YouTube", subLabel: "Channel & Competitors", icon: Youtube },
  { href: "/instagram-analysis", label: "Instagram", subLabel: "Media & Audience", icon: Instagram },
  { href: "/prospects", label: "Prospects", subLabel: "Channel Audits", icon: Telescope },
  { href: "/personal-intelligence", label: "Intelligence", subLabel: "Knowledge & Directives", icon: Brain },
];

interface SidebarProps {
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  isMobileOpen: boolean;
  onMobileClose: () => void;
}

export default function Sidebar({
  isCollapsed,
  onToggleCollapse,
  isMobileOpen,
  onMobileClose,
}: SidebarProps) {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [isOnline, setIsOnline] = useState(false);
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const router = useRouter();

  // Health check polling
  useEffect(() => {
    let isMounted = true;
    let timerId: NodeJS.Timeout | null = null;

    const checkHealth = async (retries = 2, delay = 1500) => {
      try {
        const data = await api.getHealth();
        if (isMounted) {
          setHealth(data);
          setIsOnline(true);
        }
      } catch (err) {
        if (isMounted && retries > 0) {
          timerId = setTimeout(() => {
            if (isMounted) checkHealth(retries - 1, delay * 1.5);
          }, delay);
          return;
        }
        if (isMounted) {
          setIsOnline(false);
        }
      }
    };

    checkHealth();
    const interval = setInterval(() => checkHealth(1, 1000), 30000);

    return () => {
      isMounted = false;
      if (timerId) clearTimeout(timerId);
      clearInterval(interval);
    };
  }, []);

  async function handleLogout() {
    await logout();
    router.replace("/login");
  }

  const isRouteActive = (href: string) => {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  };

  return (
    <>
      {/* Mobile Backdrop */}
      <AnimatePresence>
        {isMobileOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={onMobileClose}
            className="fixed inset-0 z-40 bg-black/70 backdrop-blur-xs md:hidden"
            aria-hidden="true"
          />
        )}
      </AnimatePresence>

      {/* Sidebar Container */}
      <aside
        className={`fixed top-0 bottom-0 left-0 z-50 flex flex-col bg-slate-950/95 border-r border-white/5 backdrop-blur-xl transition-all duration-300 ease-in-out ${
          // Desktop sizing
          isCollapsed ? "md:w-[68px]" : "md:w-[260px]"
          } ${
          // Mobile slide-over transform
          isMobileOpen
            ? "translate-x-0 w-[280px]"
            : "-translate-x-full md:translate-x-0"
          }`}
      >
        {/* ── 1. Header / Branding ── */}
        <div className="flex h-16 shrink-0 items-center justify-between border-b border-white/5 px-3.5">
          <Link
            href="/"
            onClick={onMobileClose}
            className={`group flex items-center gap-3 overflow-hidden transition-opacity hover:opacity-90 ${isCollapsed ? "justify-center w-full md:w-auto" : ""
              }`}
          >
            <motion.div
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 via-indigo-500 to-purple-600 shadow-lg shadow-blue-500/20"
              animate={{ rotate: [0, 4, -4, 0] }}
              transition={{ duration: 5, repeat: Infinity, ease: "easeInOut" }}
            >
              <Activity className="h-4.5 w-4.5 text-white" />
            </motion.div>

            {(!isCollapsed || isMobileOpen) && (
              <div className="flex min-w-0 flex-col">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-bold uppercase tracking-[0.18em] text-white">
                    Wings of AI
                  </span>
                  <span className="text-[10px] text-slate-600">//</span>
                  <span className="bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-[11px] font-bold uppercase tracking-wider text-transparent">
                    Nexus
                  </span>
                </div>
                <span className="text-[9px] uppercase tracking-[0.25em] text-slate-500 truncate">
                  Autonomous Syndicate
                </span>
              </div>
            )}
          </Link>

          {/* Close button on mobile */}
          <button
            onClick={onMobileClose}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-white/5 hover:text-white md:hidden"
            aria-label="Close sidebar"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* ── 2. Scrollable Body: Nav & Sections ── */}
        <div className="sidebar-scrollbar flex flex-1 flex-col gap-6 overflow-y-auto overflow-x-hidden px-2.5 py-4">
          {/* Navigation Group */}
          <div>
            {(!isCollapsed || isMobileOpen) && (
              <div className="mb-2 px-2 text-[10px] font-semibold uppercase tracking-[0.25em] text-slate-500">
                Navigation
              </div>
            )}

            <nav className="flex flex-col gap-1">
              {NAV_ITEMS.map((item) => {
                const active = isRouteActive(item.href);
                const Icon = item.icon;

                return (
                  <SidebarTooltip
                    key={item.href}
                    label={item.label}
                    subLabel={item.subLabel}
                    isCollapsed={isCollapsed && !isMobileOpen}
                  >
                    <Link
                      href={item.href}
                      onClick={onMobileClose}
                      className={`group relative flex h-10 w-full items-center gap-3 rounded-lg px-2.5 text-xs font-medium transition-all ${active
                          ? "bg-blue-600/15 text-blue-300 border border-blue-500/30 shadow-[0_0_12px_rgba(59,130,246,0.12)]"
                          : "text-slate-400 hover:bg-white/5 hover:text-slate-200 border border-transparent"
                        } ${isCollapsed && !isMobileOpen ? "justify-center px-0" : ""}`}
                    >
                      {/* Active Indicator Bar */}
                      {active && (
                        <div className="absolute left-0 top-1.5 bottom-1.5 w-[3px] rounded-r bg-blue-500" />
                      )}

                      <Icon
                        className={`h-4.5 w-4.5 shrink-0 transition-transform group-hover:scale-105 ${active ? "text-blue-400" : "text-slate-400 group-hover:text-slate-200"
                          }`}
                      />

                      {(!isCollapsed || isMobileOpen) && (
                        <span className="truncate tracking-wide">{item.label}</span>
                      )}
                    </Link>
                  </SidebarTooltip>
                );
              })}
            </nav>
          </div>

          {/* System Status Section */}
          <div className="border-t border-white/5 pt-4">
            {(!isCollapsed || isMobileOpen) && (
              <div className="mb-2.5 px-2 text-[10px] font-semibold uppercase tracking-[0.25em] text-slate-500">
                Live Status
              </div>
            )}

            <div className="flex flex-col gap-2">
              {/* Online / Offline */}
              <SidebarTooltip
                label={isOnline ? "System Online" : "System Offline"}
                subLabel="Health check endpoint response"
                isCollapsed={isCollapsed && !isMobileOpen}
              >
                <div
                  className={`flex h-9 items-center gap-2.5 rounded-lg px-2.5 text-xs font-medium ${isCollapsed && !isMobileOpen ? "justify-center w-full px-0" : ""
                    }`}
                >
                  <span className="relative flex h-2.5 w-2.5 shrink-0">
                    <span
                      className={`absolute inline-flex h-full w-full rounded-full opacity-75 animate-ping ${isOnline ? "bg-green-400" : "bg-red-400"
                        }`}
                    />
                    <span
                      className={`relative inline-flex h-2.5 w-2.5 rounded-full ${isOnline ? "bg-green-500 animate-pulse-green" : "bg-red-500"
                        }`}
                    />
                  </span>

                  {(!isCollapsed || isMobileOpen) && (
                    <span
                      className={`truncate text-xs uppercase tracking-wider ${isOnline ? "text-green-400 font-medium" : "text-red-400"
                        }`}
                    >
                      {isOnline ? "System Online" : "System Offline"}
                    </span>
                  )}
                </div>
              </SidebarTooltip>

              {/* Agents Active */}
              <SidebarTooltip
                label={`${health?.agents_available || 0} Agents Active`}
                subLabel="Autonomous Pipeline Workers"
                isCollapsed={isCollapsed && !isMobileOpen}
              >
                <div
                  className={`flex h-9 items-center gap-2.5 rounded-lg glass-card px-2.5 text-xs ${isCollapsed && !isMobileOpen ? "justify-center w-full px-0" : ""
                    }`}
                >
                  <div className="relative">
                    <Users className="h-4 w-4 shrink-0 text-blue-400" />
                    {isCollapsed && !isMobileOpen && (
                      <span className="absolute -top-1.5 -right-2 flex h-3.5 min-w-3.5 items-center justify-center rounded-full bg-blue-500 px-1 text-[9px] font-bold text-white">
                        {health?.agents_available || 0}
                      </span>
                    )}
                  </div>

                  {(!isCollapsed || isMobileOpen) && (
                    <span className="font-mono text-xs text-blue-300 truncate">
                      {health?.agents_available || 0} Agents Active
                    </span>
                  )}
                </div>
              </SidebarTooltip>

              {/* Live Radio Pulse */}
              <SidebarTooltip
                label="Realtime Stream Active"
                subLabel="Telemetry & Task Feeds"
                isCollapsed={isCollapsed && !isMobileOpen}
              >
                <div
                  className={`flex h-8 items-center gap-2 rounded-lg px-2.5 text-xs ${isCollapsed && !isMobileOpen ? "justify-center w-full px-0" : ""
                    }`}
                >
                  <motion.div
                    className="flex items-center gap-1.5"
                    animate={{ opacity: [0.4, 1, 0.4] }}
                    transition={{ duration: 2, repeat: Infinity }}
                  >
                    <Radio className="h-3.5 w-3.5 shrink-0 text-purple-400" />
                    {(!isCollapsed || isMobileOpen) && (
                      <span className="font-mono text-[10px] tracking-wider text-purple-400/80 uppercase">
                        LIVE PULSE
                      </span>
                    )}
                  </motion.div>
                </div>
              </SidebarTooltip>
            </div>
          </div>
        </div>

        {/* ── 3. Bottom: User Profile & Collapse Toggle ── */}
        <div className="shrink-0 border-t border-white/5 bg-slate-950/80 p-2 flex flex-col gap-1.5">
          {user && (
            <div
              className={`flex items-center justify-between gap-2 rounded-lg p-1.5 ${isCollapsed && !isMobileOpen ? "justify-center" : ""
                }`}
            >
              <SidebarTooltip
                label={user.email || "Account"}
                subLabel="Signed in user"
                isCollapsed={isCollapsed && !isMobileOpen}
              >
                <div
                  className={`flex items-center gap-2 overflow-hidden ${isCollapsed && !isMobileOpen ? "justify-center" : ""
                    }`}
                >
                  <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-slate-800 border border-white/10 text-slate-300">
                    <UserIcon className="h-3.5 w-3.5" />
                  </div>
                  {(!isCollapsed || isMobileOpen) && (
                    <div className="flex min-w-0 flex-col">
                      <span className="truncate text-xs font-mono text-slate-300" title={user.email}>
                        {user.email}
                      </span>
                    </div>
                  )}
                </div>
              </SidebarTooltip>

              {(!isCollapsed || isMobileOpen) && (
                <button
                  onClick={handleLogout}
                  title="Sign out"
                  className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-white/10 glass-card text-slate-400 hover:border-red-500/30 hover:bg-red-500/10 hover:text-red-300 transition-all"
                  aria-label="Sign out"
                >
                  <LogOut className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          )}

          {/* Separate sign out in collapsed mode */}
          {user && isCollapsed && !isMobileOpen && (
            <SidebarTooltip
              label="Sign out"
              subLabel={user.email}
              isCollapsed={true}
            >
              <button
                onClick={handleLogout}
                className="flex h-8 w-full items-center justify-center rounded-lg border border-white/10 glass-card text-slate-400 hover:border-red-500/30 hover:bg-red-500/10 hover:text-red-300 transition-all"
                aria-label="Sign out"
              >
                <LogOut className="h-3.5 w-3.5" />
              </button>
            </SidebarTooltip>
          )}

          {/* Desktop Collapse / Expand Toggle Button */}
          <div className="hidden md:block">
            <SidebarTooltip
              label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
              shortcut="⌘B / Ctrl+B"
              isCollapsed={isCollapsed}
            >
              <button
                onClick={onToggleCollapse}
                className={`flex h-8 w-full items-center gap-2 rounded-lg border border-white/5 bg-white/[0.02] px-2 text-xs text-slate-400 hover:bg-white/5 hover:text-slate-200 transition-all ${isCollapsed ? "justify-center" : "justify-between"
                  }`}
                aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
              >
                {isCollapsed ? (
                  <ChevronsRight className="h-4 w-4 shrink-0" />
                ) : (
                  <>
                    <span className="text-[11px] font-medium text-slate-400">Collapse</span>
                    <div className="flex items-center gap-1">
                      <kbd className="rounded border border-white/10 bg-white/5 px-1 py-0.5 text-[9px] font-mono text-slate-500">
                        ⌘B
                      </kbd>
                      <ChevronsLeft className="h-4 w-4 shrink-0" />
                    </div>
                  </>
                )}
              </button>
            </SidebarTooltip>
          </div>
        </div>
      </aside>
    </>
  );
}
