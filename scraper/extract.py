"""Rule-based field extraction from a job posting's title + description.

Everything here is deterministic regex/keyword logic so the pipeline works with
no API keys. `llm_enrich.py` can optionally overwrite these fields with a
Claude-extracted version when ANTHROPIC_API_KEY is set.
"""
from __future__ import annotations

import re

# --------------------------------------------------------------------------
# Relevance: is this a physician-level heme/onc job?
# --------------------------------------------------------------------------
HEME_ONC_RE = re.compile(
    r"hematolog|haematolog|oncolog|\bheme\b|\bhem[/ -]?onc|\bBMT\b|bone marrow transplant|"
    r"stem cell transplant|cell(?:ular)? therapy|leukemia|lymphoma|myeloma|malignan|cancer center|"
    r"\bcancer\b",
    re.I,
)
NON_PHYSICIAN_TITLE_RE = re.compile(
    r"\b(nurse|\bRN\b|\bNP\b|\bPA-C\b|physician assistant|nurse practitioner|\bAPP\b|advanced practice|"
    r"pharmacist|pharmacy|technologist|technician|phlebotom|medical assistant|\bMA\b|coordinator|"
    r"navigator|scheduler|receptionist|billing|coder|scribe|social worker|dietitian|nutritionist|"
    r"genetic counselor|research assistant|research associate|lab(?:oratory)? (?:manager|tech|assistant|scientist)|"
    r"data (?:manager|analyst|scientist|engineer)|sales|account manager|territory|"
    r"post-?doc|postdoctoral|fellowship program|fellow(?:ship)?\b(?!.*(?:trained|-trained))|resident|"
    r"veterinar|dental|dentist|radiation therapist|dosimetrist|physicist|\bCRA\b|clinical research (?:coordinator|associate)|"
    r"intern\b|student|specialist(?! physician)|administrative assistant|executive assistant|"
    r"medical science liaison|\bMSL\b|marketing|\bmanager\b|supervisor|operations|business|"
    r"research professional|research (?:manager|specialist|scientist|associate|technician)|implementation scientist|"
    r"safety officer|informatic|radiochem|therapist|nursing|andrology|small animal|core\b|"
    r"biostatistic|statistician|writer|engineer|software|IT\b|analyst|paralegal|counsel\b|attorney)\b",
    re.I,
)
# "PA" is ambiguous (physician assistant vs. Pennsylvania): only treat it as the role
# when it is not preceded by a comma and is followed by a dash/slash or role-ish word.
PA_TITLE_RE = re.compile(r"(?<!,)(?<!,\s)\bPA\s*(?:[-–/](?!C)|\s(?:needed|job|opportunit|position|locum))|\b(?:NP|APP)\s*/\s*PA\b", re.I)

PHYSICIAN_HINT_RE = re.compile(
    r"\b(physician|\bMD\b|\bM\.D\.|D\.?O\.?\b|doctor|hematologist|oncologist|medical director|"
    r"professor|faculty|attending|clinician|chief|chair|BC/BE|board[- ]certified|board[- ]eligible)\b",
    re.I,
)


OTHER_SPECIALTY_TITLE_RE = re.compile(
    r"radiation oncolog|surgical oncolog|gynecolog(?:ic|y) oncolog|gyn[- ]onc|urolog|orthop|neurosurg|"
    r"dermatolog|patholog|radiolog|nuclear medicine|interventional|anesthesi|psychiatr|psycho-?oncolog|"
    r"ophthalm|otolaryng|\bENT\b|plastic|thoracic surg|colorectal surg|breast surg|surgeon|"
    r"oncology pharmac|genetic|hospice|nephrolog|cardiolog|cardio-?oncolog|pulmonolog|gastroenterolog|hepatolog|"
    r"rheumatolog|endocrinolog|infectious|hospitalist|internal medicine(?!.*(?:hematolog|oncolog))|primary care|family medicine|"
    r"emergency|urgent care|exercise|physical medicine|rehabilitation|physiatr|"
    r"\bOB/?GYN\b|obstetric|neonat|adolescent|epilept|neurolog|imaging|brachytherapy|hospital medicine|"
    r"critical care|transfusion|laboratory-based|blood research|eating disorder|quality and safety|"
    r"radiation services|maxillofacial|developmental pediatric|geriatric|sleep medicine|allergy|"
    r"chief medical research officer|research officer|vice chair, brach|colon (?:&|and) rectal|"
    r"regional medical director(?!.*oncolog)|head (?:&|and) neck surg|motility|^palliative|palliative care physician|"
    r"physician leader|staff physicians\b|"
    r"project scientist|medical physic|basic science|cancer biology|stem cell research center|department of surg|"
    r"integrative medicine|functional medicine|theranostic|antibody therapeutics|"
    r"biostatist|epidemiolog|computational|bioinformatic|immunolog(?!.*hematolog)|\bPhD\b(?!.*\bMD\b)",
    re.I,
)


