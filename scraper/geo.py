"""US state normalization + coarse coordinates for the map.

We deliberately avoid a geocoding API: a city table for major metros (heavy on
California) plus state centroids is plenty for a dot map, and it keeps the
scraper free of API keys.
"""
from __future__ import annotations

import re

STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia",
    "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "PR": "Puerto Rico",
}
_NAME_TO_CODE = {v.lower(): k for k, v in STATES.items()}

STATE_CENTROIDS = {
    "AL": (32.8, -86.8), "AK": (64.2, -152.5), "AZ": (34.3, -111.7), "AR": (34.9, -92.4),
    "CA": (37.2, -119.5), "CO": (39.0, -105.5), "CT": (41.6, -72.7), "DE": (39.0, -75.5),
    "DC": (38.9, -77.0), "FL": (28.6, -82.4), "GA": (32.7, -83.4), "HI": (20.8, -156.3),
    "ID": (44.4, -114.6), "IL": (40.0, -89.2), "IN": (39.9, -86.3), "IA": (42.1, -93.5),
    "KS": (38.5, -98.4), "KY": (37.5, -85.3), "LA": (31.1, -92.0), "ME": (45.4, -69.2),
    "MD": (39.1, -76.8), "MA": (42.3, -71.8), "MI": (44.3, -85.4), "MN": (46.3, -94.3),
    "MS": (32.7, -89.7), "MO": (38.4, -92.5), "MT": (47.0, -109.6), "NE": (41.5, -99.8),
    "NV": (39.3, -116.6), "NH": (43.7, -71.6), "NJ": (40.2, -74.7), "NM": (34.4, -106.1),
    "NY": (42.9, -75.5), "NC": (35.6, -79.4), "ND": (47.4, -100.5), "OH": (40.3, -82.8),
    "OK": (35.6, -97.5), "OR": (43.9, -120.6), "PA": (40.9, -77.8), "RI": (41.7, -71.6),
    "SC": (33.9, -80.9), "SD": (44.4, -100.2), "TN": (35.9, -86.4), "TX": (31.5, -99.3),
    "UT": (39.3, -111.7), "VT": (44.1, -72.7), "VA": (37.5, -78.9), "WA": (47.4, -120.5),
    "WV": (38.6, -80.6), "WI": (44.6, -89.9), "WY": (43.0, -107.5), "PR": (18.2, -66.5),
}

