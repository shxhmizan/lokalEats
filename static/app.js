const CUISINES = ["malay", "chinese", "tomyam", "seafood", "kopitiam", "cafe",
  "western", "indian", "burger", "bakery", "cendol"];
const TAGS = ["breakfast", "rice", "noodle", "soup", "seafood", "western",
  "dessert", "drink", "dinner", "lunch", "grilled", "fish", "burger",
  "salad", "healthy", "pastry", "snack", "side"];

const CUISINE_EMOJI = {
  malay: "🍚", chinese: "🥢", tomyam: "🌶️", seafood: "🦐", kopitiam: "☕",
  cafe: "🍰", western: "🍝", indian: "🍛", burger: "🍔", bakery: "🥐", cendol: "🍧",
};

const WIZARD_TOTAL_STEPS = 2;
const DEFAULT_SPICE_PREF = 1;
const TOTAL_DISTRICTS = 10;

const state = {
  userId: null,
  userName: "",
  wizardStep: 1,
  selectedCuisines: new Set(),
  selectedTags: new Set(),
  recDishes: [],
  searchDishes: [],
  starredIds: new Set(),
  starredDishesMap: new Map(),
  maps: {
    rec: { instance: null, markers: [] },
    search: { instance: null, markers: [] },
  },
};

// ---------- Toasts ----------

function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  const el = document.createElement("div");
  el.className = `toast ${type === "error" ? "error" : ""}`.trim();
  el.textContent = message;
  container.appendChild(el);
  setTimeout(() => {
    el.classList.add("leaving");
    setTimeout(() => el.remove(), 300);
  }, 2400);
}

// ---------- Landing ----------

function animateCounter(el, target, duration = 1400) {
  const start = performance.now();
  function tick(now) {
    const progress = Math.min((now - start) / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    el.textContent = Math.floor(eased * target).toLocaleString();
    if (progress < 1) requestAnimationFrame(tick);
    else el.textContent = target.toLocaleString();
  }
  requestAnimationFrame(tick);
}

document.addEventListener("DOMContentLoaded", () => {
  setTimeout(() => {
    document.querySelectorAll(".stat-num").forEach(el => {
      animateCounter(el, parseInt(el.dataset.target, 10));
    });
  }, 550);
});

function goToOnboarding() {
  const landing = document.getElementById("view-landing");
  landing.classList.add("leaving");
  setTimeout(() => {
    landing.classList.remove("active");
    landing.classList.remove("leaving");
    document.getElementById("view-onboarding").classList.add("active");
  }, 450);
}

function backToLanding() {
  document.getElementById("view-onboarding").classList.remove("active");
  document.getElementById("view-landing").classList.add("active");
}

document.getElementById("landing-cta").addEventListener("click", goToOnboarding);
document.getElementById("wizard-close").addEventListener("click", backToLanding);

// ---------- Onboarding wizard ----------

function buildChipSelect(containerId, options, selectedSet) {
  const container = document.getElementById(containerId);
  options.forEach(opt => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip";
    chip.textContent = opt;
    chip.addEventListener("click", () => {
      if (selectedSet.has(opt)) {
        selectedSet.delete(opt);
        chip.classList.remove("selected");
      } else {
        selectedSet.add(opt);
        chip.classList.add("selected");
      }
    });
    container.appendChild(chip);
  });
}

buildChipSelect("ob-cuisines", CUISINES, state.selectedCuisines);
buildChipSelect("ob-tags", TAGS, state.selectedTags);

const budgetSlider = document.getElementById("ob-budget");
budgetSlider.addEventListener("input", () => {
  document.getElementById("ob-budget-value").textContent = `RM ${budgetSlider.value}`;
});

function renderWizardStep(step) {
  document.querySelectorAll(".wizard-step").forEach(el => {
    el.classList.toggle("active", parseInt(el.dataset.step, 10) === step);
  });
  document.getElementById("wizard-progress-fill").style.width = `${(step / WIZARD_TOTAL_STEPS) * 100}%`;
  document.getElementById("wizard-back").classList.toggle("hidden", step === 1);
  document.getElementById("wizard-next").classList.toggle("hidden", step === WIZARD_TOTAL_STEPS);
  document.getElementById("wizard-finish").classList.toggle("hidden", step !== WIZARD_TOTAL_STEPS);
  document.getElementById("ob-error").textContent = "";
}

document.getElementById("wizard-next").addEventListener("click", () => {
  if (state.wizardStep === 1) {
    const name = document.getElementById("ob-name").value.trim();
    if (!name) {
      document.getElementById("ob-error").textContent = "Please enter your name.";
      return;
    }
  }
  state.wizardStep = Math.min(WIZARD_TOTAL_STEPS, state.wizardStep + 1);
  renderWizardStep(state.wizardStep);
});