def is_relevant(title: str, text: str, *, require_physician_hint: bool = False) -> bool:
    """Physician-level hematology / medical-oncology job?

    For industry postings (require_physician_hint=True) the boilerplate almost
    always mentions "oncology" somewhere, so we additionally demand that the
    heme/onc terms appear in the title or repeatedly in the body.
    """
    blob = f"{title}\n{text[:3000]}"
    if not HEME_ONC_RE.search(blob):
        return False
    if NON_PHYSICIAN_TITLE_RE.search(title) or PA_TITLE_RE.search(title) or OTHER_SPECIALTY_TITLE_RE.search(title):
        return False
    if require_physician_hint:
        if not PHYSICIAN_HINT_RE.search(blob):
            return False
        if not HEME_ONC_RE.search(title) and len(HEME_ONC_RE.findall(text)) < 4:
            return False
    elif not HEME_ONC_RE.search(title) and len(HEME_ONC_RE.findall(text)) < 3:
        return False
    return True


# --------------------------------------------------------------------------
# MD requirement
# --------------------------------------------------------------------------
MD_RE = re.compile(
    r"\b(M\.?D\.?|D\.?O\.?|MD/DO|MD or DO|medical degree|doctor of medicine|physician|"
    r"board[- ]?(?:certified|eligible)|BC/BE|BE/BC|ABIM|fellowship[- ]trained|"
    r"medical license|licensed to practice medicine)\b",
    re.I,
)
MD_OR_PHD_RE = re.compile(r"\b(MD|M\.D\.)\s*(?:/|or|and/or)\s*(PhD|Ph\.D\.|PharmD)\b", re.I)


def md_required(title: str, text: str) -> dict:
    """Returns {'required': bool|None, 'note': str}."""
    blob = f"{title}\n{text}"
    if MD_OR_PHD_RE.search(blob) and not re.search(r"\bBC/BE|board[- ]?(certified|eligible)\b", blob, re.I):
        return {"required": None, "note": "MD or PhD accepted"}
    if MD_RE.search(blob):
        return {"required": True, "note": "MD/DO or board certification referenced"}
    return {"required": None, "note": "not stated"}


