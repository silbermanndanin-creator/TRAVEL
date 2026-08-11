import time
from datetime import date

import requests
import streamlit as st

CHAIN_BLACKLIST = [
    "mcdonald", "burger king", "kfc", "starbucks", "subway", "pizza hut",
    "domino", "taco bell", "dunkin", "costa coffee", "greggs", "five guys",
    "nando", "wendy", "papa john", "wagamama express",
]

WALK_LIMIT_SECONDS = 25 * 60
DRIVE_LIMIT_SECONDS = 50 * 60
WALK_SEARCH_RADIUS_M = 2200
CAR_SEARCH_RADIUS_M = 45000
MIN_RATING_STRICT = 4.3
MIN_REVIEWS_STRICT = 50
MIN_RATING_RELAXED = 4.0
MIN_REVIEWS_RELAXED = 20
MAX_RESULTS_SHOWN = 9

DETAIL_FIELDS = ",".join([
    "name", "rating", "user_ratings_total", "price_level", "formatted_address",
    "geometry", "opening_hours", "website", "url", "types", "editorial_summary",
    "business_status",
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
    return {"lat": loc["lat"], "lng": loc["lng"], "formatted_address": result["formatted_address"]}


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


def filter_and_score(raw_results):
    deduped = {}
    for r in raw_results:
        place_id = r.get("place_id")
        if not place_id or place_id in deduped:
            continue
        if r.get("business_status") and r["business_status"] != "OPERATIONAL":
            continue
        name_lower = (r.get("name") or "").lower()
        if any(chain in name_lower for chain in CHAIN_BLACKLIST):
            continue
        deduped[place_id] = r
    candidates = list(deduped.values())

    strict = [
        r for r in candidates
        if (r.get("rating") or 0) >= MIN_RATING_STRICT
        and (r.get("user_ratings_total") or 0) >= MIN_REVIEWS_STRICT
    ]
    pool = strict if len(strict) >= 5 else [
        r for r in candidates
        if (r.get("rating") or 0) >= MIN_RATING_RELAXED
        and (r.get("user_ratings_total") or 0) >= MIN_REVIEWS_RELAXED
    ]
    if not pool:
        pool = candidates

    for r in pool:
        score = (r.get("rating") or 0) * _log10(1 + (r.get("user_ratings_total") or 0))
        if r.get("price_level") == 4:
            score *= 0.92
        r["_score"] = score

    return sorted(pool, key=lambda r: r["_score"], reverse=True)


def _log10(x):
    import math
    return math.log10(x) if x > 0 else 0


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


def attach_distances(paired, origin, has_car, api_key):
    if not paired:
        return []

    destinations = [p["details"]["geometry"]["location"] for p in paired]
    walk_elements = distance_matrix(origin, destinations, "walking", api_key)
    drive_elements = distance_matrix(origin, destinations, "driving", api_key) if has_car else None

    results = []
    for i, p in enumerate(paired):
        travel = None
        walk_el = walk_elements[i] if walk_elements else None
        drive_el = drive_elements[i] if drive_elements else None

        if walk_el and walk_el.get("status") == "OK" and walk_el["duration"]["value"] <= WALK_LIMIT_SECONDS:
            travel = {"mode": "walk", "duration": walk_el["duration"], "distance": walk_el["distance"]}
        elif drive_el and drive_el.get("status") == "OK" and drive_el["duration"]["value"] <= DRIVE_LIMIT_SECONDS:
            travel = {"mode": "drive", "duration": drive_el["duration"], "distance": drive_el["distance"]}

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
                icon = "🚶" if travel["mode"] == "walk" else "🚗"
                st.markdown(f"`{icon} {travel['duration']['text']}`")
                st.caption(travel["distance"]["text"])
            else:
                st.markdown("`Distance unknown`")

        rating = details.get("rating", "–")
        reviews = details.get("user_ratings_total", 0)
        price = "€" * max(1, details.get("price_level", 0)) if details.get("price_level") is not None else ""
        hours_note = "" if details.get("opening_hours", {}).get("periods") else " · ⚠️ confirm hours before visiting"
        st.markdown(f"★ **{rating}** ({reviews:,} reviews)  {price}{hours_note}")

        st.write(build_blurb(details))

        link_col1, link_col2 = st.columns(2)
        maps_url = details.get("url") or (
            "https://www.google.com/maps/search/?api=1&query="
            + requests.utils.quote(f"{details['name']} {details.get('formatted_address', '')}")
        )
        link_col1.link_button("📍 View on Google Maps", maps_url, use_container_width=True)
        book_url = details.get("website") or details.get("url")
        book_label = "🌐 Website / Book" if details.get("website") else "📅 Reserve on Google Maps"
        link_col2.link_button(book_label, book_url, use_container_width=True)


def main():
    api_key = api_key_gate()

    st.title("🍽️ Trip Bites")
    st.caption("Find great, locally-loved restaurants wherever you're staying.")

    with st.form("search_form"):
        location_text = st.text_input(
            "Where are you staying?", placeholder="Hotel name, address, or city"
        )
        col1, col2 = st.columns(2)
        start_date = col1.date_input("Arrival date", value=date.today(), min_value=date.today())
        end_date = col2.date_input("Departure date", value=date.today(), min_value=date.today())
        has_car = st.checkbox("We have a car (search up to 50 minutes' drive away)")
        submitted = st.form_submit_button("Find Restaurants", type="primary", use_container_width=True)

    if not submitted:
        return

    if not location_text.strip():
        st.error("Please enter where you're staying.")
        return
    if end_date < start_date:
        st.error("Departure date can't be before arrival date.")
        return

    with st.spinner("Researching local favourites…"):
        try:
            place = geocode_location(location_text.strip(), api_key)
            if not place:
                st.error("Couldn't find that location. Try a more specific address or hotel name.")
                return

            weekdays = collect_weekdays(start_date, end_date)
            radius = CAR_SEARCH_RADIUS_M if has_car else WALK_SEARCH_RADIUS_M

            raw_results = nearby_search_restaurants(place["lat"], place["lng"], radius, api_key)
            filtered = filter_and_score(raw_results)

            if not filtered:
                st.warning(
                    "No great matches found nearby. Try widening the search by ticking "
                    "\"we have a car\", or double-check the location."
                )
                return

            top_candidates = filtered[:20]
            paired = []
            for cand in top_candidates:
                details = get_place_details(cand["place_id"], api_key)
                if details:
                    paired.append({"details": details, "candidate_score": cand["_score"]})

            with_distances = attach_distances(paired, place, has_car, api_key)

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

    mode_note = "walking + driving" if has_car else "walking distance"
    st.caption(
        f"{len(final_list)} great option{'s' if len(final_list) != 1 else ''} near "
        f"{place['formatted_address']} ({mode_note})."
    )
    for r in final_list:
        render_card(r["details"], r["travel"])


if __name__ == "__main__":
    main()
