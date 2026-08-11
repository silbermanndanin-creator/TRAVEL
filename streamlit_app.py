import re
import time
from datetime import date
from functools import partial
from urllib.parse import urljoin

import requests
import streamlit as st
from streamlit_searchbox import st_searchbox

EXCLUDE_KEYWORDS = [
    "mcdonald", "burger king", "kfc", "starbucks", "subway", "pizza hut",
    "domino", "taco bell", "dunkin", "costa coffee", "greggs", "five guys",
    "nando", "wendy", "papa john", "wagamama express",
    "buffet", "all you can eat", "all-you-can-eat", "tourist menu", "set menu tourist",
]

WALK_LIMIT_SECONDS = 25 * 60
DRIVE_LIMIT_SECONDS = 50 * 60
WALK_SEARCH_RADIUS_M = 2200
CAR_SEARCH_RADIUS_M = 45000
TARGET_PRICE_LEVEL = 4  # Google's $$$$ tier, roughly €50+ per person
FALLBACK_PRICE_LEVEL = 3  # used only if too few $$$$ options exist nearby
MIN_RATING_PREMIUM = 4.4
MIN_REVIEWS_PREMIUM = 30
MAX_REVIEWS_CAP = 6000  # above this, volume usually means high-turnover/tourist crowd, not exclusivity
MIN_RATING_RELAXED = 4.0
MIN_REVIEWS_RELAXED = 20
MAX_RESULTS_SHOWN = 9

TAG_KEYWORDS = [
    ("Steak", ["steak", "ribeye", "sirloin", "chateaubriand", "tomahawk"]),
    ("Seafood", ["seafood", "oyster", "lobster", "prawn", "shellfish", "crab", " fish "]),
    ("Sushi", ["sushi", "sashimi", "omakase"]),
    ("Pizza", ["pizza", "pizzeria"]),
    ("Pasta", ["pasta", "risotto", "gnocchi"]),
    ("Tapas / Small Plates", ["tapas", "small plates", "sharing plates"]),
    ("Grill / BBQ", ["grill", "bbq", "barbecue", "chargrill", "charcoal"]),
    ("Tasting Menu", ["tasting menu", "degustation", "chef's menu", "chef's table"]),
    ("Wine", ["wine list", "wine pairing", "sommelier", "wine cellar", "extensive wine"]),
    ("Cocktails", ["cocktail", "mixology", "speakeasy"]),
    ("Truffle", ["truffle"]),
    ("Cheese", ["cheese board", "cheese selection", "fromage"]),
    ("Desserts / Pastry", ["dessert", "pastry", "patisserie", "chocolate"]),
    ("Vegetarian / Vegan", ["vegetarian", "vegan", "plant-based", "plant based"]),
    ("Traditional / Local Cuisine", ["traditional", "authentic", "local specialt", "family recipe"]),
]
MAX_TAGS_SHOWN = 4

RESERVATION_HOST_HINTS = [
    "opentable.", "resy.com", "thefork.", "quandoo.", "sevenrooms.",
    "exploretock.", "zenchef.", "formitable.", "bookatable.", "reserve.google.com",
]
RESERVATION_PATH_HINTS = ["reserv", "book-a-table", "/book", "booking"]

DETAIL_FIELDS = ",".join([
    "name", "rating", "user_ratings_total", "price_level", "formatted_address",
    "geometry", "opening_hours", "website", "url", "types", "editorial_summary",
    "business_status", "reviews",
])

st.set_page_config(page_title="Trip Bites", page_icon="🍽️", layout="centered")


def get_api_key():
    try:
        secret_key = st.secrets.get("GOOGLE_MAPS_API_KEY")
    except Exception:
        secret_key = None
    if secret_key:
        return secret_key
    return st.session_state.get("api_key")