document.getElementById("wizard-back").addEventListener("click", () => {
  state.wizardStep = Math.max(1, state.wizardStep - 1);
  renderWizardStep(state.wizardStep);
});

document.getElementById("wizard-finish").addEventListener("click", async () => {
  const name = document.getElementById("ob-name").value.trim();
  const errorEl = document.getElementById("ob-error");
  errorEl.textContent = "";
  if (!name) {
    errorEl.textContent = "Please enter your name.";
    state.wizardStep = 1;
    renderWizardStep(1);
    return;
  }

  const finishBtn = document.getElementById("wizard-finish");
  finishBtn.disabled = true;
  finishBtn.textContent = "Finding your dishes…";

  const payload = {
    name,
    budget_max: parseFloat(budgetSlider.value),
    spice_pref: DEFAULT_SPICE_PREF,
    halal_only: false,
    cuisines: Array.from(state.selectedCuisines),
    tags_pref: Array.from(state.selectedTags),
  };

  try {
    const res = await fetch("/api/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error("Failed to create user");
    const user = await res.json();
    state.userId = user.user_id;
    state.userName = user.name;

    document.getElementById("view-onboarding").classList.remove("active");
    document.getElementById("user-greeting").textContent = `Hi, ${user.name} 👋`;
    document.getElementById("app-shell").classList.remove("hidden");
    recBudgetSlider.value = user.budget_max;
    document.getElementById("rec-budget-value").textContent = `RM ${user.budget_max}`;
    showView("recommend");
    await loadDistricts();
    await loadRecommendations();
  } catch (err) {
    errorEl.textContent = "Something went wrong. Please try again.";
    console.error(err);
  } finally {
    finishBtn.disabled = false;
    finishBtn.textContent = "Find my dishes ✨";
  }
});

// ---------- Main nav / view switching ----------

function showView(viewName) {
  document.querySelectorAll("#app-shell .view").forEach(v => v.classList.remove("active"));
  document.getElementById(`view-${viewName}`).classList.add("active");
  document.querySelectorAll(".nav-btn").forEach(b => {
    b.classList.toggle("active", b.dataset.view === viewName);
  });
  if (viewName === "starred") loadStarred();
}

document.querySelectorAll(".nav-btn").forEach(btn => {
  btn.addEventListener("click", () => showView(btn.dataset.view));
});

// ---------- Dish card rendering ----------

const cardTemplate = document.getElementById("dish-card-template");
const skeletonTemplate = document.getElementById("skeleton-card-template");

function spiceEmoji(level) {
  return level > 0 ? "🌶️".repeat(level) : "😌";
}

function renderCard(dish, index) {
  const node = cardTemplate.content.cloneNode(true);
  const card = node.querySelector(".dish-card");
  card.dataset.dishId = dish.dish_id;
  card.style.animationDelay = `${Math.min(index, 10) * 40}ms`;

  const imageEl = node.querySelector(".dish-image");
  imageEl.classList.add(`cuisine-${dish.cuisine_profile}`);
  node.querySelector(".dish-emoji").textContent = CUISINE_EMOJI[dish.cuisine_profile] || "🍽️";

  node.querySelector(".dish-name").textContent = dish.dish_name;
  node.querySelector(".price-badge").textContent = `RM ${dish.price_rm.toFixed(2)}`;
  node.querySelector(".restaurant-name").textContent = dish.restaurant_name;
  node.querySelector(".city-district").textContent = `${dish.city || ""}, ${dish.district}`;
  node.querySelector(".spice-display").textContent = spiceEmoji(dish.spice_level);

  const halalBadge = node.querySelector(".halal-badge");
  halalBadge.textContent = dish.halal;
  halalBadge.classList.add(dish.halal);

  const ratingEl = node.querySelector(".rating-display");
  ratingEl.textContent = dish.restaurant_rating ? `★ ${dish.restaurant_rating.toFixed(1)}` : "★ –";

  const explainEl = node.querySelector(".explain-text");

  const starBtn = node.querySelector(".btn-star");
  if (state.starredIds.has(dish.dish_id)) {
    starBtn.classList.add("starred");
    starBtn.textContent = "⭐ Starred";
  }
  starBtn.addEventListener("click", () => toggleStar(dish, starBtn, card));

  node.querySelector(".btn-explain").addEventListener("click", async (e) => {
    e.target.disabled = true;
    e.target.textContent = "…";
    try {
      const res = await fetch("/api/explain", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: state.userId, dish_id: dish.dish_id }),
      });
      const data = await res.json();
      explainEl.classList.remove("hidden");
      if (data.error === "llm_disabled") {
        explainEl.textContent = "✨ Explanations unavailable (no LLM key configured).";
      } else if (data.error) {
        explainEl.textContent = "Couldn't generate an explanation right now.";
      } else {
        explainEl.textContent = data.text;
      }
    } catch (err) {
      explainEl.classList.remove("hidden");
      explainEl.textContent = "Couldn't generate an explanation right now.";
    } finally {
      e.target.disabled = false;
      e.target.textContent = "✨ Why?";
    }
  });

  node.querySelector(".btn-similar").addEventListener("click", async () => {
    try {
      const res = await fetch(`/api/dishes/${encodeURIComponent(dish.dish_id)}/similar?k=5`);
      const dishes = await res.json();
      renderGrid(document.getElementById("rec-grid"), dishes);
      state.recDishes = dishes;
      document.getElementById("rec-status").textContent = `Dishes similar to "${dish.dish_name}"`;
      showView("recommend");
      setViewMode("rec", "list");
    } catch (err) {
      console.error(err);
      showToast("Couldn't load similar dishes.", "error");
    }
  });

  return node;
}

