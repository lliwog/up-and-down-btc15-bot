const STRATEGY_LABELS = {
  early_entry: "Strategy 1 — Early Entry",
  mid_game: "Strategy 2 — Mid Game",
  late_scalp: "Strategy 3 — Late Scalp",
};

function formatPnl(cents) {
  const dollars = cents / 100;
  const sign = dollars >= 0 ? "+" : "";
  return sign + "$" + dollars.toFixed(2);
}

function pnlClass(cents) {
  if (cents > 0) return "pnl-positive";
  if (cents < 0) return "pnl-negative";
  return "pnl-zero";
}

function renderOrder(order) {
  const li = document.createElement("li");
  li.className = "order-" + order.status;
  const fill = order.fill_price != null ? ` → filled@${order.fill_price}¢` : "";
  li.textContent = `${order.order_type} ${order.side} ${order.size}x @ ${order.limit_price}¢ [${order.status}]${fill}`;
  return li;
}

function renderStrategy(strat) {
  const card = document.createElement("div");
  card.className = "strategy-card";

  const header = document.createElement("div");
  header.className = "strat-header";
  const name = document.createElement("span");
  name.className = "strat-name";
  name.textContent = STRATEGY_LABELS[strat.name] || strat.name;
  const badge = document.createElement("span");
  badge.className = "phase-badge phase-" + strat.phase;
  badge.textContent = strat.phase;
  header.appendChild(name);
  header.appendChild(badge);
  card.appendChild(header);

  if (strat.orders.length > 0) {
    const ul = document.createElement("ul");
    ul.className = "order-list";
    strat.orders.forEach(o => ul.appendChild(renderOrder(o)));
    card.appendChild(ul);
  }

  if (strat.outcome) {
    const out = document.createElement("div");
    out.className = "outcome outcome-" + strat.outcome;
    out.textContent = strat.outcome + " " + formatPnl(strat.pnl_cents);
    card.appendChild(out);
  } else if (strat.phase !== "PENDING") {
    const pnl = document.createElement("div");
    pnl.className = "outcome " + pnlClass(strat.pnl_cents);
    pnl.textContent = formatPnl(strat.pnl_cents);
    card.appendChild(pnl);
  }

  return card;
}

function update(state) {
  document.getElementById("mode-badge").textContent = state.mode;
  document.getElementById("market-slug").textContent = state.market_slug || "—";
  if (state.time_left_min > 0) {
    const totalSec = Math.round(state.time_left_min * 60);
    const mins = Math.floor(totalSec / 60);
    const secs = totalSec % 60;
    document.getElementById("time-left").textContent = mins + ":" + secs.toString().padStart(2, "0");
  } else {
    document.getElementById("time-left").textContent = "—";
  }
  document.getElementById("signal").textContent = state.signal || "—";
  document.getElementById("recommendation").textContent = state.recommendation || "—";
  const priceEl = document.getElementById("current-price");
  priceEl.classList.remove("price-above", "price-below");
  if (state.current_price) {
    const priceText = "$" + state.current_price.toLocaleString(undefined, {maximumFractionDigits: 0});
    if (state.price_to_beat) {
      const diff = state.current_price - state.price_to_beat;
      const absDiff = Math.abs(diff).toFixed(2);
      if (diff > 0) {
        priceEl.classList.add("price-above");
        priceEl.innerHTML = priceText + ' <span class="price-diff">(+$' + absDiff + ")</span>";
      } else if (diff < 0) {
        priceEl.classList.add("price-below");
        priceEl.innerHTML = priceText + ' <span class="price-diff">(-$' + absDiff + ")</span>";
      } else {
        priceEl.textContent = priceText;
      }
    } else {
      priceEl.textContent = priceText;
    }
  } else {
    priceEl.textContent = "—";
  }
  document.getElementById("price-to-beat").textContent = state.price_to_beat
    ? "$" + state.price_to_beat.toLocaleString(undefined, {minimumFractionDigits: 2})
    : "—";
  if (state.adjusted_up || state.adjusted_down) {
    const up = (state.adjusted_up * 100).toFixed(0);
    const dn = (state.adjusted_down * 100).toFixed(0);
    document.getElementById("ta-predict").innerHTML =
      '<span class="price-above">LONG ' + up + '%</span> / <span class="price-below">SHORT ' + dn + '%</span>';
  } else {
    document.getElementById("ta-predict").textContent = "—";
  }
  document.getElementById("market-up").textContent = state.market_up + "¢";
  document.getElementById("market-down").textContent = state.market_down + "¢";

  const pnlEl = document.getElementById("global-pnl");
  pnlEl.textContent = formatPnl(state.global_pnl_cents);
  pnlEl.className = "pnl-value " + pnlClass(state.global_pnl_cents);

  const cardsEl = document.getElementById("strategy-cards");
  cardsEl.innerHTML = "";
  (state.strategies || []).forEach(s => cardsEl.appendChild(renderStrategy(s)));

  const errPanel = document.getElementById("error-panel");
  const errMsg = document.getElementById("error-message");
  if (state.error) {
    errPanel.classList.remove("hidden");
    errMsg.textContent = state.error;
  } else {
    errPanel.classList.add("hidden");
    errMsg.textContent = "";
  }
}

function connect() {
  const statusEl = document.getElementById("connection-status");
  const es = new EventSource("/api/stream");

  es.onopen = () => {
    statusEl.textContent = "Connected";
    statusEl.className = "badge badge-connected";
  };

  es.onmessage = (event) => {
    try {
      const state = JSON.parse(event.data);
      update(state);
    } catch (e) {
      console.error("Parse error:", e);
    }
  };

  es.onerror = () => {
    statusEl.textContent = "Disconnected";
    statusEl.className = "badge badge-disconnected";
    es.close();
    setTimeout(connect, 3000);
  };
}

connect();