def api_key_gate():
    key = get_api_key()
    if key:
        return key

    st.title("🍽️ Trip Bites")
    st.caption("Find great, locally-loved restaurants wherever you're staying.")
    st.info(
        "This app needs a free Google Maps API key (Geocoding, Places, and Distance "
        "Matrix APIs enabled) to look up restaurants. See README.md for setup steps. "
        "For a permanent deployment, add it as a Streamlit secret named "
        "`GOOGLE_MAPS_API_KEY` instead of typing it below."
    )
    entered = st.text_input("Google Maps API key", type="password")
    if st.button("Save & Continue", type="primary"):
        if entered.strip():
            st.session_state["api_key"] = entered.strip()
            st.rerun()
        else:
            st.error("Please paste a valid API key.")
    st.stop()


@st.cache_data(ttl=600, show_spinner=False)
def autocomplete_predictions(input_text, api_key):
    resp = requests.get(
        "https://maps.googleapis.com/maps/api/place/autocomplete/json",
        params={"input": input_text, "key": api_key},
        timeout=15,
    )
    data = resp.json()
    if data.get("status") not in ("OK", "ZERO_RESULTS"):
        return []
    return [
        {"description": p["description"], "place_id": p["place_id"]}
        for p in data.get("predictions", [])
    ]


@st.cache_data(ttl=3600, show_spinner=False)
def get_place_location(place_id, api_key):
    resp = requests.get(
        "https://maps.googleapis.com/maps/api/place/details/json",
        params={"place_id": place_id, "fields": "name,formatted_address,geometry,url", "key": api_key},
        timeout=15,
    )
    data = resp.json()
    if data.get("status") != "OK":
        return None
    result = data["result"]
    loc = result["geometry"]["location"]
    return {
        "place_id": place_id,
        "name": result.get("name"),
        "lat": loc["lat"],
        "lng": loc["lng"],
        "formatted_address": result.get("formatted_address", result.get("name", "")),
        "maps_url": result.get("url"),
    }


@st.cache_data(ttl=3600, show_spinner=False)
def geocode_location(address, api_key):
    resp = requests.get(
        "https://maps.googleapis.com/maps/api/geocode/json",
        params={"address": address, "key": api_key},
        timeout=15,
    )
    data = resp.json()
    if data.get("status") != "OK" or not data.get("results"):
        return None
    result = data["results"][0]
    loc = result["geometry"]["location"]
    return {
        "place_id": result.get("place_id"),
        "name": result["formatted_address"],
        "lat": loc["lat"],
        "lng": loc["lng"],
        "formatted_address": result["formatted_address"],
        "maps_url": (
            f"https://www.google.com/maps/place/?q=place_id:{result['place_id']}"
            if result.get("place_id") else None
        ),
    }


@st.cache_data(ttl=1800, show_spinner=False)
def nearby_search_restaurants(lat, lng, radius, api_key):
    all_results = []
    params = {"location": f"{lat},{lng}", "radius": radius, "type": "restaurant", "key": api_key}
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"

    for page in range(2):
        resp = requests.get(url, params=params, timeout=15)
        data = resp.json()
        status = data.get("status")
        if status == "ZERO_RESULTS":
            break
        if status != "OK":
            if all_results:
                break
            raise RuntimeError(f"Places search failed: {status}")
        all_results.extend(data.get("results", []))
        token = data.get("next_page_token")
        if not token or page == 1:
            break
        time.sleep(2)
        params = {"pagetoken": token, "key": api_key}

    return all_results


@st.cache_data(ttl=1800, show_spinner=False)
def get_place_details(place_id, api_key):
    resp = requests.get(
        "https://maps.googleapis.com/maps/api/place/details/json",
        params={"place_id": place_id, "fields": DETAIL_FIELDS, "key": api_key},
        timeout=15,
    )
    data = resp.json()
    if data.get("status") != "OK":
        return None
    return data.get("result")