# (city, state) -> (lat, lon). California is intentionally dense.
CITY_COORDS = {
    ("los angeles", "CA"): (34.05, -118.24), ("san francisco", "CA"): (37.77, -122.42),
    ("san diego", "CA"): (32.72, -117.16), ("san jose", "CA"): (37.34, -121.89),
    ("sacramento", "CA"): (38.58, -121.49), ("oakland", "CA"): (37.80, -122.27),
    ("fresno", "CA"): (36.74, -119.78), ("bakersfield", "CA"): (35.37, -119.02),
    ("irvine", "CA"): (33.68, -117.83), ("orange", "CA"): (33.79, -117.85),
    ("anaheim", "CA"): (33.84, -117.91), ("long beach", "CA"): (33.77, -118.19),
    ("pasadena", "CA"): (34.15, -118.14), ("duarte", "CA"): (34.14, -117.98),
    ("stanford", "CA"): (37.43, -122.17), ("palo alto", "CA"): (37.44, -122.14),
    ("santa monica", "CA"): (34.02, -118.49), ("torrance", "CA"): (33.84, -118.34),
    ("loma linda", "CA"): (34.05, -117.26), ("riverside", "CA"): (33.95, -117.40),
    ("san bernardino", "CA"): (34.11, -117.29), ("santa barbara", "CA"): (34.42, -119.70),
    ("santa rosa", "CA"): (38.44, -122.71), ("walnut creek", "CA"): (37.91, -122.07),
    ("santa clara", "CA"): (37.35, -121.95), ("redwood city", "CA"): (37.49, -122.24),
    ("south san francisco", "CA"): (37.65, -122.41), ("thousand oaks", "CA"): (34.17, -118.84),
    ("foster city", "CA"): (37.56, -122.27), ("emeryville", "CA"): (37.83, -122.29),
    ("berkeley", "CA"): (37.87, -122.27), ("davis", "CA"): (38.54, -121.74),
    ("modesto", "CA"): (37.64, -120.99), ("stockton", "CA"): (37.96, -121.29),
    ("visalia", "CA"): (36.33, -119.29), ("redding", "CA"): (40.59, -122.39),
    ("chico", "CA"): (39.73, -121.84), ("eureka", "CA"): (40.80, -124.16),
    ("monterey", "CA"): (36.60, -121.89), ("salinas", "CA"): (36.68, -121.66),
    ("san luis obispo", "CA"): (35.28, -120.66), ("ventura", "CA"): (34.27, -119.29),
    ("oxnard", "CA"): (34.20, -119.18), ("burbank", "CA"): (34.18, -118.31),
    ("glendale", "CA"): (34.14, -118.25), ("downey", "CA"): (33.94, -118.13),
    ("fontana", "CA"): (34.09, -117.44), ("ontario", "CA"): (34.06, -117.65),
    ("temecula", "CA"): (33.49, -117.15), ("murrieta", "CA"): (33.55, -117.21),
    ("escondido", "CA"): (33.12, -117.09), ("la jolla", "CA"): (32.84, -117.27),
    ("encinitas", "CA"): (33.04, -117.29), ("chula vista", "CA"): (32.64, -117.08),
    ("santa cruz", "CA"): (36.97, -122.03), ("napa", "CA"): (38.30, -122.29),
    ("vallejo", "CA"): (38.10, -122.26), ("fairfield", "CA"): (38.25, -122.04),
    ("roseville", "CA"): (38.75, -121.29), ("folsom", "CA"): (38.68, -121.18),
    ("mountain view", "CA"): (37.39, -122.08), ("sunnyvale", "CA"): (37.37, -122.04),
    ("fremont", "CA"): (37.55, -121.99), ("hayward", "CA"): (37.67, -122.08),
    ("san mateo", "CA"): (37.56, -122.33), ("daly city", "CA"): (37.69, -122.47),
    ("antioch", "CA"): (38.00, -121.81), ("concord", "CA"): (37.98, -122.03),
    ("lancaster", "CA"): (34.69, -118.15), ("palm springs", "CA"): (33.83, -116.55),
    ("rancho mirage", "CA"): (33.74, -116.41), ("el centro", "CA"): (32.79, -115.56),
    ("newport beach", "CA"): (33.62, -117.93), ("mission viejo", "CA"): (33.60, -117.67),
    ("fountain valley", "CA"): (33.71, -117.95), ("west hollywood", "CA"): (34.09, -118.36),
    ("beverly hills", "CA"): (34.07, -118.40), ("whittier", "CA"): (33.98, -118.03),
    ("west covina", "CA"): (34.07, -117.94), ("pomona", "CA"): (34.06, -117.75),
    ("santa ana", "CA"): (33.75, -117.87), ("huntington beach", "CA"): (33.66, -118.00),
    ("northridge", "CA"): (34.23, -118.54), ("tarzana", "CA"): (34.17, -118.55), ("simi valley", "CA"): (34.27, -118.78),
    ("corona", "CA"): (33.88, -117.57), ("cerritos", "CA"): (33.86, -118.06), ("san gabriel", "CA"): (34.10, -118.11),
    ("oceanside", "CA"): (33.20, -117.38), ("lakeport", "CA"): (39.04, -122.92), ("novato", "CA"): (38.11, -122.57),
    ("mather", "CA"): (38.55, -121.28), ("turlock", "CA"): (37.49, -120.85), ("merced", "CA"): (37.30, -120.48),
    ("san rafael", "CA"): (37.97, -122.53), ("pleasant hill", "CA"): (37.95, -122.06), ("dublin", "CA"): (37.70, -121.94),
    ("pleasanton", "CA"): (37.66, -121.87), ("livermore", "CA"): (37.68, -121.77), ("san leandro", "CA"): (37.72, -122.16),
    ("castro valley", "CA"): (37.69, -122.09), ("vacaville", "CA"): (38.36, -121.99), ("elk grove", "CA"): (38.41, -121.37),
    ("auburn", "CA"): (38.90, -121.08), ("grass valley", "CA"): (39.22, -121.06), ("truckee", "CA"): (39.33, -120.18),
    ("south lake tahoe", "CA"): (38.94, -119.98), ("santa maria", "CA"): (34.95, -120.44), ("lompoc", "CA"): (34.64, -120.46),
    ("paso robles", "CA"): (35.63, -120.69), ("templeton", "CA"): (35.55, -120.71), ("atascadero", "CA"): (35.49, -120.67),
    ("hanford", "CA"): (36.33, -119.65), ("tulare", "CA"): (36.21, -119.35), ("porterville", "CA"): (36.07, -119.02),
    ("madera", "CA"): (36.96, -120.06), ("clovis", "CA"): (36.83, -119.70), ("los banos", "CA"): (37.06, -120.85),
    ("mission hills", "CA"): (34.27, -118.46), ("panorama city", "CA"): (34.22, -118.45), ("woodland hills", "CA"): (34.17, -118.61),
    ("van nuys", "CA"): (34.19, -118.45), ("encino", "CA"): (34.16, -118.50), ("valencia", "CA"): (34.44, -118.61),
    ("santa clarita", "CA"): (34.39, -118.54), ("palmdale", "CA"): (34.58, -118.12), ("victorville", "CA"): (34.54, -117.29),
    ("apple valley", "CA"): (34.50, -117.19), ("hesperia", "CA"): (34.43, -117.30), ("redlands", "CA"): (34.06, -117.18),
    ("rancho cucamonga", "CA"): (34.11, -117.59), ("upland", "CA"): (34.10, -117.65), ("covina", "CA"): (34.09, -117.89),
    ("arcadia", "CA"): (34.14, -118.04), ("alhambra", "CA"): (34.10, -118.13), ("monterey park", "CA"): (34.06, -118.12),
    ("inglewood", "CA"): (33.96, -118.35), ("lynwood", "CA"): (33.93, -118.21), ("bellflower", "CA"): (33.88, -118.12),
    ("lakewood", "CA"): (33.85, -118.13), ("garden grove", "CA"): (33.77, -117.94), ("laguna hills", "CA"): (33.60, -117.71),
    ("laguna niguel", "CA"): (33.52, -117.71), ("san clemente", "CA"): (33.43, -117.61), ("san juan capistrano", "CA"): (33.50, -117.66),
    ("carlsbad", "CA"): (33.16, -117.35), ("vista", "CA"): (33.20, -117.24), ("san marcos", "CA"): (33.14, -117.17),
    ("poway", "CA"): (32.96, -117.04), ("el cajon", "CA"): (32.79, -116.96), ("la mesa", "CA"): (32.77, -117.02),
    ("national city", "CA"): (32.68, -117.10), ("indio", "CA"): (33.72, -116.22), ("la quinta", "CA"): (33.66, -116.31),
    ("palm desert", "CA"): (33.72, -116.37), ("hemet", "CA"): (33.75, -116.97), ("moreno valley", "CA"): (33.94, -117.23),
    ("santa cruz", "CA"): (36.97, -122.03), ("watsonville", "CA"): (36.91, -121.76), ("gilroy", "CA"): (37.01, -121.57),
    ("los gatos", "CA"): (37.23, -121.97), ("campbell", "CA"): (37.29, -121.95), ("milpitas", "CA"): (37.43, -121.90),
    ("burlingame", "CA"): (37.58, -122.35), ("san bruno", "CA"): (37.63, -122.41), ("menlo park", "CA"): (37.45, -122.18),
    ("marin", "CA"): (38.05, -122.55), ("greenbrae", "CA"): (37.95, -122.53), ("petaluma", "CA"): (38.23, -122.64),
    ("ukiah", "CA"): (39.15, -123.21), ("fort bragg", "CA"): (39.45, -123.81), ("crescent city", "CA"): (41.76, -124.20),
    ("yuba city", "CA"): (39.14, -121.62), ("marysville", "CA"): (39.15, -121.59), ("oroville", "CA"): (39.51, -121.56),
    ("red bluff", "CA"): (40.18, -122.24), ("susanville", "CA"): (40.42, -120.65), ("bishop", "CA"): (37.36, -118.40),
    ("ridgecrest", "CA"): (35.62, -117.67), ("barstow", "CA"): (34.90, -117.02), ("brawley", "CA"): (32.98, -115.53),
    ("orange county", "CA"): (33.72, -117.83), ("inland empire", "CA"): (34.00, -117.30), ("central valley", "CA"): (36.75, -119.75),
    ("bay area", "CA"): (37.65, -122.20), ("silicon valley", "CA"): (37.39, -122.06), ("north coast", "CA"): (40.50, -124.00),
    # Non-CA metros (enough to spread dots sensibly nationwide)
    ("new york", "NY"): (40.71, -74.01), ("boston", "MA"): (42.36, -71.06),
    ("philadelphia", "PA"): (39.95, -75.17), ("pittsburgh", "PA"): (40.44, -79.99),
    ("chicago", "IL"): (41.88, -87.63), ("houston", "TX"): (29.76, -95.37),
    ("dallas", "TX"): (32.78, -96.80), ("austin", "TX"): (30.27, -97.74),
    ("san antonio", "TX"): (29.42, -98.49), ("seattle", "WA"): (47.61, -122.33),
    ("portland", "OR"): (45.52, -122.68), ("denver", "CO"): (39.74, -104.99),
    ("aurora", "CO"): (39.73, -104.83), ("phoenix", "AZ"): (33.45, -112.07),
    ("tucson", "AZ"): (32.22, -110.97), ("scottsdale", "AZ"): (33.49, -111.93),
    ("las vegas", "NV"): (36.17, -115.14), ("salt lake city", "UT"): (40.76, -111.89),
    ("minneapolis", "MN"): (44.98, -93.27), ("rochester", "MN"): (44.02, -92.48),
    ("detroit", "MI"): (42.33, -83.05), ("ann arbor", "MI"): (42.28, -83.74),
    ("cleveland", "OH"): (41.50, -81.69), ("columbus", "OH"): (39.96, -83.00),
    ("cincinnati", "OH"): (39.10, -84.51), ("indianapolis", "IN"): (39.77, -86.16),
    ("st. louis", "MO"): (38.63, -90.20), ("saint louis", "MO"): (38.63, -90.20),
    ("kansas city", "MO"): (39.10, -94.58), ("nashville", "TN"): (36.16, -86.78),
    ("memphis", "TN"): (35.15, -90.05), ("atlanta", "GA"): (33.75, -84.39),
    ("miami", "FL"): (25.76, -80.19), ("tampa", "FL"): (27.95, -82.46),
    ("orlando", "FL"): (28.54, -81.38), ("jacksonville", "FL"): (30.33, -81.66),
    ("charlotte", "NC"): (35.23, -80.84), ("durham", "NC"): (35.99, -78.90),
    ("chapel hill", "NC"): (35.91, -79.06), ("raleigh", "NC"): (35.78, -78.64),
    ("baltimore", "MD"): (39.29, -76.61), ("bethesda", "MD"): (38.98, -77.09),
    ("rockville", "MD"): (39.08, -77.15), ("washington", "DC"): (38.91, -77.04),
    ("richmond", "VA"): (37.54, -77.44), ("charlottesville", "VA"): (38.03, -78.48),
    ("new haven", "CT"): (41.31, -72.92), ("providence", "RI"): (41.82, -71.41),
    ("buffalo", "NY"): (42.89, -78.88), ("albany", "NY"): (42.65, -73.75),
    ("newark", "NJ"): (40.74, -74.17), ("new brunswick", "NJ"): (40.49, -74.45),
    ("hershey", "PA"): (40.29, -76.65), ("milwaukee", "WI"): (43.04, -87.91),
    ("madison", "WI"): (43.07, -89.40), ("iowa city", "IA"): (41.66, -91.53),
    ("omaha", "NE"): (41.26, -95.94), ("oklahoma city", "OK"): (35.47, -97.52),
    ("little rock", "AR"): (34.75, -92.29), ("new orleans", "LA"): (29.95, -90.07),
    ("birmingham", "AL"): (33.52, -86.81), ("louisville", "KY"): (38.25, -85.76),
    ("lexington", "KY"): (38.04, -84.50), ("honolulu", "HI"): (21.31, -157.86),
    ("anchorage", "AK"): (61.22, -149.90), ("albuquerque", "NM"): (35.08, -106.65),
    ("boise", "ID"): (43.62, -116.20), ("spokane", "WA"): (47.66, -117.43),
    ("burlington", "VT"): (44.48, -73.21), ("portland", "ME"): (43.66, -70.26),
    ("manchester", "NH"): (42.99, -71.46), ("wilmington", "DE"): (39.75, -75.55),
    ("columbia", "SC"): (34.00, -81.03), ("charleston", "SC"): (32.78, -79.93),
    ("jackson", "MS"): (32.30, -90.18), ("sioux falls", "SD"): (43.55, -96.73),
    ("fargo", "ND"): (46.88, -96.79), ("billings", "MT"): (45.78, -108.50),
    ("cheyenne", "WY"): (41.14, -104.82), ("morgantown", "WV"): (39.63, -79.96),
    ("wichita", "KS"): (37.69, -97.34), ("tulsa", "OK"): (36.15, -95.99),
    ("el paso", "TX"): (31.76, -106.49), ("fort worth", "TX"): (32.75, -97.33),
    ("sacramento", "CA"): (38.58, -121.49), ("san juan", "PR"): (18.47, -66.11),
}

