/**
 * Reusable Top Navigation Bar Component for SQLite AI Sandbox
 * Automatically injects a consistent sticky header with emojis and active-page highlighting
 * across all HTML pages in the project.
 */
(function () {
  const NAV_ITEMS = [
    { href: "index.html", emoji: "🏠", label: "Overview & Sandbox" },
    { href: "sql-playground.html", emoji: "🛠️", label: "SQL & CRUD Studio" },
    { href: "fly-persistence.html", emoji: "💾", label: "Fly.io Persistence" },
    { href: "fly-costs.html", emoji: "💰", label: "Fly.io Volume Costs" },
    { href: "architecture.html", emoji: "📐", label: "Architecture Blueprint" },
    { href: "files-and-run.html", emoji: "📂", label: "Files & Run Guide" }
  ];

  function getActiveFilename() {
    const path = window.location.pathname;
    const base = path.split("/").pop();
    return base && base.endsWith(".html") ? base : "index.html";
  }

  function injectSharedNavStyles() {
    if (document.getElementById("shared-nav-styles")) return;
    const style = document.createElement("style");
    style.id = "shared-nav-styles";
    style.textContent = `
      .reusable-topbar {
        position: sticky;
        top: 0;
        z-index: 100;
        backdrop-filter: blur(14px);
        background: rgba(7, 11, 20, 0.92);
        border-bottom: 1px solid #2e3f5c;
        padding: 0.75rem 1.75rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
        flex-wrap: wrap;
        gap: 0.85rem;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, sans-serif;
      }
      .reusable-brand {
        display: flex;
        align-items: center;
        gap: 0.65rem;
        font-weight: 700;
        font-size: 1.02rem;
        color: #f1f5f9;
        text-decoration: none;
      }
      .reusable-brand:hover {
        text-decoration: none;
        color: #38bdf8;
      }
      .reusable-badge {
        font-family: "JetBrains Mono", "SFMono-Regular", Consolas, monospace;
        font-size: 0.72rem;
        padding: 0.18rem 0.55rem;
        border-radius: 999px;
        background: rgba(56, 189, 248, 0.15);
        color: #38bdf8;
        border: 1px solid rgba(56, 189, 248, 0.35);
      }
      .reusable-nav-links {
        display: flex;
        align-items: center;
        gap: 0.45rem;
        flex-wrap: wrap;
      }
      .reusable-nav-link {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        padding: 0.42rem 0.75rem;
        border-radius: 8px;
        font-size: 0.84rem;
        font-weight: 600;
        color: #94a3b8;
        text-decoration: none;
        border: 1px solid transparent;
        transition: all 0.15s ease;
      }
      .reusable-nav-link:hover {
        color: #e2e8f0;
        background: rgba(255, 255, 255, 0.04);
        border-color: #2e3f5c;
        text-decoration: none;
      }
      .reusable-nav-link.active {
        color: #38bdf8;
        background: rgba(56, 189, 248, 0.12);
        border-color: rgba(56, 189, 248, 0.4);
      }
    `;
    document.head.appendChild(style);
  }

  function renderNavbar() {
    injectSharedNavStyles();
    const currentFile = getActiveFilename();
    const linksHtml = NAV_ITEMS.map((item) => {
      const isActive = item.href === currentFile ? "active" : "";
      return `<a href="${item.href}" class="reusable-nav-link ${isActive}"><span>${item.emoji}</span><span>${item.label}</span></a>`;
    }).join("");

    const navHtml = `
      <a href="index.html" class="reusable-brand">
        <span>📦 SQLite AI Sandbox</span>
        <span class="reusable-badge" id="global-nav-badge">🐍 sqlite3 • 💾 /data NVMe</span>
      </a>
      <nav class="reusable-nav-links" aria-label="Main Navigation">
        ${linksHtml}
      </nav>
    `;

    const existingHeader = document.querySelector("header.topbar, #reusable-navbar");
    if (existingHeader) {
      existingHeader.className = "reusable-topbar";
      existingHeader.id = "reusable-navbar";
      existingHeader.innerHTML = navHtml;
    } else {
      const header = document.createElement("header");
      header.className = "reusable-topbar";
      header.id = "reusable-navbar";
      header.innerHTML = navHtml;
      document.body.prepend(header);
    }

    // Fetch live engine version + mount status to enrich the reusable badge
    fetch("/api/status")
      .then((r) => r.json())
      .then((snap) => {
        const badge = document.getElementById("global-nav-badge");
        if (badge && snap && snap.engine) {
          const mountLabel = snap.engine.persistent_volume_mounted ? "💾 /data Fly NVMe" : "💻 Local Disk";
          badge.textContent = `🐍 SQLite ${snap.engine.sqlite_version} • ${mountLabel}`;
        }
      })
      .catch(() => {});
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", renderNavbar);
  } else {
    renderNavbar();
  }
})();
