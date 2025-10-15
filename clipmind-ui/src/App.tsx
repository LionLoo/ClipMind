import { useEffect, useMemo, useRef, useState } from "react";
import "./App.css";
import {
  WebviewWindow,
  getCurrentWebviewWindow,
} from "@tauri-apps/api/webviewWindow";
import {
  register,
  unregister,
  isRegistered,
} from "@tauri-apps/plugin-global-shortcut";
import { writeText, writeImage } from "@tauri-apps/plugin-clipboard-manager";

type HKStatus = "pending" | "ok" | "exists" | "failed";

interface ClipItem {
  id: number;
  text: string;
  source: string;a
  blob_uri: string | null;
  created_ts: number;
  readable_time: string;
  score?: number;
  preview?: string;
}

function useCurrentLabel() {
  const [label, setLabel] = useState<string>("(loading)");
  useEffect(() => {
    (async () => {
      try {
        const w = await getCurrentWebviewWindow();
        setLabel(w.label);
      } catch (e) {
        setLabel("(error getting label)");
      }
    })();
  }, []);
  return label;
}

async function waitForCreated(win: WebviewWindow) {
  return new Promise<void>((resolve, reject) => {
    const offCreated = win.once("tauri://created", () => {
      offCreated();
      offError();
      resolve();
    });
    const offError = win.once("tauri://error", (e) => {
      offCreated();
      offError();
      reject(typeof e === "string" ? new Error(e) : (e as any));
    });
  });
}

async function ensureQuickboardWindow(log: (s: string) => void, pushErr: (s: string) => void) {
  try {
    let qb = WebviewWindow.getByLabel("quickboard");
    if (qb) return qb;

    log("[qb] creating quickboard webview...");
    qb = new WebviewWindow("quickboard", {
      url: "index.html",
      visible: false,
      decorations: false,
      transparent: true,
      alwaysOnTop: true,
      resizable: false,
      skipTaskbar: true,
      focus: true,
      width: 900,
      height: 580,
    });

    try {
      await waitForCreated(qb);
      log("[qb] created");
    } catch (e: any) {
      const msg = `[qb] create failed: ${e?.message ?? String(e)}`;
      pushErr(msg);
      throw new Error(msg);
    }
    return qb;
  } catch (e: any) {
    pushErr(`[qb] ensure failed: ${e?.message ?? String(e)}`);
    throw e;
  }
}

let lastToggleTime = 0;
const TOGGLE_COOLDOWN_MS = 300;

async function toggleQuickboard(log: (s: string) => void, pushErr: (s: string) => void) {
  const now = Date.now();
  if (now - lastToggleTime < TOGGLE_COOLDOWN_MS) {
    log("[qb] toggle blocked (cooldown)");
    return;
  }
  lastToggleTime = now;

  const qb = await ensureQuickboardWindow(log, pushErr);
  try {
    const visible = await qb.isVisible();
    if (visible) {
      await qb.hide();
      log("[qb] hide");
    } else {
      await qb.center();
      await qb.show();
      await qb.setFocus();
      log("[qb] show + focus + center");
    }
  } catch (e: any) {
    pushErr(`[qb] toggle failed: ${e?.message ?? String(e)}`);
  }
}