# --------------------------------------------------------------------------
# Job type
# --------------------------------------------------------------------------
_ACADEMIC = [
    (r"\b(assistant|associate|full)?\s*professor\b", 4), (r"\bfaculty\b", 3), (r"\buniversity\b", 2),
    (r"school of medicine|college of medicine|medical school", 3), (r"\btenure", 3),
    (r"academic", 2), (r"\bNCI[- ]designated\b", 2), (r"comprehensive cancer center", 1),
    (r"\bresearch\b.*\b(protected|time|effort)\b", 1), (r"\bteaching\b", 1), (r"\bfellows?\b|residents?\b", 1),
    (r"\bdivision of hematology", 2), (r"\bin[- ]residence\b|clinical x\b|HS clinical|health sciences clinical", 4),
]
_COMMUNITY = [
    (r"community(?:-based)? (?:practice|oncology|hospital|cancer)", 4), (r"private practice", 4),
    (r"physician[- ]owned|physician[- ]led", 3), (r"\bpartnership(?: track)?\b", 3),
    (r"medical group|health system|regional medical center|community hospital", 2),
    (r"\bwRVU|productivity", 2), (r"sign[- ]on bonus", 1), (r"\bcall\b.*\b1:\d", 1),
    (r"\bUS Oncology|OneOncology|American Oncology Network|Texas Oncology|Florida Cancer Specialists|"
     r"Rocky Mountain Cancer|Minnesota Oncology|New York Cancer|Virginia Cancer|Tennessee Oncology|"
     r"Maryland Oncology|Illinois Cancer|Arizona Oncology|Willamette Valley|Northwest Medical|"
     r"Kaiser|Sutter|Sharp|Scripps|Dignity|CommonSpirit|Providence|Adventist|Optum|Epic Care|"
     r"Pacific Cancer|Cancer Care Associates|Oncology Associates|Hematology[- ]Oncology Associates", 4),
    (r"employed position|hospital[- ]employed", 3), (r"\bclinic\b", 1),
    (r"cancer network|cancer (?:care|center)s? (?:of|associates|specialists)|cancer (?:&|and) blood|blood (?:&|and) cancer|"
     r"(?:oncology|hematology)[- /]?(?:oncology )?(?:associates|group|partners|specialists|consultants|medical group)|"
     r"medical oncology associates|starling oncology", 4),
    (r"\b(Jackson Physician Search|Merritt Hawkins|Enterprise Medical|Britt Medical|Pinnacle Health Group|"
     r"Physician Affiliate Group|Curative Talent|Pacific Companies|Palm Health Resources|Fidelis Partners)\b", 2),
]
_INDUSTRY = [
    (r"\b(pharma|pharmaceutical|biotech|biopharma)\b", 4), (r"clinical development", 3),
    (r"medical director|senior medical director|executive medical director|VP,? medical|chief medical officer", 2),
    (r"drug safety|pharmacovigilance|medical affairs|medical monitor|clinical scientist", 3),
    (r"\b(Amgen|Gilead|Kite|Genentech|Roche|Pfizer|Merck|AbbVie|BMS|Bristol[- ]Myers|Novartis|AstraZeneca|"
     r"Lilly|Johnson & Johnson|Janssen|Regeneron|Moderna|Seagen|Daiichi|Takeda|Sanofi|GSK|Bayer|"
     r"BeiGene|Incyte|Jazz|Exelixis|Guardant|Grail|Tempus|Natera|Foundation Medicine|Arcus|Nektar|"
     r"Revolution Medicines|Iovance|Allogene|Arcellx|Legend|Sana|Vir|Nurix|Kura|Syndax|Autolus|"
     r"Adaptive Biotechnologies|Flatiron|IQVIA|Parexel|ICON|Syneos|Medpace|PPD|Labcorp)\b", 5),
    (r"\bIND\b|\bNDA\b|\bBLA\b|\bFDA\b", 2), (r"phase (?:1|2|3|I|II|III)\b.*trial", 1),
    (r"\bremote\b", 1), (r"\bGCP\b|\bICH\b", 2), (r"study (?:physician|director)", 3),
]
_GOVERNMENT = [
    (r"\bVA\b|Veterans? (?:Affairs|Health|Administration)|\bVAMC\b|\bVACHCS\b|\bVACCHCS\b", 5),
    (r"\bNIH\b|National Cancer Institute|\bNCI\b(?! designated)", 3), (r"federal (?:employee|position|government)", 3),
    (r"Indian Health Service|\bIHS\b|military|\bArmy\b|\bNavy\b|Air Force|Department of Defense|\bDoD\b", 4),
    (r"\bGS-1[0-5]\b", 5), (r"USAJobs", 5),
]
_LOCUMS = [
    (r"\blocum", 6), (r"\bper diem\b", 3), (r"temporary (?:coverage|assignment)", 3), (r"\bTravel(?:ing)? physician\b", 3),
    (r"\b(Barton Associates|CompHealth|Weatherby|LocumTenens\.com|Medicus|Hayes Locums|AMN Healthcare|Jackson \+ Coker|"
     r"Jackson & Coker|Aya Locums|Interim Physicians|Consilium|Vista Staffing|All Star Recruiting|Alumni Healthcare|"
     r"Onyx MD|MPLT|Curative|Integrity Locums|Wapiti|StaffMed)\b", 6),
]


def _score(patterns, blob: str) -> int:
    return sum(w for p, w in patterns if re.search(p, blob, re.I))