_STATE_CODE_RE = re.compile(r"\b([A-Z]{2})\b")


def state_code(s: str | None) -> str | None:
    """Return the 2-letter code for a state name/abbreviation, else None."""
    if not s:
        return None
    t = s.strip()
    if t.upper() in STATES:
        return t.upper()
    return _NAME_TO_CODE.get(t.lower())


def parse_location(text: str | None) -> tuple[str | None, str | None]:
    """Best-effort (city, state_code) from strings like 'Rockville, Maryland',
    'La Jolla, CA, USA', 'United States - Remote', 'California'."""
    if not text:
        return None, None
    # "San Francisco, CA or Oakland, CA" / "Fort Myers and Cape Coral, FL": use the first alternative
    # when it already names a state; otherwise borrow the state from the full string.
    alt = re.split(r"\s+(?:or|and|&)\s+", text, maxsplit=1)
    if len(alt) == 2:
        c1, s1 = parse_location(alt[0])
        if s1:
            return c1, s1
        c2, s2 = parse_location(alt[1])
        if s2 and c1 is None and looks_like_city(alt[0]):
            return alt[0].strip().title(), s2
    t = re.sub(r"\b(USA?|United States(?: of America)?)\b", "", text, flags=re.I)
    t = re.sub(r"\s*[-–|]\s*(Remote|Hybrid|Field).*$", "", t, flags=re.I)
    parts = [p.strip() for p in re.split(r"[,/]", t) if p.strip()]
    city = state = None
    for p in reversed(parts):
        code = state_code(p)
        if code and not state:
            state = code
        elif state and not city:
            city = p
    if not state:
        # "San Diego, CA 92101" style: a bare code only counts right after a comma —
        # otherwise "Hematologist/Oncologist - MD" would become Maryland.
        m = re.search(r",\s*([A-Z]{2})\b", t)
        if m and m.group(1) in STATES:
            state = m.group(1)
            city = t[: m.start()].strip(" ,") or None
    if not state:
        # "Northern California", "Central Valley California", "Metro South Carolina"
        for name, code in _NAME_TO_CODE.items():
            if re.search(r"\b" + re.escape(name) + r"\b", t, re.I):
                state = code
                break
    if city:
        city = re.split(r"\s+(?:or|and|&)\s+|/", city)[0].strip(" -–|,")
    if city and city.lower() == (STATES.get(state or "") or "").lower():
        city = None
    if city and city.lower() in ("new york city", "nyc", "manhattan"):
        city = "New York"
    if city and not looks_like_city(city):
        city = None
    return (city.title() if city else None), state


