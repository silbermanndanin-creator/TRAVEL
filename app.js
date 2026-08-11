// Trip Bites — restaurant finder
// All logic runs client-side using the Google Maps JavaScript API (Places + Distance Matrix).

const STORAGE_KEY = "tripbites_gmaps_key";

const CHAIN_BLACKLIST = [
  "mcdonald", "burger king", "kfc", "starbucks", "subway", "pizza hut",
  "domino", "taco bell", "dunkin", "costa coffee", "greggs", "five guys",
  "nando", "wendy", "papa john", "wagamama express"
];

const WALK_LIMIT_SECONDS = 25 * 60; // 25 min walk cap
const DRIVE_LIMIT_SECONDS = 50 * 60; // 50 min drive cap, per user request
const WALK_SEARCH_RADIUS_M = 2200;
const CAR_SEARCH_RADIUS_M = 45000;
const MIN_RATING_STRICT = 4.3;
const MIN_REVIEWS_STRICT = 50;
const MIN_RATING_RELAXED = 4.0;
const MIN_REVIEWS_RELAXED = 20;
const MAX_RESULTS_SHOWN = 9;

let accommodation = null; // { name, address, location: google.maps.LatLng }
let map; // hidden map instance required by PlacesService

// ---------- Bootstrapping ----------

document.addEventListener("DOMContentLoaded", () => {
  const savedKey = localStorage.getItem(STORAGE_KEY);
  document.getElementById("save-key-btn").addEventListener("click", onSaveKey);
  document.getElementById("change-key-btn").addEventListener("click", onChangeKey);
  document.getElementById("find-btn").addEventListener("click", onFindRestaurants);

  if (savedKey) {
    startApp(savedKey);
  } else {
    showScreen("setup-screen");
  }
});

function showScreen(id) {
  document.getElementById("setup-screen").hidden = id !== "setup-screen";
  document.getElementById("app-screen").hidden = id !== "app-screen";
}

function onSaveKey() {
  const input = document.getElementById("api-key-input");
  const key = input.value.trim();
  const errorEl = document.getElementById("setup-error");
  if (!key) {
    errorEl.textContent = "Please paste a valid API key.";
    errorEl.hidden = false;
    return;
  }
  errorEl.hidden = true;
  localStorage.setItem(STORAGE_KEY, key);
  startApp(key);
}

function onChangeKey() {
  localStorage.removeItem(STORAGE_KEY);
  document.getElementById("api-key-input").value = "";
  showScreen("setup-screen");
}

function startApp(key) {
  loadGoogleMaps(key)
    .then(() => {
      showScreen("app-screen");
      initApp();
    })
    .catch(() => {
      localStorage.removeItem(STORAGE_KEY);
      const errorEl = document.getElementById("setup-error");
      errorEl.textContent = "Couldn't load Google Maps with that key. Double-check it's correct and has Places, Maps JavaScript, and Distance Matrix APIs enabled.";
      errorEl.hidden = false;
      showScreen("setup-screen");
    });
}