def classify_job_type(title: str, employer: str, text: str) -> dict:
    """Returns {'type': str, 'confidence': float, 'scores': {...}}."""
    head = f"{title}\n{employer}\n{text[:2500]}"
    body = text
    scores = {
        "academic": _score(_ACADEMIC, head) * 2 + _score(_ACADEMIC, body),
        "community": _score(_COMMUNITY, head) * 2 + _score(_COMMUNITY, body),
        "industry": _score(_INDUSTRY, head) * 2 + _score(_INDUSTRY, body),
        "government": _score(_GOVERNMENT, head) * 2 + _score(_GOVERNMENT, body),
        "locums": _score(_LOCUMS, head) * 2 + _score(_LOCUMS, body),
    }
    # Locums and government are decisive when they hit the title/employer.
    if re.search(r"\blocum|\b(Barton Associates|CompHealth|Weatherby|LocumTenens\.com|Medicus|Hayes Locums)\b", f"{title} {employer}", re.I):
        return {"type": "locums", "confidence": 0.95, "scores": scores}
    if re.search(r"\bVA\b|Veterans", f"{title} {employer}", re.I):
        return {"type": "government", "confidence": 0.9, "scores": scores}
    best = max(scores, key=scores.get)
    total = sum(scores.values()) or 1
    conf = scores[best] / total
    if scores[best] == 0:
        return {"type": "unknown", "confidence": 0.0, "scores": scores}
    return {"type": best, "confidence": round(conf, 2), "scores": scores}


# --------------------------------------------------------------------------
# Salary
# --------------------------------------------------------------------------
_MONEY = r"\$\s?(\d{1,3}(?:,\d{3})+|\d{3,7})(?:\.\d+)?\s*(k|K|thousand)?"
_RANGE_RE = re.compile(_MONEY + r"\s*(?:-|–|—|to|and)\s*" + _MONEY, re.I)
_SINGLE_RE = re.compile(_MONEY, re.I)
_PERIOD_RE = re.compile(r"(per|/|an?)\s*(hour|hr|day|week|month|year|yr|annum)|annual(?:ly)?|yearly|hourly|daily", re.I)
_SALARY_CONTEXT_RE = re.compile(
    r"(salary|compensation|pay|base|guarantee|earning|income|package|range|rate|\bAPU\b|scale|\$)",
    re.I,
)


def _to_num(num: str, k: str | None) -> float:
    v = float(num.replace(",", ""))
    if k:
        v *= 1000
    return v


def _plausible_annual(v: float) -> bool:
    return 90_000 <= v <= 1_600_000


def _plausible_hourly(v: float) -> bool:
    # Physician hourly rates; "$7.25 - $999.99" style compliance placeholders fail this.
    return 60 <= v <= 750


_TITLE_SALARY_RE = re.compile(r"\$?\s?(\d{3})\s?K\b\s*(?:\+\s*)?(base|salary|guarantee[d]?)", re.I)


def parse_salary(text: str, salary_field: str | None = None, title: str | None = None) -> dict | None:
    """Find an annual physician salary (or range). Returns dict or None.

    dict: {min, max, period:'year', text, disclosed: bool}
    Recruiter titles like "626K Base | 75K Recruitment" are the most reliable
    statement of base pay, so they win when present.
    """
    if title:
        m = _TITLE_SALARY_RE.search(title)
        if m:
            v = int(m.group(1)) * 1000
            if _plausible_annual(v):
                return {"min": v, "max": None, "period": "year", "text": title, "disclosed": True, "annualized_from": None}
    candidates: list[tuple[float, float | None, str]] = []
    for src in [salary_field or "", text]:
        for m in _RANGE_RE.finditer(src):
            lo, hi = _to_num(m.group(1), m.group(2)), _to_num(m.group(3), m.group(4))
            ctx = src[max(0, m.start() - 80): m.end() + 60]
            candidates.append((lo, hi, ctx))
        for m in _SINGLE_RE.finditer(src):
            v = _to_num(m.group(1), m.group(2))
            ctx = src[max(0, m.start() - 80): m.end() + 60]
            candidates.append((v, None, ctx))

    best = None
    for lo, hi, ctx in candidates:
        period = "year"
        pm = _PERIOD_RE.search(ctx)
        if pm:
            unit = (pm.group(2) or pm.group(0)).lower()
            if "hour" in unit or "hr" in unit:
                if not _plausible_hourly(lo) or (hi and not _plausible_hourly(hi)):
                    continue
                lo, hi, period = lo * 2080, (hi * 2080 if hi else None), "hour"
            elif "day" in unit:
                lo, hi, period = lo * 220, (hi * 220 if hi else None), "day"
            elif "week" in unit:
                lo, hi, period = lo * 48, (hi * 48 if hi else None), "week"
            elif "month" in unit:
                lo, hi, period = lo * 12, (hi * 12 if hi else None), "month"
        if not _plausible_annual(lo) or (hi and not _plausible_annual(hi)):
            continue
        if hi and hi < lo:
            lo, hi = hi, lo
        # Skip things that are obviously bonuses / loan repayment rather than base pay.
        if re.search(r"(sign[- ]?on|bonus|loan|relocation|stipend|CME|retention|forgiveness|student)", ctx, re.I) \
                and not re.search(r"(salary|base|compensation|earning|guarantee)", ctx, re.I):
            continue
        cand = {
            "min": int(lo), "max": int(hi) if hi else None, "period": period,
            "text": re.sub(r"\s+", " ", ctx).strip(), "disclosed": True,
            "annualized_from": period if period != "year" else None,
        }
        # Prefer ranges, then salary-context matches, then the first plausible number.
        score = (1 if hi else 0) + (1 if _SALARY_CONTEXT_RE.search(ctx) else 0)
        if best is None or score > best[0]:
            best = (score, cand)
    return best[1] if best else None