@st.cache_data(ttl=86400, show_spinner=False)
def find_reservation_link(website_url):
    try:
        resp = requests.get(
            website_url, timeout=3,
            headers={"User-Agent": "Mozilla/5.0 (compatible; TripBitesBot/1.0)"},
        )
        html = resp.text[:200000]
    except requests.RequestException:
        return None

    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html, re.IGNORECASE)

    def resolve(href):
        return href if href.lower().startswith("http") else urljoin(website_url, href)

    for href in hrefs:
        if any(h in href.lower() for h in RESERVATION_HOST_HINTS):
            return resolve(href)
    for href in hrefs:
        if any(p in href.lower() for p in RESERVATION_PATH_HINTS):
            return resolve(href)
    return None


def filter_and_score(raw_results):
    deduped = {}
    for r in raw_results:
        place_id = r.get("place_id")
        if not place_id or place_id in deduped:
            continue
        if r.get("business_status") and r["business_status"] != "OPERATIONAL":
            continue
        name_lower = (r.get("name") or "").lower()
        if any(kw in name_lower for kw in EXCLUDE_KEYWORDS):
            continue
        deduped[place_id] = r
    candidates = list(deduped.values())

    def meets_quality_bar(r, min_rating, min_reviews):
        review_count = r.get("user_ratings_total") or 0
        return (r.get("rating") or 0) >= min_rating and min_reviews <= review_count <= MAX_REVIEWS_CAP

    def is_premium_tier(r):
        return r.get("price_level") == TARGET_PRICE_LEVEL

    def is_acceptable_tier(r):
        return r.get("price_level") in (TARGET_PRICE_LEVEL, FALLBACK_PRICE_LEVEL)

    pool = [r for r in candidates if is_premium_tier(r) and meets_quality_bar(r, MIN_RATING_PREMIUM, MIN_REVIEWS_PREMIUM)]
    if len(pool) < 5:
        pool = [r for r in candidates if is_acceptable_tier(r) and meets_quality_bar(r, MIN_RATING_PREMIUM, MIN_REVIEWS_PREMIUM)]
    if not pool:
        pool = [r for r in candidates if is_acceptable_tier(r) and meets_quality_bar(r, MIN_RATING_RELAXED, MIN_REVIEWS_RELAXED)]

    for r in pool:
        score = (r.get("rating") or 0) * _log10(1 + (r.get("user_ratings_total") or 0))
        if is_premium_tier(r):
            score *= 1.05
        r["_score"] = score

    return sorted(pool, key=lambda r: r["_score"], reverse=True)


def _log10(x):
    import math
    return math.log10(x) if x > 0 else 0


def extract_tags(details):
    review_texts = " ".join(rev.get("text", "") for rev in details.get("reviews", []))
    combined = f"{details.get('name', '')} {(details.get('editorial_summary') or {}).get('overview', '')} {review_texts}".lower()

    matched = []
    for label, triggers in TAG_KEYWORDS:
        if any(t in combined for t in triggers):
            matched.append(label)
            if len(matched) >= MAX_TAGS_SHOWN:
                break
    return matched


def distance_matrix(origin, destinations, mode, api_key):
    dest_param = "|".join(f"{d['lat']},{d['lng']}" for d in destinations)
    resp = requests.get(
        "https://maps.googleapis.com/maps/api/distancematrix/json",
        params={
            "origins": f"{origin['lat']},{origin['lng']}",
            "destinations": dest_param,
            "mode": mode,
            "units": "metric",
            "key": api_key,
        },
        timeout=15,
    )
    data = resp.json()
    if data.get("status") != "OK":
        return None
    return data["rows"][0]["elements"]


def attach_distances(paired, origin, expand_radius, api_key, drive_icon="🚗", drive_label=None):
    if not paired:
        return []

    destinations = [p["details"]["geometry"]["location"] for p in paired]
    walk_elements = distance_matrix(origin, destinations, "walking", api_key)
    drive_elements = distance_matrix(origin, destinations, "driving", api_key) if expand_radius else None

    results = []
    for i, p in enumerate(paired):
        travel = None
        walk_el = walk_elements[i] if walk_elements else None
        drive_el = drive_elements[i] if drive_elements else None

        if walk_el and walk_el.get("status") == "OK" and walk_el["duration"]["value"] <= WALK_LIMIT_SECONDS:
            travel = {"mode": "walk", "icon": "🚶", "label": None, "duration": walk_el["duration"], "distance": walk_el["distance"]}
        elif drive_el and drive_el.get("status") == "OK" and drive_el["duration"]["value"] <= DRIVE_LIMIT_SECONDS:
            travel = {"mode": "drive", "icon": drive_icon, "label": drive_label, "duration": drive_el["duration"], "distance": drive_el["distance"]}

        results.append({"details": p["details"], "travel": travel, "score": p["candidate_score"]})
    return results


