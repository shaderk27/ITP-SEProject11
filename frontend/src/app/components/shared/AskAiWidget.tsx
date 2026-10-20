/**
 * Floating "Ask AI" widget.
 *
 * A draggable launcher pill that opens a chat panel, available on every
 * authenticated page. Defaults to the top-right corner — the one part of the
 * header that is always empty — and remembers where the user drags it.
 *
 * The pill is the ONLY drag handle — the panel itself is not draggable, since
 * its placement is derived from the pill and grabbing it made it flip sides
 * under the cursor. An open panel stays open and travels with the pill,
 * holding a fixed offset so nothing jumps mid-drag, then settles into a
 * proper placement when the pill is dropped.
 *
 * Questions go to POST /api/chatbot/ask, which answers with an LLM from
 * role-scoped budget data. If the AI is unavailable the service falls back to
 * the rule-based answers built on /api/chatbot/query-context, so the popup
 * keeps working without an API key. See services/chatbotService.ts.
 */

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import {
  ChevronLeft,
  History,
  Send,
  Sparkles,
  SquarePen,
  Trash2,
  X,
} from "lucide-react";
import { cn } from "../ui/utils";
import { useAuth } from "../../context/AuthContext";
import {
  askAssistant,
  type AnswerSource,
  type ChatTurn,
} from "../../services/chatbotService";

const LAUNCHER_WIDTH = 116;
const LAUNCHER_HEIGHT = 44;
const PANEL_WIDTH = 384;
const PANEL_HEIGHT = 540;
const EDGE_MARGIN = 16;
/** Pointer travel (px) past which a press counts as a drag, not a click. */
const DRAG_THRESHOLD = 4;
const STORAGE_KEY = "askAi.launcherPosition";
const CHATS_STORAGE_KEY = "askAi.conversations";
/** Conversations kept in history; older ones fall off the end. */
const MAX_CONVERSATIONS = 30;
/** Characters of the opening question used to title a conversation. */
const TITLE_LENGTH = 40;

interface Point {
  x: number;
  y: number;
}

interface ChatMessage {
  id: number;
  role: "user" | "assistant";
  text: string;
  /** Provenance line under an assistant answer (AI vs fallback, period, counts). */
  note?: string;
  /** Purchase lines the AI answer cited (W13-03A). */
  sources?: AnswerSource[];
}

/** One saved thread. Persisted per browser; nothing leaves the device. */
interface Conversation {
  id: string;
  title: string;
  updatedAt: number;
  messages: ChatMessage[];
}

function newConversation(): Conversation {
  return {
    id: `c${Date.now()}${Math.random().toString(36).slice(2, 7)}`,
    title: "New chat",
    updatedAt: Date.now(),
    messages: [],
  };
}

/** Title a thread from its opening question, the way most chat UIs do. */
function titleFrom(question: string): string {
  const clean = question.trim().replace(/\s+/g, " ");
  if (clean.length <= TITLE_LENGTH) return clean;
  return `${clean.slice(0, TITLE_LENGTH).trimEnd()}…`;
}