# --------------------------------------------------------------------------
# Effort split (clinical / research / admin / teaching)
# --------------------------------------------------------------------------
_PCT_RE = re.compile(
    r"(\d{1,3})\s*(?:%|percent)\s*(?:of\s+)?(?:time\s+|effort\s+|FTE\s+)?(?:(?:for|to|in|on|toward|towards|dedicated to|protected(?: for)?|devoted to)\s+)?"
    r"(clinical|clinic|patient care|research|protected|academic|scholarly|admin(?:istrative)?|teaching|education|non-?clinical)",
    re.I,
)
_PCT_RE_REV = re.compile(
    r"(clinical|clinic|patient care|research|protected|academic|scholarly|admin(?:istrative)?|teaching|education|non-?clinical)"
    r"(?:\s+\w+){0,4}?\s*(?:\(|:|of|at|is|=|-|–)?\s*(\d{1,3})\s*(?:%|percent)",
    re.I,
)
_RANGE_PCT_RE = re.compile(
    r"(\d{1,3})\s*(?:-|–|to)\s*(\d{1,3})\s*(?:%|percent)\s*(?:effort\s+|time\s+)?(?:(?:for|to|in|on|toward|towards|dedicated to|protected(?: for)?)\s+)?"
    r"(clinical|clinic|patient care|research|protected|academic|scholarly|admin(?:istrative)?|teaching|education)",
    re.I,
)
_DAYS_RE = re.compile(
    r"(\d(?:\.\d)?|one|two|three|four|five)\s*(?:half[- ])?days?\s*(?:per|a|/|each)?\s*week\s*(?:of|in|for)?\s*(clinic|clinical|research|admin|protected)",
    re.I,
)
_PROTECTED_RE = re.compile(r"protected\s+(?:research\s+|academic\s+|non-?clinical\s+)?time", re.I)
_WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


def _bucket(label: str) -> str:
    label = label.lower()
    if label.startswith(("clinic", "patient")):
        return "clinical"
    if label.startswith(("research", "protected", "academic", "scholar")):
        return "research"
    if label.startswith("admin"):
        return "admin"
    if label.startswith(("teach", "educ")):
        return "teaching"
    if label.startswith("non"):
        return "nonclinical"
    return label