def collect_weekdays(start_date, end_date):
    weekdays = set()
    cursor = start_date
    guard = 0
    while cursor <= end_date and guard < 60:
        weekdays.add((cursor.weekday() + 1) % 7)  # Google: 0=Sunday
        cursor = date.fromordinal(cursor.toordinal() + 1)
        guard += 1
        if len(weekdays) == 7:
            break
    return weekdays


def is_open_during_stay(details, weekday_set):
    oh = details.get("opening_hours")
    periods = oh.get("periods") if oh else None
    if not periods:
        return True
    if len(periods) == 1 and "close" not in periods[0]:
        return True
    return any(p.get("open", {}).get("day") in weekday_set for p in periods)


def build_blurb(details):
    summary = details.get("editorial_summary", {}).get("overview") if details.get("editorial_summary") else None
    if summary:
        return summary
    count = details.get("user_ratings_total", 0)
    rating = details.get("rating", "–")
    return f"Rated {rating}★ by {count:,} diners — a consistently well-reviewed local favourite."


def render_card(details, travel):
    with st.container(border=True):
        top_left, top_right = st.columns([3, 1])
        with top_left:
            st.markdown(f"**{details['name']}**")
            st.caption(details.get("formatted_address", ""))
        with top_right:
            if travel:
                text = f"{travel['icon']} {travel['duration']['text']}"
                if travel.get("label"):
                    text += f" ({travel['label']})"
                st.markdown(f"`{text}`")
                st.caption(travel["distance"]["text"])
            else:
                st.markdown("`Distance unknown`")

        rating = details.get("rating", "–")
        reviews = details.get("user_ratings_total", 0)
        price = "€" * max(1, details.get("price_level", 0)) if details.get("price_level") is not None else ""
        hours_note = "" if details.get("opening_hours", {}).get("periods") else " · ⚠️ confirm hours before visiting"
        st.markdown(f"★ **{rating}** ({reviews:,} reviews)  {price}{hours_note}")

        tags = extract_tags(details)
        if tags:
            st.caption("Known for: " + " · ".join(tags))

        st.write(build_blurb(details))

        link_col1, link_col2 = st.columns(2)
        maps_url = details.get("url") or (
            "https://www.google.com/maps/search/?api=1&query="
            + requests.utils.quote(f"{details['name']} {details.get('formatted_address', '')}")
        )
        link_col1.link_button("📍 View on Google Maps", maps_url, use_container_width=True)

        reservation_url = details.get("reservation_url")
        website = details.get("website")
        if reservation_url:
            book_url, book_label = reservation_url, "📅 Book a Table"
        elif website:
            book_url, book_label = website, "🌐 Website / Book"
        else:
            book_url, book_label = maps_url, "📅 Reserve on Google Maps"
        link_col2.link_button(book_label, book_url, use_container_width=True)


def search_google_places(searchterm, api_key):
    text = (searchterm or "").strip()
    if not text:
        return []
    predictions = autocomplete_predictions(text, api_key)
    options = [(p["description"], ("place", p["place_id"])) for p in predictions]
    if not options:
        options.append((f'Use "{text}" exactly as typed (unverified)', ("raw", text)))
    return options