_NOT_CITY_RE = re.compile(
    r"[|–/#$%]|\bfacility|\bposition|\bfaculty|\bremote|hematolog|oncolog|physician|\bhem\b|\bonc\b|\barea\b|"
    r"\boutside\b|\bnear\b|\bopportunit|\bjob\b|\bclinical\b|\bacademic\b|\bmedical\b|\bgreater\b|\d",
    re.I,
)


def looks_like_city(city: str) -> bool:
    c = city.strip()
    return 2 <= len(c) <= 40 and not _NOT_CITY_RE.search(c) and not c.endswith("-")


def sanitize_locations(jobs: list[dict]) -> int:
    """Drop junk cities produced by earlier parsing (job titles, agency blurbs)."""
    n = 0
    for j in jobs:
        loc = j.get("location") or {}
        if loc.get("city") and not looks_like_city(loc["city"]):
            loc["city"] = None
            ll = STATE_CENTROIDS.get(loc.get("state") or "")
            loc["lat"], loc["lon"] = (ll[0], ll[1]) if ll else (None, None)
            loc["geo_precision"] = "state"
            n += 1
    return n


_CITY_RES: dict[str, re.Pattern] = {}


def find_city_in_text(state: str | None, title: str, text: str) -> str | None:
    """Best-effort city from free text using the known-city table for that state.
    Title mentions win; otherwise the most-mentioned city in the description."""
    if not state:
        return None
    if state not in _CITY_RES:
        names = sorted((c for c, s in CITY_COORDS if s == state), key=len, reverse=True)
        _CITY_RES[state] = re.compile(r"\b(" + "|".join(map(re.escape, names)) + r")\b", re.I) if names else re.compile(r"(?!x)x")
    rx = _CITY_RES[state]
    m = rx.findall(title)
    if m:
        return m[0].title()
    hits = [h.lower() for h in rx.findall(text)]
    if not hits:
        return None
    counts: dict[str, int] = {}
    for h in hits:
        counts[h] = counts.get(h, 0) + 1
    best = max(counts, key=lambda c: (counts[c], -hits.index(c)))
    return best.title()


def place_by_text(jobs: list[dict]) -> int:
    """For normalized jobs with a state but no city, scan title/description for a
    known city of that state and set city + coordinates. Returns count placed."""
    n = 0
    for j in jobs:
        loc = j.get("location") or {}
        if loc.get("state") and not loc.get("city"):
            c = find_city_in_text(loc["state"], j.get("title", ""), j.get("description", ""))
            if c:
                loc["city"] = c
                ll = coords(c, loc["state"])
                if ll:
                    loc["lat"], loc["lon"], loc["geo_precision"] = ll[0], ll[1], "city"
                n += 1
    return n


def coords(city: str | None, state: str | None) -> tuple[float, float] | None:
    if not state:
        return None
    if city:
        hit = CITY_COORDS.get((city.lower(), state))
        if hit:
            return hit
    return STATE_CENTROIDS.get(state)