def parse_effort(text: str) -> dict:
    """Returns {clinical, research, admin, teaching (pct or None), protected_time: bool, text: snippet|None}."""
    out = {"clinical": None, "research": None, "admin": None, "teaching": None,
           "protected_time": bool(_PROTECTED_RE.search(text)), "text": None}
    snippets = []

    def _set(bucket, val, snippet):
        if bucket == "nonclinical":
            if out["clinical"] is None:
                out["clinical"] = max(0, 100 - val)
            snippets.append(snippet)
            return
        if bucket in out and out[bucket] is None and 0 < val <= 100:
            out[bucket] = val
            snippets.append(snippet)

    for m in _RANGE_PCT_RE.finditer(text):
        lo, hi = int(m.group(1)), int(m.group(2))
        _set(_bucket(m.group(3)), round((lo + hi) / 2), text[max(0, m.start() - 40): m.end() + 40])
    for m in _PCT_RE.finditer(text):
        _set(_bucket(m.group(2)), int(m.group(1)), text[max(0, m.start() - 40): m.end() + 40])
    for m in _PCT_RE_REV.finditer(text):
        _set(_bucket(m.group(1)), int(m.group(2)), text[max(0, m.start() - 40): m.end() + 40])
    for m in _DAYS_RE.finditer(text):
        n = m.group(1).lower()
        days = _WORDNUM.get(n) or float(n)
        _set(_bucket(m.group(2)), round(days / 5 * 100), text[max(0, m.start() - 40): m.end() + 40])

    # Fill the complement when exactly one side is stated.
    if out["clinical"] is not None and out["research"] is None and out["admin"] is None and out["teaching"] is None:
        pass  # leave: 100 - clinical could be research OR admin; don't guess
    if out["clinical"] is None and out["research"] is not None and out["admin"] is None and out["teaching"] is None:
        out["clinical"] = 100 - out["research"]

    if snippets:
        out["text"] = " … ".join(re.sub(r"\s+", " ", s).strip() for s in snippets[:3])
    return out


# --------------------------------------------------------------------------
# Benefits
# --------------------------------------------------------------------------
BENEFIT_PATTERNS = [
    ("sign_on_bonus", r"sign[- ]?(?:on|ing) bonus|signing bonus|commencement bonus"),
    ("relocation", r"relocation (?:assistance|package|bonus|allowance|reimbursement|expenses)|paid relocation"),
    ("loan_repayment", r"loan (?:repayment|forgiveness|assistance)|student (?:loan|debt)|\bPSLF\b|educational debt"),
    ("cme", r"\bCME\b|continuing medical education"),
    ("malpractice", r"malpractice|tail coverage|professional liability"),
    ("retirement", r"\b401\(?k\)?|\b403\(?b\)?|\b457\(?b\)?|pension|retirement (?:plan|match|contribution)|UCRP"),
    ("pto", r"\bPTO\b|paid time off|vacation|weeks? off"),
    ("health_insurance", r"health(?:care)? (?:insurance|benefits|coverage)|medical,? dental,? (?:and |&)?vision|dental|vision insurance"),
    ("partnership_track", r"partnership(?: track| opportunity| eligib| potential| after)|path(?:way)? to partner(?:ship)?|become a partner|partner-track"),
    ("productivity_bonus", r"\bwRVU|productivity(?:-based)? (?:bonus|incentive|compensation|model)|incentive (?:bonus|compensation)|quality (?:bonus|incentive)"),
    ("visa_sponsorship", r"\bJ-?1\b|\bH-?1B\b|visa (?:sponsorship|support)|waiver"),
    ("retention_bonus", r"retention bonus|quality bonus|stipend"),
    ("equity", r"stock options|equity (?:award|grant|compensation|package)|\bRSUs?\b|employee stock|restricted stock"),
    ("housing", r"housing (?:assistance|allowance|stipend)|mortgage (?:assistance|program)|home loan"),
    ("no_call", r"no (?:call|weekend|nights?)|light call|limited call|1:\d\s*call|call (?:schedule )?(?:of )?1:\d"),
    ("four_day_week", r"4[- ]day (?:work )?week|four[- ]day (?:work )?week|3\.5 days"),
    ("research_support", r"start[- ]?up (?:package|funds|funding)|research (?:support|funding|start-?up)|lab space"),
    ("disability_life", r"disability insurance|life insurance"),
]
_BENEFIT_RES = [(k, re.compile(p, re.I)) for k, p in BENEFIT_PATTERNS]
_BONUS_AMT_RE = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})+|\d{2,6})\s*(k|K)?[^.\n]{0,60}?(sign[- ]?on|signing|bonus|relocation|loan|retention)|"
                           r"(sign[- ]?on|signing|relocation|loan (?:repayment|forgiveness)|retention)[^.\n]{0,60}?\$\s?(\d{1,3}(?:,\d{3})+|\d{2,6})\s*(k|K)?", re.I)