async function toggleStar(dish, starBtn, card) {
  const nowStarred = !state.starredIds.has(dish.dish_id);
  const badgesBefore = computeBadges();

  if (nowStarred) {
    state.starredIds.add(dish.dish_id);
    state.starredDishesMap.set(dish.dish_id, dish);
    starBtn.classList.add("starred");
    starBtn.textContent = "⭐ Starred";
  } else {
    state.starredIds.delete(dish.dish_id);
    state.starredDishesMap.delete(dish.dish_id);
    starBtn.classList.remove("starred");
    starBtn.textContent = "⭐ Star";
  }

  const badgesAfter = computeBadges();
  renderAchievements(badgesAfter);

  try {
    await fetch("/api/rate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: state.userId, dish_id: dish.dish_id, liked: nowStarred }),
    });
    showToast(nowStarred ? `Starred ${dish.dish_name} ⭐` : `Removed from starred`, "info");
    if (nowStarred) announceNewBadges(badgesBefore, badgesAfter);
    if (!nowStarred && card.closest("#starred-grid")) {
      card.style.transition = "opacity 0.25s ease";
      card.style.opacity = "0";
      setTimeout(() => card.remove(), 250);
    }
  } catch (err) {
    console.error(err);
    showToast("Couldn't save your rating.", "error");
  }
}

// ---------- Achievements ----------

function computeBadges() {
  const dishes = Array.from(state.starredDishesMap.values());
  return {
    cuisineCount: new Set(dishes.map(d => d.cuisine_profile)).size,
    districtCount: new Set(dishes.map(d => d.district)).size,
    firstStar: dishes.length > 0,
    braveEater: dishes.some(d => d.spice_level === 3),
  };
}

function renderAchievements(badges) {
  badges = badges || computeBadges();

  const cuisinePct = Math.min(100, (badges.cuisineCount / CUISINES.length) * 100);
  document.getElementById("badge-cuisine-fill").style.width = `${cuisinePct}%`;
  document.getElementById("badge-cuisine-count").textContent = `${badges.cuisineCount}/${CUISINES.length}`;

  const districtPct = Math.min(100, (badges.districtCount / TOTAL_DISTRICTS) * 100);
  document.getElementById("badge-district-fill").style.width = `${districtPct}%`;
  document.getElementById("badge-district-count").textContent = `${badges.districtCount}/${TOTAL_DISTRICTS}`;

  const firstStarEl = document.getElementById("badge-first-star");
  firstStarEl.textContent = badges.firstStar ? "✓ Unlocked" : "Locked";
  firstStarEl.classList.toggle("unlocked", badges.firstStar);

  const braveEaterEl = document.getElementById("badge-brave-eater");
  braveEaterEl.textContent = badges.braveEater ? "✓ Unlocked" : "Locked";
  braveEaterEl.classList.toggle("unlocked", badges.braveEater);
}

