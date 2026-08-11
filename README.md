# Trip Bites 🍽️

A simple, no-install web app for finding well-reviewed restaurants near wherever you're
staying — with one tap to see it on Google Maps and one tap to book or visit its website.

**How it works:** you type in your hotel/accommodation and your travel dates, choose
**Dinner** or **Lunch**, tick a box if you have a car, and it shows a shortlist of
restaurants nearby, each with:

- Star rating and number of reviews
- Price level (shown as € / €€ / €€€ / €€€€)
- "Known for" tags mined from reviews and Google's editorial summary — e.g. Steak, Wine,
  Seafood, Tasting Menu, Truffle — so you know what each place specialises in at a glance
- For lunch, how close it is to a nice walk, park, beach, or landmark
- Distance and walking (or driving) time from your accommodation
- A "View on Google Maps" button
- A "Website / Book" button (or "Reserve on Google Maps" if the restaurant has no own site)

**Dinner mode** targets the **€50+ per person / €€€€ tier** (Google's highest price
level), and is only shown if it also clears a high quality bar (4.4★+ with a healthy
number of reviews) — gently relaxing to €€€ if a town doesn't have enough €€€€ options.
**Lunch mode** flips that: it targets casual **€/€€** places (4.2★+), and prioritises ones
within about a 12-minute walk of a park, tourist attraction, or beach, so it's easy to pair
a bite with sightseeing. Both modes automatically exclude chain fast-food restaurants,
buffets, and "tourist menu" spots. If you tick **"we have a car"**, the search widens to
include anywhere up to a 50-minute drive away; otherwise it sticks to a comfortable walk.

There's no backend server and nothing to install — it's a single web page that runs
entirely in the browser, so it works great on a phone.

## Two ways to run this

There are two independent versions of the same app in this repo — pick one:

| | Static web app | Streamlit app |
|---|---|---|
| Main file | `index.html` | **`streamlit_app.py`** |
| Runs on | Any web host / your own browser | [Streamlit Community Cloud](https://streamlit.io/cloud) (free) |
| API key entry | Pasted once in the browser, saved to that browser only | Stored server-side as a Streamlit "secret" — never exposed to visitors |
| Best for | GitHub Pages, opening the file directly | One-click free hosting, no GitHub Pages setup |

Instructions for the static app are below. For the **Streamlit version**, jump to
[Running the Streamlit app](#running-the-streamlit-app).

## One-time setup (5 minutes) — static web app

The app needs a free Google Maps API key to look up restaurants, ratings, and distances.

1. Go to the [Google Cloud Console](https://console.cloud.google.com/) and sign in with
   any Google account.
2. Create a new project (top-left project dropdown → "New Project"). Any name is fine,
   e.g. "Trip Bites".
3. Go to **APIs & Services → Library** and enable these three APIs:
   - **Maps JavaScript API**
   - **Places API**
   - **Distance Matrix API**
4. Go to **APIs & Services → Credentials → Create Credentials → API key**. Copy the key
   it gives you.
5. (Recommended) Click on the new key to restrict it:
   - Under **Application restrictions**, choose **Websites** and add the web address
     you'll open the app from (e.g. `https://yourusername.github.io/*` if using GitHub
     Pages — see below).
   - Under **API restrictions**, restrict it to the three APIs above.
6. Open the app and paste the key into the "Google Maps API key" box when prompted. It's
   saved in your browser only (never sent anywhere else) so you only do this once per
   device.

**Cost:** Google Maps Platform includes a recurring free usage tier every month, which
comfortably covers casual personal use like this. Check current pricing at
[mapsplatform.google.com/pricing](https://mapsplatform.google.com/pricing/) before
relying on it for a long trip, and consider setting a budget alert in the Cloud Console
for peace of mind.

## Using it

1. Open `index.html` (or the hosted link — see deployment below).
2. Paste your API key in once (first time only).
3. Type your hotel name, address, or the city you're staying in, and pick the matching
   suggestion from the dropdown.
4. Choose your arrival and departure dates.
5. Tick "We have a car" if you'd like restaurants up to 50 minutes' drive away included;
   leave it unticked to only see places within an easy walk.
6. Tap **Find Restaurants**.
7. Tap a restaurant's **View on Google Maps** to navigate there, or **Website / Book** to
   go straight to its booking page or site.

## Deploying so it's easy to open on a phone (optional)

The simplest option is **GitHub Pages**, which gives you a free public link:

1. Push this repository to GitHub (already done if you're reading this from the repo).
2. In the repository, go to **Settings → Pages**.
3. Under "Build and deployment", set **Source** to "Deploy from a branch", pick the
   branch this code is on, and folder `/ (root)`.
4. Save. GitHub will give you a URL like `https://yourusername.github.io/TRAVEL/` — open
   that on any phone or laptop.
5. If you restricted your API key to specific websites (step 5 above), add this exact
   URL (with a trailing `/*`) to the allowed list.

Bookmark the link on your phone's home screen for one-tap access while travelling.

## Running the Streamlit app

The Streamlit version is the **same app logic rebuilt in Python**, so it can be deployed
for free on [Streamlit Community Cloud](https://share.streamlit.io) without touching
GitHub Pages. Its main file is:

```
streamlit_app.py
```

### Deploy for free (recommended)

1. Push this repo to GitHub (already done).
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
3. Click **New app**, pick this repository and branch, and set the main file path to
   `streamlit_app.py`.
4. Before (or after) deploying, open the app's **Settings → Secrets** and paste:
   ```toml
   GOOGLE_MAPS_API_KEY = "your-key-here"
   ```
   Use the same key from the [setup steps above](#one-time-setup-5-minutes--static-web-app),
   but enable **Geocoding API**, **Places API**, and **Distance Matrix API** (not Maps
   JavaScript API — the Streamlit version doesn't need it). Since the key is only ever
   used server-side here, leave its **Application restrictions** set to "None" and only
   set **API restrictions** to those three APIs.
5. Deploy. Streamlit gives you a public URL you can bookmark on your phone.

Once the secret is set, **every visitor goes straight to the search form** — nobody ever
has to paste an API key, including on a different phone or browser. That's the main
advantage of this version over the static one for sharing with family.

### Verified location lookup

The "Where are you staying?" box shows a **live dropdown of matches as you type**, backed
by Google Maps' own Places database — the same experience as Google's own address
autocomplete widgets, distinguishing e.g. "Hotel Le Meurice, Paris" from a same-named spa
or street. Pick the right one from the list, and the app shows the confirmed address plus
a **"View on Google Maps"** button linking straight to that exact place, so you can
double-check it's correct before it searches for restaurants nearby. If Google has no
matches for what you typed, the dropdown offers a "use exactly as typed (unverified)"
option as a fallback.

### Direct booking links

The **"Book a Table"** button tries to skip straight to a restaurant's actual reservation
page instead of just its homepage. It checks the restaurant's website for a link to a
known booking platform (OpenTable, Resy, TheFork, Quandoo, SevenRooms, Tock, and others)
or a page whose link looks like a reservations/booking page, and uses that if found. If
nothing booking-related is found, it falls back to the plain website, then to the
restaurant's Google Maps page (which shows its own "Reserve a table" option automatically
when the restaurant supports it). This is a best-effort scan of the homepage's links, not
a guarantee — some restaurant websites won't have a detectable link (e.g. reservations
handled only by phone, or a booking widget that JavaScript loads in without a plain link).

### No car? Willing to Uber

There are two independent ways to widen the search beyond an easy walk:

- **"Willing to take an Uber/taxi"** — up to a **20-minute** drive away
- **"We have a car"** — up to a **50-minute** drive away

Tick either or both. If you tick **only** the Uber option, results reached that way are
clearly labelled **🚕 (Uber/taxi)** instead of a plain car icon, so it's obvious a ride is
needed rather than your own vehicle. If "We have a car" is ticked (with or without Uber),
the wider 50-minute car search takes over and results just show the plain car icon, since
driving yourself covers everything a shorter Uber trip would.

### Dinner vs. Lunch

A radio toggle right under the location box switches between two different profiles:

- **Dinner (upscale, €50pp+)** — the default. Targets fine dining ($$$$/€€€€), 4.4★+.
- **Lunch (casual, near sights)** — targets casual, inexpensive-to-moderate places
  (€/€€), 4.2★+, and gives a ranking boost to anywhere within roughly a 12-minute walk of
  a park, tourist attraction, or beach (found via a separate Google Places lookup around
  your accommodation). When a restaurant qualifies, its card shows a line like
  "🏖️ 8 min walk to [landmark]" so you can pair lunch with a walk, a swim, or sightseeing.
  Lunch mode also doesn't penalise busy/high-review-count places the way dinner mode does
  — a great casual spot next to a beach is *supposed* to be popular.

Both modes still exclude chains, buffets, and "tourist menu" spots, and both fall back
gracefully (never leaving you empty-handed) exactly as described below.

### At least 7 results, whenever there's anything to show

The app tries hard not to leave you with a thin or empty list. Restaurants aren't hard-cut
by price tier or rating — a $$$$-and-4.4★+ place always ranks first, but $$$/casual/less-
reviewed options are still ranked (just lower) rather than thrown away, and if the top
batch doesn't clear 7 valid, open, reachable results, the app automatically pulls in more
candidates from further down the list until it does (or runs out of nearby restaurants
entirely). In a genuinely small town with only a handful of restaurants total, you'll see
however many actually exist — the app can't invent restaurants that aren't there, but it
will always show the most it possibly can rather than giving up early.

### Running it locally instead

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # then edit in your key
streamlit run streamlit_app.py
```

If you skip the secrets file, the app will ask you to paste an API key directly in the
browser instead (handy for a quick local test, but it only lasts that session).

## Good to know / limitations

- **Opening hours** are checked against each restaurant's usual weekly schedule, not
  public holidays or one-off closures — always confirm before making a special trip.
- **Booking links**: not every restaurant has online booking. Where there's no dedicated
  website, the "Reserve on Google Maps" button opens its Google Maps page, which shows a
  reservation option automatically when the restaurant supports it (e.g. via OpenTable
  or The Fork); otherwise you may need to call ahead.
- **Distances/times** are Google's typical estimates, not live traffic.
- **"Known for" tags** are mined from Google's editorial summary and review text using
  keyword matching (steak, seafood, wine, tasting menu, etc.) — they're a helpful hint,
  not a verified menu, so a restaurant might be great at something the tags don't catch.
- **Price/tourist filtering** relies on Google's own price-level and review data, which
  isn't perfect everywhere — very new or lesser-reviewed gems can be missed, and
  occasionally a place slips through despite the filters.
- Everything (your API key, search inputs) stays local in your browser — the app has no
  server and doesn't store or transmit your data anywhere else.

## Files

Static web app:
- `index.html` — page structure and the search form
- `style.css` — styling (large, high-contrast, mobile-friendly)
- `app.js` — all the search, filtering, ranking, and rendering logic

Streamlit app:
- `streamlit_app.py` — main file: search form, Google Places/Distance Matrix calls,
  filtering, ranking, and rendering
- `requirements.txt` — Python dependencies
- `.streamlit/secrets.toml.example` — template for your API key secret