function loadConversations(): Conversation[] {
  try {
    const raw = window.localStorage.getItem(CHATS_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    // Tolerate anything malformed rather than blowing up the whole widget.
    return parsed.filter(
      (c): c is Conversation =>
        c &&
        typeof c.id === "string" &&
        typeof c.title === "string" &&
        Array.isArray(c.messages),
    );
  } catch {
    return [];
  }
}

/** "just now" / "5m ago" / "3h ago" / "12 Apr" — compact enough for a row. */
function relativeTime(timestamp: number): string {
  const seconds = Math.round((Date.now() - timestamp) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(timestamp).toLocaleDateString(undefined, {
    day: "2-digit",
    month: "short",
  });
}

/** Top-right corner, the default resting place for a first-time visitor. */
function defaultPosition(): Point {
  if (typeof window === "undefined") return { x: 0, y: EDGE_MARGIN };
  return {
    x: window.innerWidth - LAUNCHER_WIDTH - EDGE_MARGIN,
    y: EDGE_MARGIN,
  };
}

function clampToViewport(point: Point): Point {
  if (typeof window === "undefined") return point;
  const maxX = Math.max(0, window.innerWidth - LAUNCHER_WIDTH - EDGE_MARGIN);
  const maxY = Math.max(0, window.innerHeight - LAUNCHER_HEIGHT - EDGE_MARGIN);
  return {
    x: Math.min(Math.max(point.x, EDGE_MARGIN), maxX),
    y: Math.min(Math.max(point.y, EDGE_MARGIN), maxY),
  };
}

interface PanelBox extends Point {
  height: number;
}

/** Panel height, shrunk to fit short viewports rather than overflowing. */
function panelHeight(): number {
  if (typeof window === "undefined") return PANEL_HEIGHT;
  return Math.min(PANEL_HEIGHT, window.innerHeight - EDGE_MARGIN * 2);
}

/** Keep a panel box fully on-screen. */
function clampPanelBox(point: Point): PanelBox {
  const height = panelHeight();
  if (typeof window === "undefined") return { ...point, height };
  return {
    x: Math.min(
      Math.max(point.x, EDGE_MARGIN),
      Math.max(EDGE_MARGIN, window.innerWidth - PANEL_WIDTH - EDGE_MARGIN),
    ),
    y: Math.min(
      Math.max(point.y, EDGE_MARGIN),
      Math.max(EDGE_MARGIN, window.innerHeight - height - EDGE_MARGIN),
    ),
    height,
  };
}

/**
 * Where the panel sits relative to the launcher, decided once when it opens.
 *
 * Tries below, then above, then beside — in that order — so the panel never
 * covers the launcher itself. Simply clamping a non-fitting placement would
 * park the panel right on top of the pill, hiding the only control that
 * closes it.
 */
function panelPosition(anchor: Point): PanelBox {
  const height = panelHeight();
  if (typeof window === "undefined") return { ...anchor, height };
  const gap = 10;
  const viewportW = window.innerWidth;
  const viewportH = window.innerHeight;

  // Horizontally: prefer right-aligning with the launcher (it usually lives
  // in the top-right corner); fall back to left-aligned.
  let left = anchor.x + LAUNCHER_WIDTH - PANEL_WIDTH;
  if (left < EDGE_MARGIN) left = anchor.x;
  left = clampPanelBox({ x: left, y: 0 }).x;

  // 1. Below the launcher.
  const below = anchor.y + LAUNCHER_HEIGHT + gap;
  if (below + height <= viewportH - EDGE_MARGIN) {
    return { x: left, y: below, height };
  }

  // 2. Above the launcher.
  const above = anchor.y - height - gap;
  if (above >= EDGE_MARGIN) {
    return { x: left, y: above, height };
  }

  // 3. Beside it — left first, then right — vertically clamped.
  const besideY = clampPanelBox({ x: 0, y: anchor.y }).y;
  const toLeft = anchor.x - PANEL_WIDTH - gap;
  if (toLeft >= EDGE_MARGIN) {
    return { x: toLeft, y: besideY, height };
  }
  const toRight = anchor.x + LAUNCHER_WIDTH + gap;
  if (toRight + PANEL_WIDTH <= viewportW - EDGE_MARGIN) {
    return { x: toRight, y: besideY, height };
  }

  // 4. Viewport too small to avoid the launcher entirely. The launcher sits
  //    one z-layer above the panel, so it stays visible and still closes it.
  return clampPanelBox({ x: left, y: below });
}

function suggestionsFor(role: string | undefined): string[] {
  if (role === "teamlead") {
    return [
      "What is my team's total spending?",
      "Which of my labs needs attention?",
      "Show recent approved purchases for my team",
    ];
  }
  if (role === "labic") {
    return [
      "What is my lab's budget utilisation?",
      "Show my lab's spending by category",
      "How much budget do I have left?",
    ];
  }
  return [
    "Which labs are exceeding their budget?",
    "What is the total spend this fiscal year?",
    "Show me the top spending categories",
  ];
}

/** Earlier turns sent with each question so follow-ups ("and FCB?") work. */
const HISTORY_TURNS = 6;

function historyFrom(messages: ChatMessage[]): ChatTurn[] {
  return messages
    .slice(-HISTORY_TURNS)
    .map((m) => ({ role: m.role, content: m.text }));
}

export function AskAiWidget() {
  const { user } = useAuth();

  // Restore the last spot this browser left it in, during initial render so
  // the widget never paints at the wrong place first. A first-time visitor —
  // or a browser blocking storage — gets the top-right default.
  const [position, setPosition] = useState<Point>(() => {
    try {
      const saved = window.localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved) as Partial<Point>;
        if (typeof parsed.x === "number" && typeof parsed.y === "number") {
          return clampToViewport({ x: parsed.x, y: parsed.y });
        }
      }
    } catch {
      // Private mode / blocked storage — fall through to the default.
    }
    return clampToViewport(defaultPosition());
  });
  const [open, setOpen] = useState(false);
  /**
   * Panel position as an offset from the pill, fixed when the panel opens.
   * Null while closed. Keeps the panel glued to the pill during a drag.
   */
  const [panelOffset, setPanelOffset] = useState<Point | null>(null);
  const [dragging, setDragging] = useState(false);
  const [draft, setDraft] = useState("");
  const [thinking, setThinking] = useState(false);

  // Saved threads, newest-updated first. Restored during initial render so
  // the history is already there the first time the panel opens.
  const [conversations, setConversations] = useState<Conversation[]>(() =>
    loadConversations(),
  );
  const [activeId, setActiveId] = useState<string | null>(null);
  const [view, setView] = useState<"chat" | "history">("chat");

  // Offset between the pointer and the launcher's top-left, so the widget
  // doesn't jump to centre itself under the cursor on grab.
  const grabOffset = useRef<Point>({ x: 0, y: 0 });
  const pressOrigin = useRef<Point | null>(null);
  /** Mirrors `position` so drag handlers can read it without a stale closure. */
  const positionRef = useRef<Point>(position);
  const movedDuringPress = useRef(false);
  const messageIdRef = useRef(0);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  // Keep the widget on-screen when the window shrinks.
  useEffect(() => {
    const onResize = () => {
      const next = clampToViewport(positionRef.current);
      positionRef.current = next;
      setPosition(next);
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  // Esc closes the panel.
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        setPanelOffset(null);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  const active = conversations.find((c) => c.id === activeId) ?? null;
  const messages = active?.messages ?? [];

  // Pin the transcript to the newest message.
  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages.length, thinking, view]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  // Only threads that actually contain something are worth keeping.
  useEffect(() => {
    try {
      const keep = conversations
        .filter((c) => c.messages.length > 0)
        .slice(0, MAX_CONVERSATIONS);
      window.localStorage.setItem(CHATS_STORAGE_KEY, JSON.stringify(keep));
    } catch {
      // Blocked storage — history simply won't survive a reload.
    }
  }, [conversations]);

  const persist = useCallback((point: Point) => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(point));
    } catch {
      // Not worth surfacing; the position simply won't be remembered.
    }
  }, []);

  const handlePointerDown = (event: ReactPointerEvent<HTMLElement>) => {
    // Left button only, and never start a drag from a nested control.
    if (event.button !== 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    grabOffset.current = {
      x: event.clientX - position.x,
      y: event.clientY - position.y,
    };
    pressOrigin.current = { x: event.clientX, y: event.clientY };
    movedDuringPress.current = false;
    setDragging(true);
  };

  const handlePointerMove = (event: ReactPointerEvent<HTMLElement>) => {
    if (!dragging || !pressOrigin.current) return;
    const travelled =
      Math.abs(event.clientX - pressOrigin.current.x) +
      Math.abs(event.clientY - pressOrigin.current.y);
    if (travelled > DRAG_THRESHOLD) movedDuringPress.current = true;
    const next = clampToViewport({
      x: event.clientX - grabOffset.current.x,
      y: event.clientY - grabOffset.current.y,
    });
    positionRef.current = next;
    setPosition(next);
  };

  const handlePointerUp = (event: ReactPointerEvent<HTMLElement>) => {
    if (!dragging) return;
    event.currentTarget.releasePointerCapture(event.pointerId);
    setDragging(false);
    pressOrigin.current = null;
    persist(positionRef.current);
    if (open && movedDuringPress.current) {
      // Clamping during the drag can slide the panel out from under its
      // original offset and leave the pill sitting on top of it. Re-derive
      // the placement now that the pill has landed; the panel animates into
      // place because the transition is re-enabled once dragging stops.
      const box = panelPosition(positionRef.current);
      setPanelOffset({
        x: box.x - positionRef.current.x,
        y: box.y - positionRef.current.y,
      });
    }
  };

  /** A press that never travelled is a click — toggle the panel. */
  const handleLauncherClick = () => {
    if (movedDuringPress.current) return;
    if (open) {
      setOpen(false);
      setPanelOffset(null);
      return;
    }
    // Decide the placement once, on open, and remember it as an offset from
    // the pill. Dragging then moves the panel rigidly with the pill instead
    // of re-running the below/above/beside search on every pointer move,
    // which would make the panel jump sides mid-drag.
    const box = panelPosition(positionRef.current);
    setPanelOffset({
      x: box.x - positionRef.current.x,
      y: box.y - positionRef.current.y,
    });
    setOpen(true);
  };

  /** Append to a thread and float it to the top of the history list. */
  const appendMessage = (id: string, message: ChatMessage, title?: string) => {
    setConversations((prev) => {
      const next = prev.map((c) =>
        c.id === id
          ? {
              ...c,
              title: title ?? c.title,
              updatedAt: Date.now(),
              messages: [...c.messages, message],
            }
          : c,
      );
      return [...next].sort((a, b) => b.updatedAt - a.updatedAt);
    });
  };

  const submit = async (question: string) => {
    const trimmed = question.trim();
    if (!trimmed || thinking) return;
    setDraft("");

    // First message of the session opens a thread; the opening question
    // becomes its title, so history rows are recognisable.
    let id = activeId;
    let title: string | undefined;
    if (!id || !conversations.some((c) => c.id === id)) {
      const created = newConversation();
      id = created.id;
      setConversations((prev) => [created, ...prev]);
      setActiveId(created.id);
    }
    const current = conversations.find((c) => c.id === id);
    if (!current || current.messages.length === 0) {
      title = titleFrom(trimmed);
    }
    const history = historyFrom(current?.messages ?? []);

    appendMessage(
      id,
      {
        id: messageIdRef.current++,
        role: "user",
        text: trimmed,
      },
      title,
    );
    setThinking(true);
    try {
      const reply = await askAssistant(trimmed, history);
      appendMessage(id, {
        id: messageIdRef.current++,
        role: "assistant",
        text: reply.text,
        note: reply.note,
        sources: reply.sources,
      });
    } catch (error) {
      appendMessage(id, {
        id: messageIdRef.current++,
        role: "assistant",
        text:
          error instanceof Error
            ? `Sorry, I couldn't answer that: ${error.message}`
            : "Sorry, I couldn't answer that. Please try again.",
      });
    } finally {
      setThinking(false);
    }
  };

  /** Start a fresh thread — unless the current one is already untouched. */
  const startNewChat = () => {
    setView("chat");
    setDraft("");
    if (active && active.messages.length === 0) {
      inputRef.current?.focus();
      return;
    }
    // Drop any empty threads so History never fills with blanks.
    setConversations((prev) => prev.filter((c) => c.messages.length > 0));
    setActiveId(null);
    inputRef.current?.focus();
  };

  const openConversation = (id: string) => {
    setActiveId(id);
    setView("chat");
  };

  const deleteConversation = (id: string) => {
    setConversations((prev) => prev.filter((c) => c.id !== id));
    if (activeId === id) setActiveId(null);
  };

  // While open, follow the frozen offset (clamped so a drag toward an edge
  // can never push the panel off-screen). Before that, fall back to a fresh
  // placement search.
  const panel = panelOffset
    ? clampPanelBox({
        x: position.x + panelOffset.x,
        y: position.y + panelOffset.y,
      })
    : panelPosition(position);
  const suggestions = suggestionsFor(user?.role);

  return (
    <>
      {/* Launcher */}
      <button
        type="button"
        aria-label={open ? "Close the AI assistant" : "Open the AI assistant"}
        aria-expanded={open}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onClick={handleLauncherClick}
        style={{
          left: position.x,
          top: position.y,
          width: LAUNCHER_WIDTH,
          height: LAUNCHER_HEIGHT,
        }}
        className={cn(
          "fixed z-[41] flex items-center justify-center gap-2 rounded-full",
          // Screen-only chrome; never wanted on a printed page.
          "no-print",
          "bg-[#1e3a8a] text-white shadow-lg ring-1 ring-black/5",
          "transition-colors hover:bg-[#1e40af]",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#1e3a8a] focus-visible:ring-offset-2",
          dragging ? "cursor-grabbing" : "cursor-grab",
          // Stop the browser panning the page when dragging on touch.
          "touch-none select-none",
        )}
      >
        <Sparkles className="h-4 w-4 shrink-0" />
        <span className="text-sm font-semibold">Ask AI</span>
      </button>

      {/* Chat panel */}
      {open && (
        <div
          role="dialog"
          aria-label="AI assistant"
          style={{
            left: panel.x,
            top: panel.y,
            width: PANEL_WIDTH,
            height: panel.height,
            transition: dragging ? "none" : "left 150ms ease, top 150ms ease",
          }}
          className={cn(
            "fixed z-40 flex flex-col overflow-hidden rounded-xl no-print",
            "border border-border bg-white shadow-2xl",
            "animate-in fade-in zoom-in-95 duration-150",
          )}
        >
          {/* Header. Deliberately NOT a drag handle: the panel's placement is
              derived from the launcher, so dragging it here would make the
              panel flip sides under the cursor. Move the pill instead. */}
          <div className="flex select-none items-center gap-1 border-b border-border bg-[#1e3a8a] px-2 py-2.5 text-white">
            {view === "history" ? (
              <button
                type="button"
                aria-label="Back to chat"
                onClick={() => setView("chat")}
                className="rounded-md p-1.5 transition-colors hover:bg-white/15"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
            ) : (
              <span className="pl-1.5">
                <Sparkles className="h-4 w-4" />
              </span>
            )}

            <div className="min-w-0 flex-1 px-1">
              <p className="truncate text-sm font-semibold leading-tight">
                {view === "history" ? "Previous chats" : "Ask AI"}
              </p>
              <p className="truncate text-xs text-white/70">
                {view === "history"
                  ? `${conversations.length} saved`
                  : active?.messages.length
                    ? active.title
                    : "Budget questions, answered from your data"}
              </p>
            </div>

            {view === "chat" && (
              <>
                <button
                  type="button"
                  aria-label="New chat"
                  title="New chat"
                  onClick={startNewChat}
                  className="rounded-md p-1.5 transition-colors hover:bg-white/15"
                >
                  <SquarePen className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  aria-label="Previous chats"
                  title="Previous chats"
                  onClick={() => setView("history")}
                  className="relative rounded-md p-1.5 transition-colors hover:bg-white/15"
                >
                  <History className="h-4 w-4" />
                  {conversations.length > 0 && (
                    <span className="absolute right-0.5 top-0.5 flex h-3.5 min-w-3.5 items-center justify-center rounded-full bg-white px-1 text-[9px] font-semibold text-[#1e3a8a]">
                      {conversations.length}
                    </span>
                  )}
                </button>
              </>
            )}

            <button
              type="button"
              aria-label="Close"
              onClick={() => {
                setOpen(false);
                setPanelOffset(null);
              }}
              className="rounded-md p-1.5 transition-colors hover:bg-white/15"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* History list — replaces the transcript while browsing. */}
          {view === "history" && (
            <div className="flex-1 overflow-y-auto p-2">
              {conversations.length === 0 ? (
                <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
                  <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#f1f5f9]">
                    <History className="h-5 w-5 text-muted-foreground" />
                  </div>
                  <p className="text-sm font-medium text-foreground">
                    No previous chats
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Conversations you start are saved here, on this browser.
                  </p>
                </div>
              ) : (
                <ul className="space-y-1">
                  {conversations.map((conversation) => (
                    <li key={conversation.id}>
                      <div
                        className={cn(
                          "group flex items-center gap-2 rounded-lg border px-2.5 py-2 transition-colors",
                          conversation.id === activeId
                            ? "border-[#1e3a8a] bg-[#f0f9ff]"
                            : "border-transparent hover:border-border hover:bg-[#f8fafc]",
                        )}
                      >
                        <button
                          type="button"
                          onClick={() => openConversation(conversation.id)}
                          className="min-w-0 flex-1 text-left"
                        >
                          <p className="truncate text-xs font-medium text-foreground">
                            {conversation.title}
                          </p>
                          <p className="mt-0.5 text-[11px] text-muted-foreground">
                            {conversation.messages.length} message
                            {conversation.messages.length === 1
                              ? ""
                              : "s"} · {relativeTime(conversation.updatedAt)}
                          </p>
                        </button>
                        <button
                          type="button"
                          aria-label={`Delete "${conversation.title}"`}
                          onClick={() => deleteConversation(conversation.id)}
                          className="shrink-0 rounded-md p-1.5 text-muted-foreground opacity-0 transition-opacity hover:bg-[#fef2f2] hover:text-[#dc2626] focus-visible:opacity-100 group-hover:opacity-100"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {view === "chat" && (
            <>
              {/* Grounding notice */}
              <div className="border-b border-[#bfdbfe] bg-[#f0f9ff] px-3 py-2">
                <p className="text-xs text-[#1e40af]">
                  AI answers use only the budget data your role can see. Check
                  key figures on the dashboard before acting on them.
                </p>
              </div>

              {/* Transcript */}
              <div
                ref={scrollRef}
                className="flex-1 space-y-3 overflow-y-auto px-3 py-3"
              >
                {messages.length === 0 && !thinking && (
                  <div className="space-y-3">
                    <div className="flex flex-col items-center gap-2 py-4 text-center">
                      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#eef2ff]">
                        <Sparkles className="h-5 w-5 text-[#1e3a8a]" />
                      </div>
                      <p className="text-sm font-medium text-foreground">
                        How can I help?
                      </p>
                      <p className="text-xs text-muted-foreground">
                        Ask about budgets, spending or purchase requests.
                      </p>
                    </div>
                    <div className="space-y-1.5">
                      <p className="px-1 text-xs font-medium text-muted-foreground">
                        Try one of these
                      </p>
                      {suggestions.map((prompt) => (
                        <button
                          key={prompt}
                          type="button"
                          onClick={() => submit(prompt)}
                          className={cn(
                            "w-full rounded-lg border border-border bg-white px-3 py-2 text-left",
                            "text-xs text-foreground transition-colors hover:border-[#1e3a8a] hover:bg-[#f8fafc]",
                          )}
                        >
                          {prompt}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {messages.map((message) => (
                  <div
                    key={message.id}
                    className={cn(
                      "flex",
                      message.role === "user" ? "justify-end" : "justify-start",
                    )}
                  >
                    <div className="flex max-w-[85%] flex-col gap-1">
                      <div
                        className={cn(
                          "whitespace-pre-wrap rounded-2xl px-3 py-2 text-xs leading-relaxed",
                          message.role === "user"
                            ? "rounded-br-sm bg-[#1e3a8a] text-white"
                            : "rounded-bl-sm bg-[#f1f5f9] text-foreground",
                        )}
                      >
                        {message.text}
                      </div>
                      {message.sources && message.sources.length > 0 && (
                        <div className="px-1 text-[10px] text-muted-foreground">
                          <p className="font-medium">Sources</p>
                          <ul className="space-y-0.5">
                            {message.sources.map((source) => (
                              <li key={source.ref}>
                                <span className="font-medium">{source.ref}</span>
                                {" · "}
                                {source.detail}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {message.note && (
                        <p className="px-1 text-[10px] text-muted-foreground">
                          {message.note}
                        </p>
                      )}
                    </div>
                  </div>
                ))}

                {thinking && (
                  <div className="flex justify-start">
                    <div className="flex items-center gap-1 rounded-2xl rounded-bl-sm bg-[#f1f5f9] px-3 py-2.5">
                      {[0, 150, 300].map((delay) => (
                        <span
                          key={delay}
                          style={{ animationDelay: `${delay}ms` }}
                          className="h-1.5 w-1.5 animate-bounce rounded-full bg-[#94a3b8]"
                        />
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Composer */}
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  submit(draft);
                }}
                className="flex items-center gap-2 border-t border-border bg-white px-3 py-2.5"
              >
                <input
                  ref={inputRef}
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  placeholder="Ask about your budgets..."
                  disabled={thinking}
                  className={cn(
                    "min-w-0 flex-1 rounded-lg border border-gray-300 px-3 py-2 text-xs outline-none transition-all",
                    "placeholder:text-muted-foreground",
                    "focus:border-[#1e3a8a] focus:ring-2 focus:ring-[#1e3a8a]/20",
                    "disabled:cursor-not-allowed disabled:bg-muted",
                  )}
                />
                <button
                  type="submit"
                  aria-label="Send"
                  disabled={!draft.trim() || thinking}
                  className={cn(
                    "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-white transition-colors",
                    "bg-[#1e3a8a] hover:bg-[#1e40af]",
                    "disabled:cursor-not-allowed disabled:opacity-40",
                  )}
                >
                  <Send className="h-4 w-4" />
                </button>
              </form>
            </>
          )}
        </div>
      )}
    </>
  );
}