function announceNewBadges(before, after) {
  const messages = [];
  if (!before.firstStar && after.firstStar) messages.push("🎉 Achievement unlocked: First Star!");
  if (!before.braveEater && after.braveEater) messages.push("🌶️ Achievement unlocked: Brave Eater!");
  if (before.cuisineCount < CUISINES.length && after.cuisineCount === CUISINES.length) {
    messages.push("🍜 Achievement unlocked: Cuisine Explorer!");
  }
  if (before.districtCount < TOTAL_DISTRICTS && after.districtCount === TOTAL_DISTRICTS) {
    messages.push("📍 Achievement unlocked: District Hopper!");
  }
  messages.forEach((msg, i) => {
    setTimeout(() => showToast(msg, "info"), 700 + i * 500);
  });
}

function renderGrid(container, dishes) {
  container.innerHTML = "";
  if (dishes.length === 0) {
    container.innerHTML = '<p class="status-text">No dishes match — try widening your filters.</p>';
    return;
  }
  dishes.forEach((dish, i) => container.appendChild(renderCard(dish, i)));
}

function renderSkeletons(container, count = 6) {
  container.innerHTML = "";
  for (let i = 0; i < count; i++) {
    container.appendChild(skeletonTemplate.content.cloneNode(true));
  }
}

// ---------- Recommendations view ----------

async function loadDistricts() {
  try {
    const res = await fetch("/api/districts");
    const districts = await res.json();
    const select = document.getElementById("rec-district");
    select.innerHTML = '<option value="">All districts</option>';
    districts.forEach(d => {
      const opt = document.createElement("option");
      opt.value = d.district;
      opt.textContent = `${d.district} (${d.count})`;
      select.appendChild(opt);
    });
  } catch (err) {
    console.error(err);
  }
}

async function loadRecommendations(extraParams = {}) {
  const statusEl = document.getElementById("rec-status");
  const grid = document.getElementById("rec-grid");
  statusEl.textContent = "Loading…";
  renderSkeletons(grid);
  const params = new URLSearchParams({ user_id: state.userId, k: 12, ...extraParams });
  const district = document.getElementById("rec-district").value;
  if (district) params.set("district", district);
  const maxPrice = document.getElementById("rec-budget").value;
  if (maxPrice) params.set("max_price", maxPrice);
  try {
    const res = await fetch(`/api/recommend?${params.toString()}`);
    const dishes = await res.json();
    state.recDishes = dishes;
    renderGrid(grid, dishes);
    statusEl.textContent = `${dishes.length} dishes found`;
    if (isMapMode("rec")) refreshMap("rec");
  } catch (err) {
    statusEl.textContent = "Failed to load recommendations.";
    grid.innerHTML = "";
    console.error(err);
  }
}

document.getElementById("rec-district").addEventListener("change", () => loadRecommendations());

const recBudgetSlider = document.getElementById("rec-budget");
let recBudgetDebounce = null;
recBudgetSlider.addEventListener("input", () => {
  document.getElementById("rec-budget-value").textContent = `RM ${recBudgetSlider.value}`;
  clearTimeout(recBudgetDebounce);
  recBudgetDebounce = setTimeout(() => loadRecommendations(), 350);
});

document.getElementById("rec-nearme").addEventListener("click", () => {
  const statusEl = document.getElementById("rec-status");
  if (!navigator.geolocation) {
    showToast("Geolocation not supported by this browser.", "error");
    return;
  }
  statusEl.textContent = "Getting your location…";
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      document.getElementById("rec-district").value = "";
      loadRecommendations({
        lat: pos.coords.latitude,
        lng: pos.coords.longitude,
        max_km: 15,
      });
    },
    (err) => {
      statusEl.textContent = "";
      showToast("Couldn't get your location.", "error");
      console.error(err);
    }
  );
});

// ---------- Search (NLQ) view ----------

document.querySelectorAll(".example-chip").forEach(chip => {
  chip.addEventListener("click", () => {
    document.getElementById("search-input").value = chip.textContent;
    runSearch();
  });
});

async function runSearch() {
  const query = document.getElementById("search-input").value.trim();
  const statusEl = document.getElementById("search-status");
  const filtersEl = document.getElementById("search-filters");
  const grid = document.getElementById("search-grid");
  if (!query) return;
  statusEl.textContent = "Searching…";
  filtersEl.innerHTML = "";
  renderSkeletons(grid);
  try {
    const res = await fetch("/api/nlq", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: state.userId, query }),
    });
    const data = await res.json();
    if (data.error === "llm_disabled") {
      statusEl.textContent = "Natural-language search unavailable (no LLM key configured).";
      state.searchDishes = [];
      renderGrid(grid, []);
      if (isMapMode("search")) refreshMap("search");
      return;
    }
    if (data.error) {
      statusEl.textContent = "Couldn't understand that query — try rephrasing.";
      state.searchDishes = [];
      renderGrid(grid, []);
      if (isMapMode("search")) refreshMap("search");
      return;
    }
    const filters = data.parsed_filters || {};
    Object.entries(filters).forEach(([key, value]) => {
      if (value === null || value === undefined) return;
      if (Array.isArray(value) && value.length === 0) return;
      if (value === false) return;
      const chip = document.createElement("span");
      chip.className = "chip selected removable";
      chip.textContent = `${key}: ${Array.isArray(value) ? value.join(", ") : value}`;
      chip.addEventListener("click", () => chip.remove());
      filtersEl.appendChild(chip);
    });
    state.searchDishes = data.results || [];
    renderGrid(grid, state.searchDishes);
    statusEl.textContent = `${state.searchDishes.length} dishes found`;
    if (isMapMode("search")) refreshMap("search");
  } catch (err) {
    statusEl.textContent = "Search failed. Please try again.";
    grid.innerHTML = "";
    console.error(err);
  }
}