function loadGoogleMaps(key) {
  return new Promise((resolve, reject) => {
    if (window.google && window.google.maps) {
      resolve();
      return;
    }
    window.__tripBitesMapsLoaded = () => resolve();
    const script = document.createElement("script");
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&libraries=places&callback=__tripBitesMapsLoaded`;
    script.async = true;
    script.onerror = () => reject(new Error("Failed to load Google Maps script"));
    document.head.appendChild(script);
  });
}

// ---------- App setup ----------

function initApp() {
  // PlacesService needs a map or a DOM node; we don't need to show it.
  const hiddenDiv = document.createElement("div");
  map = new google.maps.Map(hiddenDiv);

  const locationInput = document.getElementById("location-input");
  const autocomplete = new google.maps.places.Autocomplete(locationInput, {
    fields: ["name", "formatted_address", "geometry"],
  });

  autocomplete.addListener("place_changed", () => {
    const place = autocomplete.getPlace();
    if (!place.geometry) {
      accommodation = null;
      document.getElementById("location-hint").textContent =
        "Please choose a suggestion from the dropdown list.";
      return;
    }
    accommodation = {
      name: place.name,
      address: place.formatted_address,
      location: place.geometry.location,
    };
    document.getElementById("location-hint").textContent = `Set: ${place.formatted_address}`;
  });

  locationInput.addEventListener("input", () => {
    accommodation = null;
  });

  const today = new Date().toISOString().slice(0, 10);
  const startInput = document.getElementById("start-date");
  const endInput = document.getElementById("end-date");
  startInput.value = today;
  startInput.min = today;
  endInput.min = today;
  endInput.value = today;
  startInput.addEventListener("change", () => {
    endInput.min = startInput.value;
    if (endInput.value < startInput.value) endInput.value = startInput.value;
  });
}

// ---------- Search flow ----------

async function onFindRestaurants() {
  const errorEl = document.getElementById("search-error");
  errorEl.hidden = true;

  if (!accommodation) {
    errorEl.textContent = "Please select your accommodation from the location suggestions first.";
    errorEl.hidden = false;
    return;
  }

  const startDate = document.getElementById("start-date").value;
  const endDate = document.getElementById("end-date").value;
  const hasCar = document.getElementById("has-car").checked;

  if (!startDate || !endDate) {
    errorEl.textContent = "Please choose both an arrival and departure date.";
    errorEl.hidden = false;
    return;
  }

  setLoading(true);
  document.getElementById("results").innerHTML = "";
  document.getElementById("results-meta").hidden = true;
  document.getElementById("empty-state").hidden = true;

  try {
    const weekdays = collectWeekdays(startDate, endDate);
    const radius = hasCar ? CAR_SEARCH_RADIUS_M : WALK_SEARCH_RADIUS_M;

    const rawResults = await nearbySearchRestaurants(accommodation.location, radius);
    const filtered = filterAndScore(rawResults);

    if (filtered.length === 0) {
      showEmptyState();
      return;
    }

    const topCandidates = filtered.slice(0, 20);
    const detailsResults = await Promise.all(topCandidates.map((r) => getPlaceDetails(r.place_id)));
    const paired = topCandidates
      .map((cand, i) => ({ details: detailsResults[i], candidateScore: cand._score }))
      .filter((p) => p.details !== null);

    const withDistances = await attachDistances(paired, accommodation.location, hasCar);

    const finalList = withDistances
      .filter((r) => r.travel !== null)
      .filter((r) => isOpenDuringStay(r.details, weekdays))
      .sort((a, b) => b.score - a.score)
      .slice(0, MAX_RESULTS_SHOWN);

    if (finalList.length === 0) {
      showEmptyState();
      return;
    }

    renderResults(finalList, startDate, endDate, hasCar);
  } catch (err) {
    console.error(err);
    errorEl.textContent = "Something went wrong fetching restaurants. Please try again.";
    errorEl.hidden = false;
  } finally {
    setLoading(false);
  }
}

function setLoading(isLoading) {
  document.getElementById("loading").hidden = !isLoading;
  document.getElementById("find-btn").disabled = isLoading;
}

function showEmptyState() {
  document.getElementById("empty-state").hidden = false;
}

function collectWeekdays(startDate, endDate) {
  const weekdays = new Set();
  const start = new Date(startDate + "T00:00:00");
  const end = new Date(endDate + "T00:00:00");
  let cursor = new Date(start);
  let guard = 0;
  while (cursor <= end && guard < 60) {
    weekdays.add(cursor.getDay());
    cursor.setDate(cursor.getDate() + 1);
    guard++;
    if (weekdays.size === 7) break;
  }
  return weekdays;
}

// ---------- Google Places calls ----------

function nearbySearchRestaurants(location, radius) {
  return new Promise((resolve, reject) => {
    const service = new google.maps.places.PlacesService(map);
    let allResults = [];
    let pagesFetched = 0;

    service.nearbySearch(
      { location, radius, type: "restaurant" },
      handlePage
    );

    function handlePage(results, status, pagination) {
      if (status === google.maps.places.PlacesServiceStatus.ZERO_RESULTS) {
        resolve(allResults);
        return;
      }
      if (status !== google.maps.places.PlacesServiceStatus.OK || !results) {
        if (allResults.length > 0) {
          resolve(allResults);
        } else {
          reject(new Error("Places search failed: " + status));
        }
        return;
      }
      allResults = allResults.concat(results);
      pagesFetched++;
      if (pagination && pagination.hasNextPage && pagesFetched < 2) {
        setTimeout(() => pagination.nextPage(), 2000); // Google requires a short delay
      } else {
        resolve(allResults);
      }
    }
  });
}

function getPlaceDetails(placeId) {
  return new Promise((resolve, reject) => {
    const service = new google.maps.places.PlacesService(map);
    service.getDetails(
      {
        placeId,
        fields: [
          "name", "rating", "user_ratings_total", "price_level",
          "formatted_address", "geometry", "opening_hours", "website",
          "url", "types", "editorial_summary", "business_status",
        ],
      },
      (place, status) => {
        if (status === google.maps.places.PlacesServiceStatus.OK && place) {
          resolve(place);
        } else {
          resolve(null);
        }
      }
    );
  });
}

function filterAndScore(rawResults) {
  const deduped = new Map();
  for (const r of rawResults) {
    if (!r.place_id || deduped.has(r.place_id)) continue;
    if (r.business_status && r.business_status !== "OPERATIONAL") continue;
    const nameLower = (r.name || "").toLowerCase();
    if (CHAIN_BLACKLIST.some((chain) => nameLower.includes(chain))) continue;
    deduped.set(r.place_id, r);
  }
  let candidates = Array.from(deduped.values());

  let strict = candidates.filter(
    (r) => (r.rating || 0) >= MIN_RATING_STRICT && (r.user_ratings_total || 0) >= MIN_REVIEWS_STRICT
  );
  let pool = strict.length >= 5 ? strict : candidates.filter(
    (r) => (r.rating || 0) >= MIN_RATING_RELAXED && (r.user_ratings_total || 0) >= MIN_REVIEWS_RELAXED
  );
  if (pool.length === 0) pool = candidates;

  pool.forEach((r) => {
    let score = (r.rating || 0) * Math.log10((r.user_ratings_total || 0) + 1);
    if (r.price_level === 4) score *= 0.92; // slight nudge away from top-end fine dining toward "great standard"
    r._score = score;
  });

  return pool.sort((a, b) => b._score - a._score);
}

// ---------- Distances ----------

function attachDistances(pairedList, origin, hasCar) {
  const destinations = pairedList.map((p) => p.details.geometry.location);

  return new Promise((resolve, reject) => {
    if (destinations.length === 0) {
      resolve([]);
      return;
    }
    const service = new google.maps.DistanceMatrixService();
    service.getDistanceMatrix(
      {
        origins: [origin],
        destinations,
        travelMode: google.maps.TravelMode.WALKING,
        unitSystem: google.maps.UnitSystem.METRIC,
      },
      (walkResponse, walkStatus) => {
        if (walkStatus !== "OK") {
          reject(new Error("Distance Matrix (walking) failed: " + walkStatus));
          return;
        }
        if (!hasCar) {
          resolve(buildTravelResults(pairedList, walkResponse, null));
          return;
        }
        service.getDistanceMatrix(
          {
            origins: [origin],
            destinations,
            travelMode: google.maps.TravelMode.DRIVING,
            unitSystem: google.maps.UnitSystem.METRIC,
          },
          (driveResponse, driveStatus) => {
            if (driveStatus !== "OK") {
              resolve(buildTravelResults(pairedList, walkResponse, null));
              return;
            }
            resolve(buildTravelResults(pairedList, walkResponse, driveResponse));
          }
        );
      }
    );
  });
}

function buildTravelResults(pairedList, walkResponse, driveResponse) {
  const walkRow = walkResponse.rows[0].elements;
  const driveRow = driveResponse ? driveResponse.rows[0].elements : null;

  return pairedList.map(({ details, candidateScore }, i) => {
    const walkEl = walkRow[i];
    const driveEl = driveRow ? driveRow[i] : null;

    let travel = null;
    if (walkEl && walkEl.status === "OK" && walkEl.duration.value <= WALK_LIMIT_SECONDS) {
      travel = { mode: "walk", duration: walkEl.duration, distance: walkEl.distance };
    } else if (driveEl && driveEl.status === "OK" && driveEl.duration.value <= DRIVE_LIMIT_SECONDS) {
      travel = { mode: "drive", duration: driveEl.duration, distance: driveEl.distance };
    }

    return { details, travel, score: candidateScore || 0 };
  });
}

// ---------- Opening hours across the stay ----------

function isOpenDuringStay(details, weekdaySet) {
  const oh = details.opening_hours;
  if (!oh || !oh.periods || oh.periods.length === 0) return true; // unknown: don't exclude
  if (oh.periods.length === 1 && !oh.periods[0].close) return true; // open 24/7
  return oh.periods.some((p) => p.open && weekdaySet.has(p.open.day));
}

// ---------- Rendering ----------

function renderResults(list, startDate, endDate, hasCar) {
  const metaEl = document.getElementById("results-meta");
  metaEl.hidden = false;
  metaEl.textContent = `${list.length} great option${list.length === 1 ? "" : "s"} near ${accommodation.address}, for ${formatDateRange(startDate, endDate)}${hasCar ? " (walking + driving)" : " (walking distance)"}.`;

  const container = document.getElementById("results");
  container.innerHTML = "";

  list.forEach(({ details, travel }) => {
    container.appendChild(buildCard(details, travel));
  });
}

function formatDateRange(startDate, endDate) {
  const opts = { day: "numeric", month: "short" };
  const s = new Date(startDate + "T00:00:00").toLocaleDateString(undefined, opts);
  const e = new Date(endDate + "T00:00:00").toLocaleDateString(undefined, opts);
  return startDate === endDate ? s : `${s} – ${e}`;
}

function buildCard(details, travel) {
  const card = document.createElement("article");
  card.className = "restaurant-card";

  const top = document.createElement("div");
  top.className = "restaurant-top";

  const nameBlock = document.createElement("div");
  const name = document.createElement("p");
  name.className = "restaurant-name";
  name.textContent = details.name;
  const sub = document.createElement("p");
  sub.className = "restaurant-sub";
  sub.textContent = details.formatted_address || "";
  nameBlock.appendChild(name);
  nameBlock.appendChild(sub);

  const travelBadge = document.createElement("span");
  if (travel) {
    travelBadge.className = "badge";
    const icon = travel.mode === "walk" ? "🚶" : "🚗";
    travelBadge.textContent = `${icon} ${travel.duration.text} (${travel.distance.text})`;
  } else {
    travelBadge.className = "badge badge-warn";
    travelBadge.textContent = "Distance unknown";
  }

  top.appendChild(nameBlock);
  top.appendChild(travelBadge);

  const ratingRow = document.createElement("div");
  ratingRow.className = "rating-row";
  const stars = document.createElement("span");
  stars.className = "stars";
  stars.textContent = `★ ${details.rating ?? "–"}`;
  const reviews = document.createElement("span");
  reviews.textContent = `(${details.user_ratings_total ?? 0} reviews)`;
  ratingRow.appendChild(stars);
  ratingRow.appendChild(reviews);
  if (details.price_level !== undefined) {
    const price = document.createElement("span");
    price.className = "badge";
    price.textContent = "€".repeat(Math.max(1, details.price_level));
    ratingRow.appendChild(price);
  }
  if (!hasKnownHours(details)) {
    const warn = document.createElement("span");
    warn.className = "badge badge-warn";
    warn.textContent = "Confirm hours before visiting";
    ratingRow.appendChild(warn);
  }

  const blurb = document.createElement("p");
  blurb.className = "blurb";
  blurb.textContent = buildBlurb(details);

  const actions = document.createElement("div");
  actions.className = "card-actions";

  const mapsLink = document.createElement("a");
  mapsLink.className = "btn-maps";
  mapsLink.href = details.url || `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(details.name + " " + (details.formatted_address || ""))}`;
  mapsLink.target = "_blank";
  mapsLink.rel = "noopener";
  mapsLink.textContent = "📍 View on Google Maps";

  const bookLink = document.createElement("a");
  bookLink.className = "btn-book";
  bookLink.href = details.website || details.url;
  bookLink.target = "_blank";
  bookLink.rel = "noopener";
  bookLink.textContent = details.website ? "🌐 Website / Book" : "📅 Reserve on Google Maps";

  actions.appendChild(mapsLink);
  actions.appendChild(bookLink);

  card.appendChild(top);
  card.appendChild(ratingRow);
  card.appendChild(blurb);
  card.appendChild(actions);

  return card;
}

function hasKnownHours(details) {
  return !!(details.opening_hours && details.opening_hours.periods && details.opening_hours.periods.length);
}

function buildBlurb(details) {
  if (details.editorial_summary && details.editorial_summary.overview) {
    return details.editorial_summary.overview;
  }
  const count = details.user_ratings_total || 0;
  return `Rated ${details.rating}★ by ${count.toLocaleString()} diners — a consistently well-reviewed local favourite.`;
}