def location_picker(api_key):
    selected = st_searchbox(
        partial(search_google_places, api_key=api_key),
        placeholder="Hotel name, address, or city",
        label="Where are you staying?",
        key="location_searchbox",
    )

    if selected and selected != st.session_state.get("_last_location_selection"):
        st.session_state["_last_location_selection"] = selected
        kind, value = selected
        with st.spinner("Confirming location…"):
            accommodation = get_place_location(value, api_key) if kind == "place" else geocode_location(value, api_key)
        st.session_state["accommodation"] = accommodation
        if not accommodation:
            st.error("Couldn't find that location. Try a different spelling.")

    accommodation = st.session_state.get("accommodation")
    if accommodation:
        st.success(f"📍 Location set: {accommodation['formatted_address']}")
        if accommodation.get("maps_url"):
            st.link_button("View on Google Maps", accommodation["maps_url"])

    return accommodation


def main():
    api_key = api_key_gate()

    st.title("🍽️ Trip Bites")
    st.caption("Find great, locally-loved restaurants wherever you're staying.")

    accommodation = location_picker(api_key)

    col1, col2 = st.columns(2)
    start_date = col1.date_input("Arrival date", value=date.today(), min_value=date.today())
    end_date = col2.date_input("Departure date", value=date.today(), min_value=date.today())
    has_car = st.checkbox("We have a car (search up to 50 minutes' drive away)")
    willing_to_uber = st.checkbox("Willing to take an Uber/taxi (search up to 50 minutes away for more options)")
    submitted = st.button("Find Restaurants", type="primary", use_container_width=True)

    if not submitted:
        return

    if not accommodation:
        st.error("Please select your accommodation from the Google Maps suggestions above first.")
        return
    if end_date < start_date:
        st.error("Departure date can't be before arrival date.")
        return

    expand_radius = has_car or willing_to_uber
    if has_car:
        drive_icon, drive_label = "🚗", None
    else:
        drive_icon, drive_label = "🚕", "Uber/taxi"

    with st.spinner("Researching local favourites…"):
        try:
            place = accommodation
            weekdays = collect_weekdays(start_date, end_date)
            radius = CAR_SEARCH_RADIUS_M if expand_radius else WALK_SEARCH_RADIUS_M

            raw_results = nearby_search_restaurants(place["lat"], place["lng"], radius, api_key)
            filtered = filter_and_score(raw_results)

            if not filtered:
                st.warning(
                    "No great matches found nearby. Try widening the search by ticking "
                    "\"we have a car\" or \"willing to take an Uber/taxi\", or double-check "
                    "the location."
                )
                return

            top_candidates = filtered[:20]
            paired = []
            for cand in top_candidates:
                details = get_place_details(cand["place_id"], api_key)
                if details:
                    paired.append({"details": details, "candidate_score": cand["_score"]})

            with_distances = attach_distances(paired, place, expand_radius, api_key, drive_icon, drive_label)

            final_list = [
                r for r in with_distances
                if r["travel"] is not None and is_open_during_stay(r["details"], weekdays)
            ]
            final_list.sort(key=lambda r: r["score"], reverse=True)
            final_list = final_list[:MAX_RESULTS_SHOWN]

            if not final_list:
                st.warning(
                    "No great matches found nearby. Try widening the search by ticking "
                    "\"we have a car\", or double-check the location."
                )
                return

        except RuntimeError as e:
            st.error(f"Something went wrong fetching restaurants: {e}")
            return

    with st.spinner("Finding direct booking links…"):
        for r in final_list:
            website = r["details"].get("website")
            if website:
                r["details"]["reservation_url"] = find_reservation_link(website)

    if has_car and willing_to_uber:
        mode_note = "walking + driving/Uber"
    elif has_car:
        mode_note = "walking + driving"
    elif willing_to_uber:
        mode_note = "walking + Uber/taxi"
    else:
        mode_note = "walking distance"
    st.caption(
        f"{len(final_list)} great option{'s' if len(final_list) != 1 else ''} near "
        f"{place['formatted_address']} ({mode_note})."
    )
    for r in final_list:
        render_card(r["details"], r["travel"])


if __name__ == "__main__":
    main()
