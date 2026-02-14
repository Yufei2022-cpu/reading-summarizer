/* ==========================================================
   AI Frontier Digest — app.js
   Pure-JS renderer for DigestOutput JSON (schema v1)
   ========================================================== */

(() => {
    "use strict";

    /* ---------- DOM refs ---------- */
    const $ = (s) => document.querySelector(s);
    const $$ = (s) => [...document.querySelectorAll(s)];

    const searchInput = $("#search-input");
    const statsBar = $("#stats-bar");
    const tagBar = $("#tag-bar");
    const tagBarInner = $(".tag-bar-inner");
    const topStoriesSec = $("#top-stories");
    const topGrid = $("#top-stories-grid");
    const sectionsEl = $("#sections-container");
    const dupSection = $("#duplicates-section");
    const dupToggle = $("#dup-toggle");
    const dupContent = $("#dup-content");
    const loadZone = $("#load-zone");
    const loadZoneInner = $(".load-zone-inner");
    const schemaVerEl = $("#schema-ver");
    const searchResults = $("#search-results");
    const searchInner = $(".search-results-inner");
    const themeToggle = $("#theme-toggle");

    let digestData = null;
    let activeTag = "all";

    /* ---------- Theme ---------- */
    const savedTheme = localStorage.getItem("digest-theme") || "dark";
    document.documentElement.setAttribute("data-theme", savedTheme);

    themeToggle.addEventListener("click", () => {
        const current = document.documentElement.getAttribute("data-theme");
        const next = current === "dark" ? "light" : "dark";
        document.documentElement.setAttribute("data-theme", next);
        localStorage.setItem("digest-theme", next);
    });

    /* ---------- Keyboard shortcut ---------- */
    document.addEventListener("keydown", (e) => {
        if (e.key === "/" && document.activeElement !== searchInput) {
            e.preventDefault();
            searchInput.focus();
        }
        if (e.key === "Escape") {
            searchInput.value = "";
            searchInput.blur();
            handleSearch("");
        }
    });

    /* ---------- Search ---------- */
    let searchTimer;
    searchInput.addEventListener("input", (e) => {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(() => handleSearch(e.target.value.trim()), 200);
    });

    function handleSearch(query) {
        if (!digestData || !query) {
            searchResults.classList.add("hidden");
            topStoriesSec.classList.remove("hidden");
            sectionsEl.classList.remove("hidden");
            tagBar.classList.remove("hidden");
            return;
        }

        const q = query.toLowerCase();

        // Check search_summaries first
        const hints = (digestData.search_summaries || []).filter(
            (s) =>
                s.query_hint.toLowerCase().includes(q) ||
                s.matching_tags.some((t) => t.toLowerCase().includes(q))
        );

        // Search top_stories
        const matchedStories = digestData.top_stories.filter(
            (s) =>
                s.title.toLowerCase().includes(q) ||
                s.one_liner.toLowerCase().includes(q) ||
                s.tags.some((t) => t.toLowerCase().includes(q)) ||
                (s.subtitle && s.subtitle.toLowerCase().includes(q)) ||
                (s.source && s.source.toLowerCase().includes(q))
        );

        // Hide main content, show results
        topStoriesSec.classList.add("hidden");
        sectionsEl.classList.add("hidden");
        tagBar.classList.add("hidden");
        searchResults.classList.remove("hidden");

        searchInner.innerHTML = "";

        if (hints.length > 0) {
            hints.forEach((h) => {
                const card = document.createElement("div");
                card.className = "search-hint-card";
                card.innerHTML = `
          <div class="hint-query">🔍 ${esc(h.query_hint)}</div>
          <div class="hint-map">${esc(h.one_sentence_map)}</div>
        `;
                searchInner.appendChild(card);
            });
        }

        if (matchedStories.length > 0) {
            matchedStories.forEach((s) => {
                searchInner.appendChild(buildCompactCard(s));
            });
        }

        if (hints.length === 0 && matchedStories.length === 0) {
            searchInner.innerHTML = `<div style="text-align:center;color:var(--text-2);padding:2rem;">未找到匹配 "${esc(query)}" 的结果</div>`;
        }
    }

    /* ---------- Load handlers ---------- */
    // Sample
    $("#load-sample-btn").addEventListener("click", async () => {
        try {
            const resp = await fetch("sample_digest.json");
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            boot(data);
        } catch (e) {
            alert("加载示例数据失败：" + e.message);
        }
    });

    // File picker
    $("#file-input").addEventListener("change", (e) => {
        const file = e.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = (ev) => {
            try {
                boot(JSON.parse(ev.target.result));
            } catch (err) {
                alert("JSON 解析失败：" + err.message);
            }
        };
        reader.readAsText(file);
    });

    // URL
    $("#load-url-btn").addEventListener("click", async () => {
        const url = $("#url-input").value.trim();
        if (!url) return;
        try {
            const resp = await fetch(url);
            boot(await resp.json());
        } catch (e) {
            alert("加载失败：" + e.message);
        }
    });

    // Drag & drop
    loadZoneInner.addEventListener("dragover", (e) => {
        e.preventDefault();
        loadZoneInner.classList.add("drag-over");
    });
    loadZoneInner.addEventListener("dragleave", () => loadZoneInner.classList.remove("drag-over"));
    loadZoneInner.addEventListener("drop", (e) => {
        e.preventDefault();
        loadZoneInner.classList.remove("drag-over");
        const file = e.dataTransfer.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = (ev) => {
            try { boot(JSON.parse(ev.target.result)); } catch (err) { alert("JSON 解析失败"); }
        };
        reader.readAsText(file);
    });

    // Also try auto-loading digest.json
    (async () => {
        try {
            const resp = await fetch("digest.json");
            if (resp.ok) boot(await resp.json());
        } catch { /* ignore */ }
    })();

    /* ---------- Boot ---------- */
    function boot(data) {
        digestData = data;
        loadZone.classList.add("hidden");
        schemaVerEl.textContent = data.schema_version || "?";
        renderStats(data.stats, data.generated_at);
        renderTags(data.tag_index || {});
        renderTopStories(data.top_stories || []);
        renderSections(data.sections || []);
        renderDuplicates(data.duplicates || []);
        statsBar.classList.remove("hidden");
        tagBar.classList.remove("hidden");
        topStoriesSec.classList.remove("hidden");
        sectionsEl.classList.remove("hidden");
        if ((data.duplicates || []).length > 0) dupSection.classList.remove("hidden");
    }

    /* ---------- Stats ---------- */
    function renderStats(stats, date) {
        $("#stat-in").textContent = stats.items_in;
        $("#stat-kept").textContent = stats.items_kept;
        $("#stat-top").textContent = stats.top_stories_count;
        $("#stat-dup").textContent = stats.duplicates_count;
        $("#stat-date").textContent = date || "unknown";
    }

    /* ---------- Tags ---------- */
    function renderTags(tagIndex) {
        // "all" chip is already in HTML
        const tags = Object.keys(tagIndex).sort();
        tags.forEach((tag) => {
            const btn = document.createElement("button");
            btn.className = "tag-chip";
            btn.dataset.tag = tag;
            btn.textContent = tag;
            btn.addEventListener("click", () => setActiveTag(tag));
            tagBarInner.appendChild(btn);
        });
        // wire up the "all" button
        $(".tag-chip[data-tag='all']").addEventListener("click", () => setActiveTag("all"));
    }

    function setActiveTag(tag) {
        activeTag = tag;
        $$(".tag-chip").forEach((btn) => {
            btn.classList.toggle("active", btn.dataset.tag === tag);
        });
        filterByTag(tag);
    }

    function filterByTag(tag) {
        if (!digestData) return;
        const tagIndex = digestData.tag_index || {};
        const allowedIds = tag === "all" ? null : new Set(tagIndex[tag] || []);

        // Filter top stories
        $$(".story-card").forEach((card) => {
            const id = card.dataset.id;
            card.style.display = (!allowedIds || allowedIds.has(id)) ? "" : "none";
        });

        // Filter section items
        $$(".section-item").forEach((el) => {
            const id = el.dataset.refId;
            el.style.display = (!allowedIds || allowedIds.has(id)) ? "" : "none";
        });
    }

    /* ---------- Top Stories ---------- */
    function renderTopStories(stories) {
        topGrid.innerHTML = "";
        stories.forEach((s, i) => {
            const card = document.createElement("article");
            card.className = "story-card";
            card.dataset.id = s.id;
            card.style.animationDelay = `${i * 0.05}s`;

            card.innerHTML = `
        <div class="card-header">
          <span class="card-section-badge" style="${sectionBadgeStyle(s.section)}">${esc(s.section)}</span>
          <div class="card-meta">
            <span>${esc(s.source)}</span>
            <span class="dot">·</span>
            <span>${esc(s.date)}</span>
          </div>
        </div>
        <div class="card-title"><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a></div>
        <div class="card-subtitle">${esc(s.subtitle)}</div>
        <div class="card-one-liner">${esc(s.one_liner)}</div>
        <ul class="card-bullets">
          ${s.bullets.map((b) => `<li>${esc(b)}</li>`).join("")}
        </ul>
        <div class="card-why">${esc(s.why_it_matters)}</div>
        <div class="card-actions">
          ${s.action_items.map((a) => `<span class="action-chip">${esc(a)}</span>`).join("")}
        </div>
        <div class="card-footer">
          <div class="card-scores">
            ${scoreBadge("重要", s.scores.importance)}
            ${scoreBadge("可信", s.scores.credibility)}
            ${scoreBadge("新鲜", s.scores.freshness)}
          </div>
          <div class="card-read-time">📖 ${s.read_time_min} min</div>
        </div>
        <div class="card-tags">
          ${s.tags.map((t) => `<span class="card-tag" data-tag="${esc(t)}">${esc(t)}</span>`).join("")}
        </div>
        ${s.notes ? `<div style="font-size:0.7rem;color:var(--text-3);font-style:italic;">📝 ${esc(s.notes)}</div>` : ""}
      `;

            // Click tag to filter
            card.querySelectorAll(".card-tag").forEach((tagEl) => {
                tagEl.addEventListener("click", () => setActiveTag(tagEl.dataset.tag));
            });

            topGrid.appendChild(card);
        });
    }

    /* ---------- Sections ---------- */
    function renderSections(sections) {
        sectionsEl.innerHTML = "";
        sections.forEach((sec, idx) => {
            const group = document.createElement("div");
            group.className = "section-group open";
            group.style.animationDelay = `${idx * 0.05}s`;

            const icon = sectionIcon(sec.name);

            group.innerHTML = `
        <div class="section-group-header">
          <span style="font-size:1.2rem;">${icon}</span>
          <h3>${esc(sec.name)}</h3>
          <span class="count-badge">${sec.items.length}</span>
          <svg class="chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
        </div>
        <div class="section-items">
          ${sec.items.map((it) => sectionItemHTML(it)).join("")}
        </div>
      `;

            // Set initial max-height for animation
            const itemsEl = group.querySelector(".section-items");
            requestAnimationFrame(() => {
                itemsEl.style.maxHeight = itemsEl.scrollHeight + "px";
            });

            // Toggle collapse
            group.querySelector(".section-group-header").addEventListener("click", () => {
                const isOpen = group.classList.contains("open");
                if (isOpen) {
                    // Collapse: set explicit maxHeight first, then animate to 0
                    itemsEl.style.maxHeight = itemsEl.scrollHeight + "px";
                    requestAnimationFrame(() => {
                        itemsEl.style.maxHeight = "0";
                    });
                    group.classList.remove("open");
                } else {
                    // Expand
                    group.classList.add("open");
                    itemsEl.style.maxHeight = itemsEl.scrollHeight + "px";
                    // After transition, allow auto height for dynamic content
                    itemsEl.addEventListener("transitionend", function handler() {
                        if (group.classList.contains("open")) {
                            itemsEl.style.maxHeight = "none";
                        }
                        itemsEl.removeEventListener("transitionend", handler);
                    });
                }
            });

            sectionsEl.appendChild(group);
        });
    }

    function sectionItemHTML(it) {
        return `
      <div class="section-item" data-ref-id="${esc(it.ref_id)}">
        <div class="section-item-left">
          <div class="section-item-title"><a href="${esc(it.url)}" target="_blank" rel="noopener">${esc(it.title)}</a></div>
          <div class="section-item-oneliner">${esc(it.one_liner)}</div>
          <div class="section-item-meta">${esc(it.source)} · ${esc(it.date)}</div>
        </div>
        <div class="section-item-right">
          ${scoreBadge("", it.scores.importance)}
        </div>
      </div>
    `;
    }

    /* ---------- Duplicates ---------- */
    function renderDuplicates(dups) {
        if (!dups.length) return;
        dupContent.innerHTML = dups.map((d) => `
      <div class="dup-item">
        <span class="dup-title">${esc(d.title)}</span>
        <span class="dup-reason">原因: ${esc(d.reason)}</span>
        <span class="dup-merged-into">→ 合并至: ${esc(d.merged_into)}</span>
      </div>
    `).join("");

        dupToggle.addEventListener("click", () => {
            dupToggle.classList.toggle("open");
            dupContent.classList.toggle("hidden");
        });
    }

    /* ---------- Compact search card ---------- */
    function buildCompactCard(s) {
        const el = document.createElement("div");
        el.className = "search-hit";
        el.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <div>
          <div style="font-weight:600;font-size:0.88rem;"><a href="${esc(s.url)}" target="_blank" style="color:var(--text-0);text-decoration:none;">${esc(s.title)}</a></div>
          <div style="font-size:0.78rem;color:var(--text-2);margin-top:0.15rem;">${esc(s.one_liner)}</div>
          <div style="font-size:0.68rem;color:var(--text-3);margin-top:0.2rem;">${esc(s.source)} · ${esc(s.date)}</div>
        </div>
        <div>${scoreBadge("", s.scores.importance)}</div>
      </div>
    `;
        return el;
    }

    /* ---------- Utilities ---------- */
    function esc(str) {
        if (!str) return "";
        const el = document.createElement("span");
        el.textContent = str;
        return el.innerHTML;
    }

    function scoreColor(val) {
        const colors = { 5: "var(--score-5)", 4: "var(--score-4)", 3: "var(--score-3)", 2: "var(--score-2)", 1: "var(--score-1)" };
        return colors[val] || "var(--text-2)";
    }

    function scoreBadge(label, val) {
        const color = scoreColor(val);
        return `<span class="score-badge" style="background:${color}22;color:${color};">
      ${label ? `<span class="score-label">${label}</span>` : ""}${val}
    </span>`;
    }

    function sectionBadgeStyle(section) {
        const hueMap = {
            Models: "var(--hue-models)", Agents: "var(--hue-agents)",
            Multimodal: "var(--hue-multimodal)", Systems: "var(--hue-systems)",
            Safety: "var(--hue-safety)", Evaluation: "var(--hue-evaluation)",
            Product: "var(--hue-product)", OpenSource: "var(--hue-opensource)",
            Policy: "var(--hue-policy)", Industry: "var(--hue-industry)",
            Research: "var(--hue-research)", Hardware: "var(--hue-hardware)",
            Other: "var(--hue-other)",
        };
        const hue = hueMap[section] || "var(--hue-other)";
        return `background:hsl(${hue},60%,50%,0.15);color:hsl(${hue},70%,65%);`;
    }

    function sectionIcon(name) {
        const icons = {
            Models: "🧠", Agents: "🤖", Multimodal: "🎨",
            Systems: "⚙️", Safety: "🛡️", Evaluation: "📊",
            Product: "🚀", OpenSource: "🌐", Policy: "📜",
            Industry: "💼", Research: "🔬", Hardware: "🖥️",
            Other: "📌",
        };
        return icons[name] || "📌";
    }
})();