document.getElementById("search-submit").addEventListener("click", runSearch);
document.getElementById("search-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") runSearch();
});

// ---------- Starred view ----------

async function loadStarred() {
  const grid = document.getElementById("starred-grid");
  renderSkeletons(grid, 3);
  try {
    const res = await fetch(`/api/starred?user_id=${state.userId}`);
    const dishes = await res.json();
    state.starredDishesMap = new Map(dishes.map(d => [d.dish_id, d]));
    state.starredIds = new Set(dishes.map(d => d.dish_id));
    renderAchievements();
    if (dishes.length === 0) {
      grid.innerHTML = '<p class="status-text">You haven\'t starred anything yet — tap ⭐ on dishes you love.</p>';
      return;
    }
    renderGrid(grid, dishes);
  } catch (err) {
    console.error(err);
    grid.innerHTML = '<p class="status-text">Couldn\'t load your starred dishes.</p>';
  }
}

// ---------- Embedded maps (recommend + search) ----------

const MAP_VIEWS = {
  rec: { containerId: "rec-map", gridId: "rec-grid", toggleId: "rec-view-toggle", dishesKey: "recDishes" },
  search: { containerId: "search-map", gridId: "search-grid", toggleId: "search-view-toggle", dishesKey: "searchDishes" },
};

function isMapMode(view) {
  const toggle = document.getElementById(MAP_VIEWS[view].toggleId);
  const mapBtn = toggle.querySelector('[data-mode="map"]');
  return mapBtn.classList.contains("active");
}

function setViewMode(view, mode) {
  const { containerId, gridId, toggleId } = MAP_VIEWS[view];
  const toggle = document.getElementById(toggleId);
  toggle.querySelectorAll(".toggle-btn").forEach(b => {
    b.classList.toggle("active", b.dataset.mode === mode);
  });
  document.getElementById(gridId).classList.toggle("hidden", mode !== "list");
  document.getElementById(containerId).classList.toggle("hidden", mode !== "map");
  if (mode === "map") refreshMap(view);
}

function setupViewToggle(view) {
  const { toggleId } = MAP_VIEWS[view];
  document.getElementById(toggleId).querySelectorAll(".toggle-btn").forEach(btn => {
    btn.addEventListener("click", () => setViewMode(view, btn.dataset.mode));
  });
}

setupViewToggle("rec");
setupViewToggle("search");

function refreshMap(view) {
  const { containerId, dishesKey } = MAP_VIEWS[view];
  const mapState = state.maps[view];

  if (!mapState.instance) {
    mapState.instance = L.map(containerId).setView([4.6, 101.0], 9);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap contributors",
    }).addTo(mapState.instance);
  }

  mapState.markers.forEach(m => mapState.instance.removeLayer(m));
  mapState.markers = [];

  const byRestaurant = new Map();
  state[dishesKey].forEach(dish => {
    const existing = byRestaurant.get(dish.place_id);
    if (!existing || (dish.score || 0) > (existing.score || 0)) {
      byRestaurant.set(dish.place_id, dish);
    }
  });

  byRestaurant.forEach(dish => {
    if (dish.latitude == null || dish.longitude == null) return;
    const marker = L.marker([dish.latitude, dish.longitude]).addTo(mapState.instance);
    marker.bindPopup(
      `<strong>${dish.restaurant_name}</strong><br/>` +
      `Top dish: ${dish.dish_name} (RM ${dish.price_rm.toFixed(2)})<br/>` +
      `<a href="${dish.gmaps_url}" target="_blank" rel="noopener">Open in Google Maps</a>`
    );
    mapState.markers.push(marker);
  });

  setTimeout(() => mapState.instance.invalidateSize(), 100);
}