export default function App() {
  const label = useCurrentLabel();
  const isQuickboard = useMemo(() => label === "quickboard", [label]);

  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<"all" | "text" | "images" | "clipboard">("all");
  const [timeRange, setTimeRange] = useState<string>("all");
  const [items, setItems] = useState<ClipItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [backendStatus, setBackendStatus] = useState<"checking" | "online" | "offline">("checking");

  const [hkStatuses, setHkStatuses] = useState<Record<string, HKStatus>>({});
  const [errors, setErrors] = useState<string[]>([]);
  const [logs, setLogs] = useState<string[]>([]);
  const [stats, setStats] = useState<any>(null);
  const didAutoOpen = useRef(false);

  const log = (s: string) => setLogs((L) => [...L, s]);
  const pushErr = (s: string) => setErrors((E) => [...E, s]);

  const hotkeys = ["CommandOrControl+Shift+Space"];

  // Check backend health
  useEffect(() => {
    const checkBackend = async () => {
      try {
        const res = await fetch("http://localhost:8000/");
        if (res.ok) {
          setBackendStatus("online");
          log("[backend] connected");

          // Fetch stats
          const statsRes = await fetch("http://localhost:8000/stats");
          if (statsRes.ok) {
            const data = await statsRes.json();
            setStats(data);
          }
        } else {
          setBackendStatus("offline");
        }
      } catch {
        setBackendStatus("offline");
      }
    };

    checkBackend();
    const interval = setInterval(checkBackend, 5000);
    return () => clearInterval(interval);
  }, []);

  // Fetch items when query or filter changes
  useEffect(() => {
    if (!isQuickboard || backendStatus !== "online") return;

    const fetchItems = async () => {
      setLoading(true);
      try {
        // Calculate time filter
        let afterTimestamp: number | null = null;
        const now = Math.floor(Date.now() / 1000);

        switch (timeRange) {
          case "hour":
            afterTimestamp = now - 3600;
            break;
          case "day":
            afterTimestamp = now - 86400;
            break;
          case "week":
            afterTimestamp = now - 604800;
            break;
          case "month":
            afterTimestamp = now - 2592000;
            break;
          // "all" = no filter
        }

        if (q.trim()) {
          // Semantic search with mode
          const mode = filter === "all" ? "all" : filter === "text" ? "text" : filter === "images" ? "images" : "clipboard";
          const url = new URL("http://localhost:8000/search");
          url.searchParams.set("q", q.trim());
          url.searchParams.set("k", "20");
          url.searchParams.set("mode", mode);
          if (afterTimestamp) {
            url.searchParams.set("after", afterTimestamp.toString());
          }

          console.log('[DEBUG] Searching:', url.toString());
          const res = await fetch(url.toString());
          const data = await res.json();
          console.log('[DEBUG] Search results:', data);
          setItems(data.results || []);
        } else {
          // Get recent items
          const sourceFilter = filter === "clipboard" ? "clipboard" : filter === "images" ? "screenshot" : null;
          const url = new URL("http://localhost:8000/items/recent");
          url.searchParams.set("limit", "20");
          if (sourceFilter) url.searchParams.set("source", sourceFilter);
          if (afterTimestamp) {
            url.searchParams.set("after", afterTimestamp.toString());
          }

          console.log('[DEBUG] Fetching recent:', url.toString());
          const res = await fetch(url.toString());
          const data = await res.json();
          console.log('[DEBUG] Recent items:', data);
          setItems(data.items || []);
        }
      } catch (e: any) {
        console.error("[DEBUG] Fetch failed:", e);
        setItems([]);
      } finally {
        setLoading(false);
      }
    };

    const debounce = setTimeout(fetchItems, 300);
    return () => clearTimeout(debounce);
  }, [q, filter, timeRange, isQuickboard, backendStatus]);

  // Auto-refresh recent items every 2 seconds when quickboard is visible
  useEffect(() => {
    if (!isQuickboard || backendStatus !== "online") return;
    if (q.trim()) return; // Don't auto-refresh during search

    const interval = setInterval(async () => {
      try {
        const sourceFilter = filter === "clipboard" ? "clipboard" : filter === "images" ? "screenshot" : null;
        const url = new URL("http://localhost:8000/items/recent");
        url.searchParams.set("limit", "20");
        if (sourceFilter) url.searchParams.set("source", sourceFilter);

        // Apply time filter
        const now = Math.floor(Date.now() / 1000);
        let afterTimestamp: number | null = null;
        switch (timeRange) {
          case "hour": afterTimestamp = now - 3600; break;
          case "day": afterTimestamp = now - 86400; break;
          case "week": afterTimestamp = now - 604800; break;
          case "month": afterTimestamp = now - 2592000; break;
        }
        if (afterTimestamp) {
          url.searchParams.set("after", afterTimestamp.toString());
        }

        const res = await fetch(url.toString());
        const data = await res.json();
        setItems(data.items || []);
      } catch (e) {
        // Silently fail - don't disrupt user experience
      }
    }, 2000); // Refresh every 2 seconds

    return () => clearInterval(interval);
  }, [isQuickboard, backendStatus, q, filter, timeRange]);

  // Copy item to clipboard and close
  const handleItemClick = async (item: ClipItem) => {
  try {
    if (item.source === "screenshot" && item.blob_uri) {
      await writeImage(item.blob_uri);
      log(`[qb] copied image ${item.id}`);
    } else {
      await writeText(item.text);
      log(`[qb] copied text ${item.id}`);
    }
    const w = await getCurrentWebviewWindow();
    await w.hide();
  } catch (e: any) {
    console.error("[DEBUG] Copy failed:", e);
    pushErr(`[qb] copy failed: ${e?.message ?? String(e)}`);
    alert(`Copy failed: ${e?.message ?? String(e)}`);
  }
};

  useEffect(() => {
    (async () => {
      try {
        const current = await getCurrentWebviewWindow();
        log(`[env] current label = ${current.label}`);

        if (current.label === "main") {
          const init: Record<string, HKStatus> = {};
          hotkeys.forEach((hk) => (init[hk] = "pending"));
          setHkStatuses(init);

          await ensureQuickboardWindow(log, pushErr);

          for (const hk of hotkeys) {
            try {
              const already = await isRegistered(hk);
              if (already) {
                await unregister(hk);
                log(`[hk] unregistered existing: ${hk}`);
              }

              await register(hk, async () => {
                log(`[hk] fired: ${hk}`);
                await toggleQuickboard(log, pushErr);
              });
              log(`[hk] registered: ${hk}`);
              setHkStatuses((s) => ({ ...s, [hk]: "ok" }));
            } catch (e: any) {
              const msg = `[hk] register failed ${hk}: ${e?.message ?? String(e)}`;
              pushErr(msg);
              setHkStatuses((s) => ({ ...s, [hk]: "failed" }));
            }
          }

          // Keepalive: Re-register hotkeys every 30 seconds to prevent them from dying
          const keepalive = setInterval(async () => {
            for (const hk of hotkeys) {
              try {
                const registered = await isRegistered(hk);
                if (!registered) {
                  log(`[hk] re-registering dead hotkey: ${hk}`);
                  await register(hk, async () => {
                    log(`[hk] fired: ${hk}`);
                    await toggleQuickboard(log, pushErr);
                  });
                }
              } catch (e: any) {
                pushErr(`[hk] keepalive failed: ${e?.message ?? String(e)}`);
              }
            }
          }, 30000); // Every 30 seconds

          if (import.meta.env.DEV && !didAutoOpen.current) {
            didAutoOpen.current = true;
            setTimeout(() => {
              toggleQuickboard(log, pushErr);
            }, 500);
          }

          // Cleanup keepalive on unmount
          return () => clearInterval(keepalive);
        }

        if (current.label === "quickboard") {
          log("[qb] ready (quickboard webview)");
        }
      } catch (e: any) {
        pushErr(`[init] ${e?.message ?? String(e)}`);
      }
    })();

    return () => {
      hotkeys.forEach((hk) => unregister(hk).catch(() => {}));
    };
  }, []);

  // MAIN window dashboard
  if (!isQuickboard) {
    return (
      <div style={{
        width: "100vw",
        height: "100vh",
        background: "#111",
        color: "#ddd",
        fontFamily: "Inter, system-ui, sans-serif",
        display: "grid",
        placeItems: "center"
      }}>
        <div style={{ width: 640, maxWidth: "92%", lineHeight: 1.5 }}>
          <h2 style={{ margin: 0, color: "#9bd" }}>ClipMind Dashboard</h2>
          <p style={{ marginTop: 6, opacity: 0.85 }}>
            Current window: <code>{label}</code>
          </p>

          <div style={{ marginTop: 12, padding: 12, background: "#1a1a1a", borderRadius: 10 }}>
            <div style={{ fontWeight: 600, marginBottom: 8 }}>Backend Status</div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: backendStatus === "online" ? "#6dd57e" : backendStatus === "offline" ? "#ff6b6b" : "#888"
              }} />
              <span>{backendStatus === "online" ? "Connected to API" : backendStatus === "offline" ? "Offline" : "Checking..."}</span>
            </div>
            {backendStatus === "offline" && (
              <div style={{ marginTop: 8, fontSize: 13, opacity: 0.8 }}>
                Start backend: <code>python -m uvicorn app.api.server:app --reload</code>
              </div>
            )}
            {stats && (
              <div style={{ marginTop: 12, fontSize: 13, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                <div>Total Items: <strong>{stats.total_items}</strong></div>
                <div>Clipboard: <strong>{stats.clipboard_items}</strong></div>
                <div>Screenshots: <strong>{stats.screenshot_items}</strong></div>
                <div>Text Vectors: <strong>{stats.text_vectors}</strong></div>
              </div>
            )}
          </div>

          <div style={{ marginTop: 12, padding: 12, background: "#1a1a1a", borderRadius: 10 }}>
            <div style={{ fontWeight: 600, marginBottom: 8 }}>Hotkey Status</div>
            {hotkeys.map((hk) => {
              const st = hkStatuses[hk] ?? "pending";
              const color =
                st === "ok" || st === "exists" ? "#6dd57e"
                : st === "failed" ? "#ff6b6b"
                : "#aaa";
              return (
                <div key={hk} style={{ display: "flex", justifyContent: "space-between", margin: "6px 0" }}>
                  <code style={{ opacity: 0.9 }}>{hk}</code>
                  <span style={{ color }}>{st}</span>
                </div>
              );
            })}
          </div>

          {logs.length > 0 && (
            <div style={{ marginTop: 12, padding: 12, background: "#151a20", borderRadius: 10, maxHeight: 200, overflow: "auto" }}>
              <div style={{ fontWeight: 600, marginBottom: 8 }}>Logs</div>
              <div style={{ fontFamily: "ui-monospace, monospace", fontSize: 12, whiteSpace: "pre-wrap" }}>
                {logs.slice(-15).join("\n")}
              </div>
            </div>
          )}

          {errors.length > 0 && (
            <div style={{ marginTop: 12, padding: 12, background: "#291a1a", borderRadius: 10, color: "#ff9b9b" }}>
              <div style={{ fontWeight: 600, marginBottom: 8 }}>Errors</div>
              <div style={{ fontFamily: "ui-monospace, monospace", fontSize: 12, whiteSpace: "pre-wrap" }}>
                {errors.join("\n")}
              </div>
            </div>
          )}

          <div style={{ marginTop: 16 }}>
            <button
              onClick={() => toggleQuickboard(log, pushErr)}
              style={{ padding: "10px 16px", borderRadius: 8, background: "#2b7cff", color: "#fff", border: "none", cursor: "pointer" }}
            >
              Toggle Quickboard (Ctrl+Shift+Space)
            </button>
          </div>
        </div>
      </div>
    );
  }

  // QUICKBOARD UI
  return (
    <div className="quickboard">
      <div className="top-bar">
        <div className="search-container">
          <span className="search-icon">🔎</span>
          <input
            className="search-input"
            placeholder="Search clipboard & screenshots..."
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={async (e) => {
              if (e.key === "Escape") {
                e.preventDefault();
                const w = await getCurrentWebviewWindow();
                await w.hide();
              }
            }}
            autoFocus
          />
        </div>
        <div className="filter-buttons">
          {(["all", "text", "images", "clipboard"] as const).map((f) => (
            <button
              key={f}
              className={`filter-btn ${filter === f ? "active" : ""}`}
              onClick={() => setFilter(f)}
            >
              {f === "all" ? "All" : f === "text" ? "Text" : f === "images" ? "Images" : "Clipboard"}
            </button>
          ))}
        </div>
        <div className="filter-buttons" style={{ marginLeft: "8px" }}>
          <select
            value={timeRange}
            onChange={(e) => setTimeRange(e.target.value)}
            style={{
              background: "#2d2d2d",
              color: "#ffffff",
              border: "none",
              borderRadius: "4px",
              padding: "8px 12px",
              cursor: "pointer",
              fontSize: "14px"
            }}
          >
            <option value="all">All Time</option>
            <option value="hour">Past Hour</option>
            <option value="day">Today</option>
            <option value="week">Past Week</option>
            <option value="month">Past Month</option>
          </select>
        </div>
      </div>

      <div className="items-container">
        {backendStatus === "offline" && (
          <div className="no-items">Backend offline - Start with: python -m uvicorn app.api.server:app --reload</div>
        )}
        {backendStatus === "online" && loading && (
          <div className="loading">Searching...</div>
        )}
        {backendStatus === "online" && !loading && items.length === 0 && (
          <div className="no-items">No items found</div>
        )}
        {backendStatus === "online" && !loading && items.map((item) => (
          <div key={item.id} className="item" onClick={() => handleItemClick(item)}>
            <div className="item-icon">
              {item.source === "clipboard" ? "📋" : "🖼️"}
            </div>
            <div className="item-content">
              {item.source === "screenshot" && item.blob_uri ? (
                <div style={{ display: "flex", gap: "12px", alignItems: "center", width: "100%" }}>
                  <img
                    src={`http://localhost:8000/item/${item.id}/image`}
                    alt="Screenshot preview"
                    style={{
                      width: "80px",
                      height: "60px",
                      objectFit: "cover",
                      borderRadius: "4px",
                      flexShrink: 0
                    }}
                    onError={(e) => {
                      // Fallback if image fails to load
                      e.currentTarget.style.display = "none";
                    }}
                  />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="item-text">{item.preview || item.text}</div>
                    <div className="item-time">
                      {item.readable_time || new Date(item.created_ts * 1000).toLocaleString()}
                      {item.score !== undefined && <span> • Score: {item.score.toFixed(2)}</span>}
                    </div>
                  </div>
                </div>
              ) : (
                <>
                  <div className="item-text">{item.preview || item.text}</div>
                  <div className="item-time">
                    {item.readable_time || new Date(item.created_ts * 1000).toLocaleString()}
                    {item.score !== undefined && <span> • Score: {item.score.toFixed(2)}</span>}
                  </div>
                </>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}