def extract_benefits(text: str) -> dict:
    """Returns {'tags': [...], 'snippets': {tag: snippet}, 'amounts': {tag: int}}."""
    tags, snippets, amounts = [], {}, {}
    for tag, rx in _BENEFIT_RES:
        m = rx.search(text)
        if m:
            tags.append(tag)
            snippets[tag] = re.sub(r"\s+", " ", text[max(0, m.start() - 60): m.end() + 80]).strip()
    for m in _BONUS_AMT_RE.finditer(text):
        if m.group(1):
            amt, k, kind = m.group(1), m.group(2), m.group(3)
        else:
            kind, amt, k = m.group(4), m.group(5), m.group(6)
        v = _to_num(amt, k)
        if 1_000 <= v <= 500_000:
            key = "sign_on_bonus" if re.search(r"sign|bonus", kind, re.I) else \
                  "relocation" if "reloc" in kind.lower() else \
                  "loan_repayment" if "loan" in kind.lower() else "retention_bonus"
            amounts.setdefault(key, int(v))
    return {"tags": tags, "snippets": snippets, "amounts": amounts}


# --------------------------------------------------------------------------
# Subspecialty tags
# --------------------------------------------------------------------------
SUBSPECIALTY_PATTERNS = [
    ("malignant_heme", r"malignant hematolog|leukemia|lymphoma|myeloma|\bMDS\b|myeloproliferative|\bMPN\b|hematologic malignanc"),
    ("classical_heme", r"classical hematolog|benign hematolog|non-?malignant hematolog|thrombosis|hemostasis|sickle cell|hemophilia|bleeding disorder|anemia"),
    ("bmt_cell_therapy", r"bone marrow transplant|stem cell transplant|\bBMT\b|\bHCT\b|\bHSCT\b|cell(?:ular)? therapy|CAR[- ]?T"),
    ("solid_tumor", r"solid tumor|medical oncolog"),
    ("breast", r"\bbreast\b"),
    ("gi", r"\bGI\b|gastrointestinal|colorectal|pancrea|hepatobiliary|\bHCC\b"),
    ("thoracic", r"thoracic|\blung\b"),
    ("gu", r"\bGU\b|genitourinary|prostate|bladder|kidney cancer|renal cell|testicular"),
    ("gyn", r"gynecolog|ovarian|cervical|endometrial"),
    ("head_neck", r"head (?:and|&) neck"),
    ("neuro_onc", r"neuro-?oncolog|glioma|glioblastoma|brain tumor"),
    ("sarcoma", r"sarcoma"),
    ("melanoma_skin", r"melanoma|skin cancer|cutaneous"),
    ("phase1_drug_dev", r"phase (?:1|I)\b|early[- ]phase|drug development|developmental therapeutics|experimental therapeutics"),
    ("pediatric", r"pediatric|children'?s"),
    ("palliative", r"palliative|supportive care|hospice"),
    ("general", r"general hematology[/ ]oncology|general heme|both hematology and oncology|hematology and medical oncology|hematology/oncology"),
]
_SUB_RES = [(k, re.compile(p, re.I)) for k, p in SUBSPECIALTY_PATTERNS]


def subspecialties(title: str, text: str) -> list[str]:
    blob = f"{title}\n{text}"
    hits = [k for k, rx in _SUB_RES if rx.search(blob)]
    title_hits = [k for k, rx in _SUB_RES if rx.search(title)]
    # Title matches first, then body matches; cap to keep tags readable.
    ordered = title_hits + [h for h in hits if h not in title_hits]
    return ordered[:6]


# --------------------------------------------------------------------------
# Misc flags
# --------------------------------------------------------------------------
def rank(title: str, text: str) -> str | None:
    m = re.search(r"\b(assistant|associate|full)\s+(?:clinical\s+)?professor", f"{title} {text[:1500]}", re.I)
    if m:
        return m.group(1).lower() + "_professor"
    if re.search(r"\b(chief|chair|director|head)\b", title, re.I):
        return "leadership"
    return None


def remote_flag(title: str, text: str, location: str | None) -> bool:
    return bool(re.search(r"\bremote\b", f"{title} {location or ''} {text[:800]}", re.I))
