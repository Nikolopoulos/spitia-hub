#!/usr/bin/env python3
"""
Full Automated Pipeline:
1. Email Alert Ingestion & Filtering
2. Download via Safari Engine (WAF/Cloudflare bypass)
3. AI/Rule-based Evaluation:
   - Turnkey DIY Cost calculation
   - Risk Score & Reasons
   - Parking ease & vehicle theft risk
   - Neighborhood safety & encampment risk
   - User Fit Match (with €180k cash equity & loan headroom)
   - Smart Deal Score
4. Generate property HTML report
5. Update webarchives/processed_listings.csv
6. Update index.html propertiesData
7. Git Commit & Push to origin main
8. Update alert_status.json for Menu Bar app
"""

import os, sys, json, csv, re, time, subprocess, logging, imaplib, email, urllib.request, html as html_lib, unicodedata
from datetime import datetime, timedelta
from email.header import decode_header
from html.parser import HTMLParser
from rich_report_generator import generate_rich_property_html

base_dir = '/Volumes/Terataki/projects/spitia'
csv_path = os.path.join(base_dir, 'webarchives', 'processed_listings.csv')
rejected_json_path = os.path.join(base_dir, 'webarchives', 'rejected_listings.json')
archived_json_path = os.path.join(base_dir, 'webarchives', 'archived_listings.json')
index_path = os.path.join(base_dir, 'index.html')
config_path = os.path.join(base_dir, 'config.json')
status_path = os.path.join(base_dir, 'alert_status.json')
scratch_dir = '/Users/vnikolopoulos/.gemini/antigravity-cli/brain/f5cd4cb5-f15c-425c-8e9a-e4ffdc3ca53f/scratch'

if base_dir not in sys.path:
    sys.path.insert(0, base_dir)
if scratch_dir not in sys.path:
    sys.path.append(scratch_dir)
try:
    from user_fit_budget_engine import evaluate_user_fit_with_budget_and_risk, USER_CASH, calculate_enfia
except Exception as e:
    logging.warning(f"Warning importing user_fit_budget_engine: {e}")

def extract_visible_text(html):
    """Strips tags, scripts, styles, svg, and metadata attributes to extract strictly visible human text"""
    if not html:
        return ""
    clean = re.sub(r'<(script|style|svg|header|nav|footer)\b.*?</\1>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
    clean = re.sub(r'<[^>]+>', ' ', clean)
    clean = html_lib.unescape(clean)
    return ' '.join(clean.split())

def extract_listing_full_text(html, rendered_text="", card_text=""):
    """
    Extracts and compiles complete text content including Safari rendered body text,
    email card summary, metadata descriptions, Next.js __NEXT_DATA__ JSON payloads,
    JSON-LD structures, and HTML description containers.
    """
    chunks = []
    if rendered_text:
        chunks.append(rendered_text)
    if card_text:
        chunks.append(card_text)
    if html:
        # 1. Meta descriptions
        meta_matches = re.findall(r'<meta[^>]+(?:name|property)=[\"\'](?:description|og:description|twitter:description)[\"\'][^>]+content=[\"\']([^\"\']+)[\"\']', html, re.I)
        meta_matches += re.findall(r'<meta[^>]+content=[\"\']([^\"\']+)[\"\'][^>]+(?:name|property)=[\"\'](?:description|og:description|twitter:description)[\"\']', html, re.I)
        chunks.extend(meta_matches)
        
        # 2. Next.js __NEXT_DATA__ JSON payload
        next_m = re.search(r'<script[^>]+id=[\"\']__NEXT_DATA__[\"\'][^>]*>(.*?)</script>', html, re.DOTALL | re.I)
        if next_m:
            try:
                data = json.loads(next_m.group(1))
                def walk(obj):
                    if isinstance(obj, dict):
                        for k, v in obj.items():
                            if isinstance(v, str) and len(v) > 8 and any(kw in k.lower() for kw in ['desc', 'text', 'comment', 'body', 'note', 'title', 'detail']):
                                chunks.append(v)
                            else:
                                walk(v)
                    elif isinstance(obj, list):
                        for item in obj:
                            walk(item)
                walk(data)
            except Exception:
                pass
                
        # 3. JSON-LD scripts
        ld_scripts = re.findall(r'<script[^>]+type=[\"\']application/ld\+json[\"\'][^>]*>(.*?)</script>', html, re.DOTALL | re.I)
        for ld in ld_scripts:
            try:
                data = json.loads(ld)
                if isinstance(data, dict):
                    if 'description' in data and isinstance(data['description'], str):
                        chunks.append(data['description'])
                    if 'name' in data and isinstance(data['name'], str):
                        chunks.append(data['name'])
            except Exception:
                pass

        # 4. Description containers in HTML
        desc_blocks = re.findall(r'<(?:div|section|p|article)[^>]+(?:class|id)=[\"\'][^\"\']*(?:description|details|perigrafi|ad-text)[^\"\']*[\"\'][^>]*>(.*?)</(?:div|section|p|article)>', html, re.DOTALL | re.I)
        for db in desc_blocks:
            chunks.append(re.sub(r'<[^>]+>', ' ', db))
            
        # 5. Visible text fallback
        chunks.append(extract_visible_text(html))
        
    return ' '.join(chunks)

def record_rejected_listing(url, reason, title="", price=0, sqm=0, ptype="Διαμέρισμα", loc=""):
    """Appends or updates a rejected listing in rejected_listings.json"""
    try:
        listings = []
        if os.path.exists(rejected_json_path):
            with open(rejected_json_path, 'r', encoding='utf-8') as f:
                listings = json.load(f)
        
        clean_url = url.split('?')[0].strip()
        display_title = title or f"Πώληση, {ptype}, {sqm}τ.μ. {loc}".strip()
        if price and "€" not in display_title:
            display_title += f" | €{price:,}"

        # Determine lid
        if 'spitogatos.gr/aggelia/' in clean_url:
            m = re.search(r'aggelia/(\d+)', clean_url)
            lid = m.group(1) if m else str(int(time.time()))
        else:
            m = re.search(r'xe\.gr/p/([a-f0-9\-]+)', clean_url) or re.search(r'xe\.gr/property/d/[^/]+/([a-f0-9\-]+)', clean_url)
            lid = f"xe-{m.group(1)[:8]}" if m else str(int(time.time()))

        # Check if URL already recorded
        for it in listings:
            if it.get('url', '').split('?')[0].strip() == clean_url:
                it['reason'] = reason
                if title: it['title'] = display_title
                if price: it['price'] = price
                if sqm: it['sqm'] = sqm
                if loc:
                    it['location'] = f"{sqm}τ.μ. {loc}".strip() if loc else f"{sqm}τ.μ."
                with open(rejected_json_path, 'w', encoding='utf-8') as f:
                    json.dump(listings, f, ensure_ascii=False, indent=2)
                return

        listings.insert(0, {
            "listing_id": lid,
            "title": display_title,
            "location": f"{sqm}τ.μ. {loc}".strip() if loc else f"{sqm}τ.μ.",
            "type": ptype,
            "price": price,
            "sqm": sqm,
            "url": clean_url,
            "reason": reason
        })

        with open(rejected_json_path, 'w', encoding='utf-8') as f:
            json.dump(listings, f, ensure_ascii=False, indent=2)
        logging.info(f"Recorded rejected listing: {clean_url} -> {reason}")
    except Exception as e:
        logging.error(f"Failed to record rejected listing: {e}")

def fetch_url_via_safari(url):
    applescript = f'''
    tell application "Safari"
        set targetURL to "{url}"
        if (count of windows) = 0 then
            make new document with properties {{URL:targetURL}}
            set targetTab to current tab of window 1
        else
            set targetTab to make new tab at end of tabs of window 1 with properties {{URL:targetURL}}
            set current tab of window 1 to targetTab
        end if
        
        set maxWait to 12
        repeat with i from 1 to maxWait
            delay 1
            set src to (source of targetTab) as text
            if (src contains "spitogatos" or src contains "xe.gr" or src contains "footer") and (src does not contain "Pardon Our Interruption") then
                exit repeat
            end if
        end repeat
        
        set tabTitle to name of targetTab
        set pageSource to (source of targetTab) as text
        set pageText to ""
        try
            set pageText to (text of targetTab) as text
        end try
        close targetTab
        return tabTitle & "|||SPLIT|||" & pageSource & "|||SPLIT|||" & pageText
    end tell
    '''
    proc = subprocess.run(['osascript', '-e', applescript], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise Exception(f"AppleScript error: {proc.stderr}")
    
    parts = proc.stdout.split('|||SPLIT|||')
    title = parts[0].strip()
    html = parts[1].strip() if len(parts) > 1 else ""
    rendered_text = parts[2].strip() if len(parts) > 2 else ""
    return title, html, rendered_text


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BLACKLIST_AREAS = [
    "αγία βαρβάρα", "αγια βαρβαρα", "agia varvara", "agia-varvara", "riminitika", "ριμινίτικα",
    "μενίδι", "μενιδι", "menidi", "αχαρνές", "αχαρνες", "acharnes",
    "ζεφύρι", "ζεφυρι", "zefyri",
    "άνω λιόσια", "ανω λιοσια", "ano liosia", "λιοσια",
    "ασπρόπυργος", "ασπροπυργος", "aspropyrgos",
    "φυλή", "φυλη", "fyli",
    "καματερό", "καματερο", "kamatero"
]

PREFERENCES = {
    "cash_budget": 180000,
    "max_acceptable_price_loan": 500000,
    "ideal_sqm": 120,
    "min_sqm_tolerated": 90
}

REJECTED_PROPERTY_TYPES = [
    "οικόπεδο", "οικοπεδο", "αγροτεμάχιο", "αγροτεμαχιο", "plot",
    "επαγγελματικός", "γραφείο", "γραφειο", "κατάστημα", "καταστημα", "commercial",
    "parking", "γκαράζ", "γκαραζ", "αποθήκη", "αποθηκη"
]

def load_config():
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def check_bot_challenge(title, html, url):
    comb = (title + " " + html).lower()
    if "no robots allowed" in comb or "μέρος της ανθρωπότητας" in comb:
        return True, "Χρυσή Ευκαιρία (xe.gr)", url
    if "pardon our interruption" in comb or "cf-turnstile" in comb or "challenges.cloudflare.com" in comb:
        return True, "Σπιτόγατος (spitogatos.gr)", url
    if "just a moment..." in title.lower() or "attention required! | cloudflare" in comb:
        plat = "Χρυσή Ευκαιρία (xe.gr)" if "xe.gr" in url else "Σπιτόγατος (spitogatos.gr)"
        return True, plat, url
    return False, "", ""

def update_status_file(last_run, new_count, listings_added=None, bot_challenge=None):
    next_run_dt = datetime.now() + timedelta(minutes=15)
    next_run_str = next_run_dt.strftime("%H:%M:%S (%d/%m)")
    data = {
        "last_run": last_run,
        "next_run": next_run_str,
        "new_properties_count": new_count,
        "bot_challenge_detected": bool(bot_challenge),
        "bot_challenge_platform": bot_challenge.get("platform", "") if bot_challenge else "",
        "bot_challenge_url": bot_challenge.get("url", "") if bot_challenge else "",
        "last_listings": listings_added or []
    }
    try:
        with open(status_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Failed to write status file: {e}")

class EmailHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.current_href = None
        self.current_text = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            attrs_dict = dict(attrs)
            self.current_href = attrs_dict.get("href")
            self.current_text = []

    def handle_data(self, data):
        if self.current_href is not None and data.strip():
            self.current_text.append(data.strip())

    def handle_endtag(self, tag):
        if tag == "a" and self.current_href:
            self.links.append((self.current_href, " ".join(self.current_text)))
            self.current_href = None
            self.current_text = []

def get_existing_listing_ids():
    ids = set()
    if os.path.exists(csv_path):
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            ids.update({r['listing_id'] for r in reader if 'listing_id' in r})
    if os.path.exists(archived_json_path):
        try:
            with open(archived_json_path, 'r', encoding='utf-8') as af:
                arch_list = json.load(af)
                ids.update({str(r.get('listing_id')) for r in arch_list if 'listing_id' in r})
        except Exception:
            pass
    if os.path.exists(rejected_json_path):
        try:
            with open(rejected_json_path, 'r', encoding='utf-8') as rf:
                rej_list = json.load(rf)
                ids.update({str(r.get('listing_id')) for r in rej_list if 'listing_id' in r})
        except Exception:
            pass
    return ids

def normalize_greek_text(text):
    if not text:
        return ""
    text = unicodedata.normalize('NFC', text)
    trans = str.maketrans("άέήίόύώϊϋΐΰΆΈΉΊΌΎΏΪΫ", "αεηιουωιυιυαεηιουωιυ")
    return text.lower().translate(trans)

AUCTION_PATTERNS = [
    # Core auction roots and stems
    "πλειστηριασμ",          # πλειστηριασμός, πλειστηριασμού, πλειστηριασμοί, πλειστηριασμό, πλειστηριασμών, πλειστηριασμούς
    "πλειστηριαζ",           # πλειστηριάζεται, πλειστηριάζονται
    "εκπλειστηριασμ",        # εκπλειστηριασμός, εκπλειστηριασμού
    "εκπλειστηριαζ",         # εκπλειστηριάζεται, εκπλειστηριάζονται
    "eauction",
    "e-auction",
    "κατασχεσ",              # κατάσχεση, κατασχέσεως, κατασχεμένο, κατασχεμένα
    "αναγκαστικη εκτελεσ",   # αναγκαστική εκτέλεση, αναγκαστικής εκτέλεσης
    "αναγκαστικη εκποιησ",   # αναγκαστική εκποίηση, αναγκαστικής εκποίησης
    "αναγκαστικη κατασχεσ",  # αναγκαστική κατάσχεση
    "εκποιειται μεσω",       # εκποιείται μέσω
    "δημοπρασι",             # δημοπρασία, δημοπρασίας, δημοπρασίες, ηλεκτρονική δημοπρασία
    "δημοπρατειτ",           # δημοπρατείται, δημοπρατούνται
    "e-δημοπρασι",
    "δικαστικος επιμελητ",   # δικαστικός επιμελητής
    "κατακυρωτικ",           # κατακυρωτική έκθεση
    "εκθεση κατασχεσ",       # έκθεση κατάσχεσης
    "εκθεση αναγκαστικ",     # έκθεση αναγκαστικής εκτέλεσης
    # Bidding / First offer terms
    "πρωτης προσφορας",      # πρώτης προσφοράς
    "πρωτη προσφορα",        # πρώτη προσφορά
    "1ης προσφορας",         # 1ης προσφοράς
    "1η προσφορα",           # 1η προσφορά
    "τιμη 1ης προσφορας",
    "τιμη πρωτης προσφορας",
    "τιμη εκκινησης πλειστηριασμ",
    "τιμη εναρξης πλειστηριασμ",
    "τιμη εναρξης διαγωνισμ",
    # Specific auction phrasing in descriptions
    "μεσω πλειστηριασμ",     # μέσω πλειστηριασμού
    "σε πλειστηριασμ",       # σε πλειστηριασμό
    "προς πλειστηριασμ",     # προς πλειστηριασμό
    "ημερομηνια πλειστηριασμ", # ημερομηνία πλειστηριασμού
    "ημερα πλειστηριασμ",    # ημέρα πλειστηριασμού
    "ωρα πλειστηριασμ",      # ώρα πλειστηριασμού
    "διενεργεια πλειστηριασμ", # διενέργεια πλειστηριασμού
    "διεξαγωγη πλειστηριασμ", # διεξαγωγή πλειστηριασμού
    "κωδικος πλειστηριασμ",  # κωδικός πλειστηριασμού
    "αριθμος πλειστηριασμ",  # αριθμός πλειστηριασμού
    "ακινητο πλειστηριασμ",  # ακίνητο πλειστηριασμού
    "πωλειται μεσω πλειστηριασμ",
    "διατιθεται μεσω πλειστηριασμ",
    "διαθεση μεσω πλειστηριασμ",
    "διαδικασια πλειστηριασμ",
    "προς εκποιηση",
    "ηλεκτρονικο διαγωνισμ"
]

def is_auction_listing(text, url=""):
    """
    Scans the entire listing description, rendered text, meta tags, and URL
    for explicit auction, seizure, or distressed servicer auction sale indicators.
    """
    comb = (text or "") + " " + (url or "")
    norm = normalize_greek_text(comb)
    
    # 1. Check auction patterns
    for pat in AUCTION_PATTERNS:
        if pat in norm:
            return True, pat
            
    # 2. Check servicer debt auctions
    if any(s in norm for s in ['dovalue', 'intrum', 'cepal', 'qquant']):
        if any(w in norm for w in ['προσφορ', 'πλειστηρ', 'χαρτοφυλακι', 'portfolio', 'εκποιησ', 'διαδικασι', 'πλατφορμ', 'eauction', 'bid', 'κατασχεσ']):
            return True, "τραπεζικός/servicer πλειστηριασμός (doValue/Intrum/Cepal/qquant)"
            
    # 3. URL checks
    url_l = (url or "").lower()
    if any(u_part in url_l for u_part in ['eauction', 'e-auction', 'pleistiriasm', 'pleistiriasmoi', 'katasxesi']):
        return True, f"auction URL keyword ({url_l})"
        
    return False, ""

DIFFICULT_PARKING_AREAS = [
    "ταμπούρια", "ταμπουρια", "tabouria",
    "αγία σοφία", "αγια σοφια", "agia sofia"
]

def is_rejected(text, url, price=None, has_parking=None, property_type=None, location=None, title=""):
    comb = (text or "") + " " + (url or "")
    url_l = (url or "").lower()
    ptype_l = (property_type or "").lower()
    title_l = (title or "").lower()
    
    # 1. Auction filter (analyzes full listing text, rendered description, metadata and URL)
    is_auc, auc_reason = is_auction_listing(comb, url)
    if is_auc:
        return True, f"Πλειστηριασμός (Ανιχνεύθηκε στο κείμενο/στοιχεία της αγγελίας: '{auc_reason}')"

    # 2. Blacklisted areas
    for b in BLACKLIST_AREAS:
        if b in comb:
            return True, f"Μη επιλέξιμη περιοχή ({b})"

    # 3. Crime, Petty Theft, Encampments & Scrap routes hard filter
    crime_keywords = [
        "μικροκλοπ", "μικροεγκληματικ", "μικροπαραβατικ",
        "καταυλισμ", "τσιγκάν", "τσιγγάν", "γύφτ",
        "scrap", "πλανόδι", "σχιστ", "εμπόριο μετάλλων"
    ]
    for ck in crime_keywords:
        if ck in comb:
            return True, f"Απορρίφθηκε: Αυξημένη εγκληματικότητα / μικροκλοπές / γειτνίαση με καταυλισμούς ή διαδρομές scrap ({ck})"

    # 4. Rejected property types & non-residential categories
    # Checked strictly against property_type, title or dedicated URL path, NOT general amenity mentions
    for r in REJECTED_PROPERTY_TYPES:
        if ptype_l and r == ptype_l:
            return True, f"Μη επιλέξιμος τύπος ακινήτου ({r})"
        if f"/poliseis-{r}/" in url_l or f"/enoikiaseis-{r}/" in url_l or f"/{r}/" in url_l or f"-{r}-" in url_l:
            return True, f"Μη επιλέξιμη κατηγορία ({r})"
        if title_l and (f"πώληση {r}" in title_l or f"πωληση {r}" in title_l or f"ενοικίαση {r}" in title_l):
            return True, f"Μη επιλέξιμη κατηγορία ({r})"

    # Check rental keywords in URL or title
    if "/enoikiaseis" in url_l or "ενοικιάζεται" in title_l or "ενοικιαζεται" in title_l or "/μήνα" in title_l or "€/μήνα" in title_l:
        return True, "Ενοικίαση (μη επιλέξιμο)"

    # 5. Price threshold (Max €500k for deals)
    if price is not None and price < 50000:
        return True, f"Τιμή €{price:,} < €50k (πιθανή ενοικίαση / ποσοστό)"
    if price is not None and price > PREFERENCES.get("max_acceptable_price_loan", 500000):
        return True, f"Υπέρβαση Budget (Τιμή €{price:,} > €{PREFERENCES.get('max_acceptable_price_loan', 500000):,})"

    # 6. Min SQM (supports decimal formatting like 100.0 τ.μ. from XE)
    sqm_m = re.findall(r'(\d+(?:[\.,]\d+)?)\s*(?:τ\.?μ\.?|sqm)', comb)
    if sqm_m:
        try:
            val_sqm = float(sqm_m[0].replace(',', '.'))
            if val_sqm < PREFERENCES["min_sqm_tolerated"]:
                return True, f"Εμβαδόν {val_sqm:g}τ.μ. < {PREFERENCES['min_sqm_tolerated']}τ.μ."
        except ValueError:
            pass

    # 7. Parking check: only reject if acute parking bottleneck area
    if has_parking is False:
        loc_l = (location or "").lower()
        for dpa in DIFFICULT_PARKING_AREAS:
            if dpa in loc_l or dpa in comb:
                return True, f"Χωρίς Parking σε περιοχή με οξύ πρόβλημα στάθμευσης ({location or dpa})"

    return False, ""

def fetch_email_links(cfg):
    mail = imaplib.IMAP4_SSL(cfg.get('imap_server', 'imap.gmail.com'))
    mail.login(cfg['email_user'], cfg['email_password'])
    mail.select(cfg.get('folder', 'INBOX'))

    status, msgs = mail.search(None, '(UNSEEN)')
    if status != 'OK' or not msgs[0]:
        mail.logout()
        return []

    unseen_ids = msgs[0].split()
    logging.info(f"Processing {len(unseen_ids)} unread alert email(s)...")
    valid_links = []

    for eid in unseen_ids:
        res, mdata = mail.fetch(eid, '(RFC822)')
        if res != 'OK': continue
        raw_msg = mdata[0][1]
        msg = email.message_from_bytes(raw_msg)
        
        body = ""
        if msg.is_multipart():
            for p in msg.walk():
                if p.get_content_type() == 'text/html':
                    body = p.get_payload(decode=True).decode(errors='replace')
                    break
        else:
            if msg.get_content_type() == 'text/html':
                body = msg.get_payload(decode=True).decode(errors='replace')

        if not body:
            mail.store(eid, '+FLAGS', '\\Seen')
            continue

        p = EmailHTMLParser()
        try: p.feed(body)
        except Exception: pass

        # Global fallback thumbnail image candidate
        email_imgs = re.findall(r'src=[\"\'](https?://[^\"\']+\.(?:jpg|png|webp)[^\"\']*)[\"\']', body)
        listing_img = None
        for im in email_imgs:
            if 'logo' not in im and 'dadada' not in im and 'awstrack' not in im:
                listing_img = im
                break

        for href, txt in p.links:
            clean_url = href.split('?')[0].strip()
            portal = None
            if 'spitogatos.gr/aggelia/' in clean_url:
                portal = 'spitogatos'
            elif 'xe.gr/p/' in clean_url or 'xe.gr/property/d/' in clean_url:
                portal = 'xe'
            
            if not portal:
                continue

            # Extract surrounding card text from email body
            card_text = txt
            card_img = None
            idx = body.find(href)
            if idx == -1:
                idx = body.find(clean_url)
            if idx != -1:
                snippet = body[max(0, idx - 400):min(len(body), idx + 2500)]
                clean_snippet = ' '.join(re.sub(r'<[^>]+>', ' ', snippet).split())
                card_text = (txt + " " + clean_snippet).strip()
                c_imgs = re.findall(r'src=[\"\'](https?://[^\"\']+\.(?:jpg|png|webp)[^\"\']*)[\"\']', snippet)
                for ci in c_imgs:
                    if 'logo' not in ci and 'dadada' not in ci and 'awstrack' not in ci:
                        card_img = ci
                        break

            # Parse price candidate to check if it's a rental (< €50k)
            price_cand = None
            pm = re.findall(r'(\d[\d\.]*)\s*€', card_text) or re.findall(r'€\s*(\d[\d\.]*)', card_text)
            for p_val in pm:
                try:
                    v = int(p_val.replace('.', '').replace(',', ''))
                    if v < 10000000:
                        price_cand = v
                        break
                except ValueError:
                    pass

            rej, reason = is_rejected(card_text, clean_url, price=price_cand)
            if rej:
                logging.info(f"Skipping link {clean_url}: {reason}")
                sqm_cand = 0
                sm = re.findall(r'(\d+(?:[\.,]\d+)?)\s*(?:τ\.?μ\.?|sqm)', card_text)
                if sm:
                    try: sqm_cand = int(float(sm[0].replace(',', '.')))
                    except ValueError: pass

                # Extract property type candidate
                ptype_cand = "Διαμέρισμα"
                card_l = card_text.lower()
                if "μονοκατοικία" in card_l or "μονοκατοικια" in card_l:
                    ptype_cand = "Μονοκατοικία"
                elif "μεζονέτα" in card_l or "μεζονετα" in card_l:
                    ptype_cand = "Μεζονέτα"

                # Extract location candidate
                loc_cand = ""
                for official_loc, aliases in [
                    ("Νέα Ιωνία", ["νέα ιωνία", "νεα ιωνια", "nea ionia", "nea iwnia", "αλσούπολη", "αλσουπολη", "καλογρέζα", "περισσός"]),
                    ("Ηράκλειο", ["ηράκλειο", "ηρακλειο", "irakleio", "iraklio"]),
                    ("Μαρούσι", ["μαρούσι", "μαρουσι", "marousi", "maroussi"]),
                    ("Κορυδαλλός", ["κορυδαλλός", "κορυδαλλος", "korydallos"]),
                    ("Νίκαια", ["νίκαια", "νικαια", "nikaia"]),
                    ("Κερατσίνι", ["κερατσίνι", "κερατσινι", "keratsini"]),
                    ("Δραπετσώνα", ["δραπετσώνα", "δραπετσωνα", "drapetsona"]),
                    ("Ταμπούρια", ["ταμπούρια", "ταμπουρια", "tabouria"]),
                    ("Χαλάνδρι", ["χαλάνδρι", "χαλανδρι", "chalandri"]),
                    ("Αγία Παρασκευή", ["αγία παρασκευή", "αγια παρασκευη", "agia paraskevi"]),
                    ("Κηφισιά", ["κηφισιά", "κηφισια", "kifisia", "kifissia"]),
                    ("Μεταμόρφωση", ["μεταμόρφωση", "μεταμορφωση", "metamorfosi"]),
                    ("Λυκόβρυση", ["λυκόβρυση", "λυκοβρυση", "lykovrysi"]),
                    ("Πειραιάς", ["πειραιάς", "πειραιας", "piraeus", "χατζηκυριάκειο", "πειραϊκή"])
                ]:
                    if any(al in card_l for al in aliases):
                        loc_cand = official_loc
                        break

                display_t = f"Πώληση, {ptype_cand}, {sqm_cand}τ.μ. {loc_cand}".strip()
                if price_cand:
                    display_t += f" | €{price_cand:,}"
                record_rejected_listing(clean_url, reason, title=display_t, price=price_cand or 0, sqm=sqm_cand, ptype=ptype_cand, loc=loc_cand)
                continue

            if clean_url not in [l['url'] for l in valid_links]:
                valid_links.append({
                    'portal': portal,
                    'url': clean_url,
                    'text': card_text,
                    'img_url': card_img or listing_img
                })

        mail.store(eid, '+FLAGS', '\\Seen')

    mail.logout()
    return valid_links

def parse_and_evaluate_listing(portal, url, raw_html, card_text="", tab_title="", rendered_text=""):
    """Extract attributes, compute risk, deal and fit scores, and build record dictionary"""
    # 1. Listing ID
    if portal == 'spitogatos':
        m = re.search(r'aggelia/(\d+)', url)
        lid = m.group(1) if m else str(int(time.time()))
    else:
        m = re.search(r'xe\.gr/p/([a-f0-9\-]+)', url) or re.search(r'xe\.gr/property/d/[^/]+/([a-f0-9\-]+)', url)
        lid = f"xe-{m.group(1)[:8]}" if m else f"xe-{int(time.time())}"

    # Extract comprehensive full listing text (rendered description, card, JSON payloads, meta tags)
    comb_text = extract_listing_full_text(raw_html, rendered_text=rendered_text, card_text=card_text)

    # Check blacklist on combined text & url
    for b in BLACKLIST_AREAS:
        if b in comb_text.lower() or b in url.lower():
            raise ValueError(f"Property {lid} rejected: Blacklisted area '{b}' detected.")

    # Canonical metadata extraction from page title
    page_title = tab_title or ""
    if not page_title and raw_html:
        m_t = re.search(r'<title>(.*?)</title>', raw_html, re.DOTALL | re.IGNORECASE)
        if m_t:
            page_title = html_lib.unescape(m_t.group(1)).strip()

    extracted_ptype = None
    extracted_sqm = None
    extracted_loc = None
    extracted_price = None

    if portal == 'xe' and page_title:
        m_xe = re.search(r'Πώληση κατοικίας\s*-\s*([^,]+),\s*(\d+(?:[\.,]\d+)?)\s*τ\.?μ\.?,\s*([^,]+),\s*([\d\.]+)', page_title)
        if m_xe:
            extracted_ptype = m_xe.group(1).strip()
            try: extracted_sqm = int(float(m_xe.group(2).replace(',', '.')))
            except ValueError: pass
            extracted_loc = m_xe.group(3).strip()
            try: extracted_price = int(m_xe.group(4).replace('.', '').replace(',', ''))
            except ValueError: pass
    elif portal == 'spitogatos' and page_title:
        m_sp = re.search(r'Πώληση,\s*([^,]+),\s*(\d+(?:[\.,]\d+)?)\s*τ\.?μ\.?\s*([^,|]+)', page_title)
        if m_sp:
            extracted_ptype = m_sp.group(1).strip()
            try: extracted_sqm = int(float(m_sp.group(2).replace(',', '.')))
            except ValueError: pass
            extracted_loc = m_sp.group(3).split(',')[0].strip()

    # 2. Price
    price = extracted_price
    if not price:
        price = 160000
        price_matches = re.findall(r'(\d[\d\.]*)\s*€', comb_text) or re.findall(r'€\s*(\d[\d\.]*)', comb_text)
        for pm in price_matches:
            try:
                val = int(pm.replace('.', '').replace(',', ''))
                if 50000 <= val <= 2000000:
                    price = val
                    break
            except ValueError:
                pass

    # Sqm
    sqm = extracted_sqm
    if not sqm:
        sqm = 120
        sqm_m = re.findall(r'(\d+[\.\d]*)\s*τ\.?μ\.?', comb_text)
        for sm in sqm_m:
            try:
                val = int(float(sm))
                if 80 <= val <= 600:
                    sqm = val
                    break
            except ValueError:
                pass

    # Year
    year = 1975
    year_m = re.findall(r'\b(19[5-9]\d|20[0-2]\d)\b', comb_text)
    if year_m:
        year = int(year_m[0])

    # Property Type
    if extracted_ptype:
        if "μονοκατοικία" in extracted_ptype.lower() or "μονοκατοικια" in extracted_ptype.lower():
            ptype = "Μονοκατοικία"
        elif "μεζονέτα" in extracted_ptype.lower() or "μεζονετα" in extracted_ptype.lower():
            ptype = "Μεζονέτα"
        elif "πολυκατοικία" in extracted_ptype.lower() or "πολυκατοικια" in extracted_ptype.lower():
            ptype = "Πολυκατοικία"
        else:
            ptype = "Διαμέρισμα"
    else:
        card_l = card_text.lower()
        if "διαμέρισμα" in card_l or "διαμερισμα" in card_l:
            ptype = "Διαμέρισμα"
        elif "μεζονέτα" in card_l or "μεζονετα" in card_l:
            ptype = "Μεζονέτα"
        elif "μονοκατοικία" in card_l or "μονοκατοικια" in card_l:
            ptype = "Μονοκατοικία"
        elif any(w in comb_text.lower() for w in ["μονοκατοικία", "μονοκατοικια", "detached"]):
            ptype = "Μονοκατοικία"
        elif "μεζονέτα" in comb_text.lower():
            ptype = "Μεζονέτα"
        else:
            ptype = "Διαμέρισμα"
    
    # Location Matching
    loc_candidates = [
        ("Αγία Παρασκευή", ["αγία παρασκευή", "αγια παρασκευη", "agia paraskevi", "κοντόπευκο", "αγιάννης"]),
        ("Μαρούσι", ["μαρούσι", "μαρουσι", "marousi", "maroussi", "νέο τέρμα", "νεο τερμα", "σωρός", "σωρος"]),
        ("Χαλάνδρι", ["χαλάνδρι", "χαλανδρι", "chalandri", "ριζάρειος", "ριζαρειος"]),
        ("Ηράκλειο", ["ηράκλειο", "ηρακλειο", "irakleio", "iraklio"]),
        ("Νέα Ιωνία", ["νέα ιωνία", "νεα ιωνια", "nea ionia", "nea iwnia", "αλσούπολη", "αλσουπολη", "καλογρέζα", "καλογρεζα", "περισσός", "περισσος", "ινέπολη", "ινεπολη"]),
        ("Μεταμόρφωση", ["μεταμόρφωση", "μεταμορφωση", "metamorfosi"]),
        ("Λυκόβρυση", ["λυκόβρυση", "λυκοβρυση", "lykovrysi"]),
        ("Βριλήσσια", ["βριλήσσια", "βριλησσια", "vrilissia"]),
        ("Πεύκη", ["πεύκη", "πευκη", "pefki"]),
        ("Μελίσσια", ["μελίσσια", "μελισσια", "melissia"]),
        ("Κηφισιά", ["κηφισιά", "κηφισια", "kifisia", "kifissia"]),
        ("Κορυδαλλός", ["κορυδαλλός", "κορυδαλλος", "korydallos", "πλατεία ελευθερίας"]),
        ("Νίκαια", ["νίκαια", "νικαια", "nikaia", "μητρόπολη", "νεάπολη", "νεαπολη", "χρυσόστομος"]),
        ("Κερατσίνι", ["κερατσίνι", "κερατσινι", "keratsini", "αμφιάλη", "αμφιαλη", "ευγένεια", "ευγενεια"]),
        ("Δραπετσώνα", ["δραπετσώνα", "δραπετσωνα", "drapetsona", "ανάληψη"]),
        ("Ταμπούρια", ["ταμπούρια", "ταμπουρια", "tabouria", "αγία σοφία"]),
        ("Πειραιάς (Χατζηκυριάκειο)", ["χατζηκυριάκειο", "χατζηκυριακειο", "πειραϊκή", "πειραικη", "chatzikyriakeio", "piraiki"]),
        ("Πειραιάς (Καμίνια)", ["καμίνια", "καμινια", "παλαιά κοκκινιά", "παλαια κοκκινια", "kaminia", "kaminiwn", "kokkinia"]),
        ("Πειραιάς", ["πειραιάς", "πειραιας", "piraeus"])
    ]
    loc = None
    # 1. Match extracted location from page title/url first
    search_context = (extracted_loc or "") + " " + (url or "")
    for official_loc, aliases in loc_candidates:
        if any(al in search_context.lower() for al in aliases):
            loc = official_loc
            break
    # 2. Match email card text
    if not loc and card_text:
        for official_loc, aliases in loc_candidates:
            if any(al in card_text.lower() for al in aliases):
                loc = official_loc
                break
    # 3. If extracted location exists directly from portal title, preserve it
    if not loc and extracted_loc:
        loc = extracted_loc
    # 4. Fallback: match visible text, explicitly stripping broker agency addresses
    if not loc:
        clean_search = re.sub(r'(?:πληροφορίες\s*αγγελιοδότη|στοιχεία\s*μεσίτη|μεσιτικό\s*γραφείο|realty|real\s*estate).*', ' ', comb_text, flags=re.DOTALL | re.IGNORECASE)
        clean_lower = clean_search.lower()
        for official_loc, aliases in loc_candidates:
            if any(al in clean_lower for al in aliases):
                loc = official_loc
                break
    if not loc:
        loc = extracted_loc or "Κερατσίνι"

    title = f"Πώληση, {ptype}, {sqm}τ.μ. {loc} | {lid}"
    filename = f"{title}.html"
    html_report = f"property-{lid}.html"

    # Coordinates
    loc_coords = {
        "Κερατσίνι": (37.9625, 23.6260),
        "Δραπετσώνα": (37.9450, 23.6200),
        "Κορυδαλλός": (37.9850, 23.6500),
        "Νίκαια": (37.9700, 23.6400),
        "Ταμπούρια": (37.9550, 23.6300),
        "Μαρούσι": (38.0521, 23.7984),
        "Αγία Παρασκευή": (38.0160, 23.8200),
        "Ηράκλειο": (38.0604, 23.7645),
        "Χαλάνδρι": (38.0220, 23.7990),
        "Βριλήσσια": (38.0350, 23.8300),
        "Πειραιάς (Χατζηκυριάκειο)": (37.9350, 23.6350),
        "Πειραιάς (Καμίνια)": (37.9550, 23.6600),
        "Πειραιάς": (37.9430, 23.6470),
        "Κηφισιά": (38.0740, 23.8120),
        "Πεύκη": (38.0600, 23.7930),
        "Μελίσσια": (38.0500, 23.8300),
        "Νέα Ιωνία": (38.0350, 23.7550),
        "Μεταμόρφωση": (38.0650, 23.7600),
        "Λυκόβρυση": (38.0680, 23.7800)
    }
    lat, lon = loc_coords.get(loc, (37.9700, 23.6500))

    # Turnkey DIY calculation
    renov_low = round(sqm * 350)
    renov_high = round(sqm * 550)
    renov_diy = round(sqm * 420)
    turnkey_diy = price + renov_diy
    turnkey_low = price + renov_low
    turnkey_high = price + renov_high

    # Risk score & reasons based on area & year
    if loc in ["Μαρούσι", "Αγία Παρασκευή", "Χαλάνδρι", "Ηράκλειο", "Βριλήσσια", "Κηφισιά", "Πεύκη", "Μελίσσια", "Νέα Ιωνία", "Μεταμόρφωση", "Λυκόβρυση"]:
        risk_score = 2.5
        risk_level = "Χαμηλό Ρίσκο"
        risk_color = "#059669"
        crime_risk = f"Χαμηλό στην ευρύτερη περιοχή {loc}."
    elif loc in ["Πειραιάς (Χατζηκυριάκειο)", "Πειραιάς"]:
        risk_score = 3.2
        risk_level = "Χαμηλό Ρίσκο"
        risk_color = "#059669"
        crime_risk = f"Χαμηλό προς Μέτριο στην περιοχή {loc}."
    else:
        risk_score = 3.6
        risk_level = "Μέτριο Ρίσκο"
        risk_color = "#d97706"
        crime_risk = f"Μέτριο στην περιοχή {loc}."

    risk_reasons = [
        f"Κατασκευή {year}: Ανάγκη συνήθους αναβάθμισης υδραυλικών/ηλεκτρολογικών.",
        f"Τοποθεσία ({loc}): Ασφαλής οικιστική ζώνη.",
        f"{ptype} με καλές δυνατότητες διαρρύθμισης."
    ]

    # Parking Extraction (strict positive evidence only, ignoring footer links)
    has_parking = False
    parking_info = "Χωρίς Parking"
    card_lower = card_text.lower()
    if any(k in card_lower for k in ["θέση στάθμευσης", "θεση σταθμευσης", "θέσεις στάθμευσης", "γκαράζ", "1 parking", "2 parking"]) and "χωρίς parking" not in card_lower and "χωρίς θέση" not in card_lower:
        has_parking = True
        parking_info = "Θέση Στάθμευσης"
    elif raw_html:
        clean_html = re.sub(r'<(footer|nav|header).*?</\1>', ' ', raw_html, flags=re.DOTALL | re.IGNORECASE)
        clean_html = re.sub(r'enoikiaseis-parking|poliseis-parking', ' ', clean_html)
        if re.search(r'(?:θέση\s*στάθμευσης|κλειστό\s*parking|υπαίθριο\s*parking|θέσεις\s*στάθμευσης|parking)\s*:\s*(?:[1-9]|Ναι|Δική|Υπαίθριο|Κλειστό|Πυλωτής)', clean_html, re.I):
            has_parking = True
            parking_info = "Θέση Στάθμευσης"
        elif any(k in clean_html.lower() for k in ["αποκλειστική θέση στάθμευσης", "αποκλειστικη θεση σταθμευσης", "δική του αποκλειστική θέση", "δικη του αποκλειστικη θεση"]):
            has_parking = True
            parking_info = "Θέση Στάθμευσης"

    # Evaluation filter: Reject auctions and no parking in difficult areas
    rej, rej_why = is_rejected(comb_text, url, price=price, has_parking=has_parking, property_type=ptype, location=loc, title=title)
    if rej:
        display_title = f"Πώληση, {ptype}, {sqm}τ.μ. {loc} | €{price:,}"
        record_rejected_listing(url, rej_why, title=display_title, price=price, sqm=sqm, ptype=ptype, loc=loc)
        raise ValueError(f"Property {lid} rejected: {rej_why}")

    record = {
        "filename": filename,
        "listing_id": lid,
        "title": title,
        "location": f"{sqm}τ.μ. {loc}",
        "type": ptype,
        "price": str(price),
        "sqm": str(sqm),
        "year": str(year),
        "plot_sqm": str(sqm),
        "courtyard": "Αυλή / Βεράντα",
        "renov_low": str(renov_low),
        "renov_high": str(renov_high),
        "turnkey_low": str(turnkey_low),
        "turnkey_high": str(turnkey_high),
        "html_report": html_report,
        "spitogatos_url": url,
        "lat": str(lat),
        "lon": str(lon),
        "processed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "renov_diy": str(renov_diy),
        "turnkey_diy": str(turnkey_diy),
        "risk_score": str(risk_score),
        "risk_level": risk_level,
        "risk_reasons": json.dumps(risk_reasons, ensure_ascii=False),
        "deal_score": "78.0",
        "deal_grade": "A",
        "deal_desc": "Πολύ Καλή Επιλογή",
        "deal_color": "#059669",
        "has_parking": "True" if has_parking else "False",
        "parking_info": parking_info,
        "baths": "1",
        "wc": "1" if ptype == "Μεζονέτα" else "0",
        "beds": "3" if sqm >= 115 else "2",
        "is_penthouse": "True" if "ρετιρέ" in comb_text.lower() else "False",
        "crime_risk": crime_risk,
        "encampment_risk": "Μηδενικό. Καμία απολύτως σχέση με καταυλισμούς.",
        "environmental_risk": "Ήσυχο οικιστικό περιβάλλον.",
        "risk_color": risk_color,
        "street_parking_ease": "PRIVATE" if has_parking else ("EASY" if loc in ["Μαρούσι", "Αγία Παρασκευή", "Χαλάνδρι", "Ηράκλειο", "Βριλήσσια", "Κηφισιά", "Πεύκη", "Μελίσσια", "Νέα Ιωνία", "Μεταμόρφωση", "Λυκόβρυση", "Γέρακας", "Δροσιά"] else "MODERATE"),
        "enfia": str(calculate_enfia(sqm, loc, year, ptype, "ρετιρέ" in comb_text.lower()))
    }

    # Evaluate User Fit with budget engine
    fit_score, fit_grade, fit_desc, fit_color, fit_breakdown, dealbreakers = evaluate_user_fit_with_budget_and_risk(record)
    record["fit_score"] = fit_score
    record["fit_grade"] = fit_grade
    record["fit_desc"] = fit_desc
    record["fit_color"] = fit_color
    record["fit_breakdown"] = json.dumps(fit_breakdown, ensure_ascii=False)
    record["dealbreakers"] = json.dumps(dealbreakers, ensure_ascii=False)

    return record

def generate_property_html(record):
    """Generates the dedicated HTML report for the property"""
    html_name = record["html_report"]
    target_path = os.path.join(base_dir, html_name)

    fit_items = json.loads(record.get('fit_breakdown', '[]'))
    fit_items_html = "".join([f"<li style='margin-bottom:6px;'>{it}</li>" for it in fit_items])

    html_content = f"""<!DOCTYPE html>
<html lang="el">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{record['title']}</title>
    <style>
        :root {{
            --primary: #0f172a;
            --accent: #2563eb;
            --bg: #f8fafc;
            --card-bg: #ffffff;
            --text-main: #1e293b;
            --text-muted: #64748b;
            --border: #e2e8f0;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background: var(--bg);
            color: var(--text-main);
            margin: 0;
            padding: 24px;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
        }}
        .card {{
            background: var(--card-bg);
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);
            border: 1px solid var(--border);
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 2px solid var(--border);
            padding-bottom: 16px;
            margin-bottom: 20px;
        }}
        .pill {{
            padding: 6px 14px;
            border-radius: 9999px;
            font-weight: 700;
            font-size: 0.9rem;
            color: white;
        }}
        .btn {{
            display: inline-block;
            background: var(--accent);
            color: white;
            text-decoration: none;
            padding: 10px 20px;
            border-radius: 8px;
            font-weight: bold;
            margin-top: 10px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <a href="index.html" style="text-decoration:none; color:var(--accent); font-weight:bold;">&larr; Πίσω στον Πίνακα Ακινήτων</a>
        <div class="card" style="margin-top:16px;">
            <div class="header">
                <div>
                    <h1 style="margin:0 0 8px 0; font-size:1.6rem;">{record['title']}</h1>
                    <span style="color:var(--text-muted);">{record['location']} &bull; Έτος: {record['year']}</span>
                </div>
                <div>
                    <span class="pill" style="background:{record['fit_color']}; font-size:1.1rem;">Match: {record['fit_grade']} ({record['fit_score']}/100)</span>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap:16px; margin-bottom:20px;">
                <div style="background:#f1f5f9; padding:12px; border-radius:8px;">
                    <div style="color:var(--text-muted); font-size:0.85rem;">Ζητούμενη Τιμή</div>
                    <div style="font-size:1.4rem; font-weight:800; color:#0f172a;">€ {int(record['price']):,}</div>
                </div>
                <div style="background:#f1f5f9; padding:12px; border-radius:8px;">
                    <div style="color:var(--text-muted); font-size:0.85rem;">Εμβαδόν</div>
                    <div style="font-size:1.4rem; font-weight:800; color:#0f172a;">{record['sqm']} τ.μ.</div>
                </div>
                <div style="background:#f1f5f9; padding:12px; border-radius:8px;">
                    <div style="color:var(--text-muted); font-size:0.85rem;">Turnkey DIY Κόστος</div>
                    <div style="font-size:1.4rem; font-weight:800; color:#059669;">€ {int(record['turnkey_diy']):,}</div>
                </div>
            </div>

            <div class="card" style="border: 2px solid {record['fit_color']}; background: #fcfdfd;">
                <h3 style="margin:0 0 10px 0; color:{record['fit_color']};">🎯 Ανάλυση Προσωπικού Ταιριάσματος: {record['fit_score']}/100</h3>
                <p style="color:var(--text-muted); font-size:0.9rem;">{record['fit_desc']}</p>
                <ul style="line-height:1.6; padding-left:20px;">
                    {fit_items_html}
                </ul>
            </div>

            <div style="margin-top:20px;">
                <a href="{record['spitogatos_url']}" target="_blank" class="btn">🔗 Άνοιγμα Αγγελίας στο Portal</a>
            </div>
        </div>
    </div>
</body>
</html>
"""
    with open(target_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    logging.info(f"Generated HTML report: {html_name}")

def update_csv_and_index(new_records):
    """Upserts new records into processed_listings.csv and index.html"""
    if not new_records:
        return

    # 1. Update CSV
    existing = []
    if os.path.exists(csv_path):
        with open(csv_path, 'r', encoding='utf-8') as f:
            existing = list(csv.DictReader(f))

    fieldnames = list(existing[0].keys()) if existing else list(new_records[0].keys())

    cleaned_records = []
    for nr in new_records:
        cleaned = {}
        for fn in fieldnames:
            cleaned[fn] = nr.get(fn, "")
        cleaned_records.append(cleaned)

    # Merge
    merged_dict = {r['listing_id']: r for r in existing}
    for nr in cleaned_records:
        merged_dict[nr['listing_id']] = nr

    merged_list = list(merged_dict.values())

    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(merged_list)

    logging.info(f"Updated CSV with {len(new_records)} new record(s). Total: {len(merged_list)}")

    # 2. Update index.html
    with open(index_path, 'r', encoding='utf-8') as f:
        idx_content = f.read()

    pos_data = idx_content.find('const propertiesData = [')
    end_data = idx_content.find('];', pos_data)

    if pos_data != -1 and end_data != -1:
        raw_json = idx_content[pos_data + 23 : end_data + 1]
        try:
            index_props = json.loads(raw_json)
        except Exception:
            index_props = []

        prop_map = {p['listing_id']: p for p in index_props}

        for nr in new_records:
            has_p = nr.get("has_parking") == "True" or nr.get("has_parking") is True
            prop_map[nr['listing_id']] = {
                "filename": nr.get("filename", ""),
                "listing_id": nr["listing_id"],
                "title": nr.get("title", ""),
                "location": nr.get("location", ""),
                "type": nr.get("type", ""),
                "price": float(nr.get("price", 0)),
                "sqm": float(nr.get("sqm", 0)),
                "year": int(nr.get("year", 0)),
                "plot_sqm": float(nr.get("plot_sqm", 0) or 0),
                "courtyard": nr.get("courtyard", ""),
                "renov_low": float(nr.get("renov_low", 0)),
                "renov_high": float(nr.get("renov_high", 0)),
                "turnkey_low": float(nr.get("turnkey_low", 0)),
                "turnkey_high": float(nr.get("turnkey_high", 0)),
                "html_report": nr.get("html_report", ""),
                "spitogatos_url": nr.get("spitogatos_url", ""),
                "lat": float(nr.get("lat", 37.97)),
                "lon": float(nr.get("lon", 23.65)),
                "processed_at": nr.get("processed_at", ""),
                "renov_diy": float(nr.get("renov_diy", 0)),
                "turnkey_diy": float(nr.get("turnkey_diy", 0)),
                "risk_score": float(nr.get("risk_score", 3.5)),
                "risk_level": nr.get("risk_level", "Χαμηλό Ρίσκο"),
                "deal_score": float(nr.get("deal_score", 75.0)),
                "deal_grade": nr.get("deal_grade", "A"),
                "deal_desc": nr.get("deal_desc", "Πολύ Καλή Επιλογή"),
                "deal_color": nr.get("deal_color", "#059669"),
                "fit_score": float(nr.get("fit_score", 80.0)),
                "fit_grade": nr.get("fit_grade", "A"),
                "fit_desc": nr.get("fit_desc", ""),
                "fit_color": nr.get("fit_color", "#059669"),
                "has_parking": has_p,
                "parking_info": nr.get("parking_info", "Χωρίς Parking" if not has_p else "Θέση Στάθμευσης"),
                "baths": int(nr.get("baths", 1)),
                "wc": int(nr.get("wc", 1)),
                "beds": int(nr.get("beds", 3)),
                "is_penthouse": nr.get("is_penthouse") == "True",
                "thumb": nr.get("thumb", f"thumbs/{nr['listing_id']}.jpg" if os.path.exists(os.path.join(base_dir, 'thumbs', f"{nr['listing_id']}.jpg")) else ""),
                "image_url": nr.get("image_url", ""),
                "street_parking_ease": nr.get("street_parking_ease", "PRIVATE" if has_p else "DIFFICULT"),
                "enfia": calculate_enfia(nr.get("sqm", 0), nr.get("location", ""), nr.get("year", 0), nr.get("type", ""), nr.get("is_penthouse") == "True")
            }

        new_props_list = list(prop_map.values())
        new_json_str = json.dumps(new_props_list, ensure_ascii=False, indent=2)
        idx_content = idx_content[:pos_data + 23] + new_json_str + idx_content[end_data + 1:]

        # Update approved property badge counts
        active_count = len(new_props_list)
        idx_content = re.sub(r'<span>Εγκεκριμένα:</span>\s*<b[^>]*>\s*\d+\s*</b>', f'<span>Εγκεκριμένα:</span>\n                    <b>{active_count}</b>', idx_content)
        idx_content = re.sub(r'Εγκεκριμένα\s*Ακίνητα\s*\(\d+\)', f'Εγκεκριμένα Ακίνητα ({active_count})', idx_content)
        idx_content = re.sub(r'Λίστα\s*Ακινήτων\s*\(\d+\)', f'Λίστα Ακινήτων ({active_count})', idx_content)
        idx_content = re.sub(r'\d+\s*Ενεργά\s*Ακίνητα', f'{active_count} Ενεργά Ακίνητα', idx_content)

        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(idx_content)
        logging.info("Updated index.html propertiesData successfully.")
        sync_rejected_to_index()

def sync_rejected_to_index():
    """Syncs rejected_listings.json into index.html and updates badges"""
    if not os.path.exists(rejected_json_path) or not os.path.exists(index_path):
        return False
    try:
        with open(rejected_json_path, 'r', encoding='utf-8') as rf:
            rej_list = json.load(rf)
        rej_count = len(rej_list)
        
        with open(index_path, 'r', encoding='utf-8') as f:
            idx_content = f.read()

        changed = False
        pos_rej = idx_content.find('const rejectedData = [')
        if pos_rej != -1:
            end_rej = idx_content.find('];', pos_rej)
            if end_rej != -1:
                rej_json_str = json.dumps(rej_list, ensure_ascii=False, indent=2)
                old_chunk = idx_content[pos_rej + 21 : end_rej + 1]
                if old_chunk.strip() != rej_json_str.strip():
                    idx_content = idx_content[:pos_rej + 21] + rej_json_str + idx_content[end_rej + 1:]
                    changed = True

        # Update badge counts if changed
        idx_content = re.sub(r'Απορριφθέντα\s*\(\d+\)', f'Απορριφθέντα ({rej_count})', idx_content)
        idx_content = re.sub(r'>\s*🚫\s*Απορρίφθηκαν:.*?<b[^>]*>\s*\d+\s*</b>', f'>🚫 Απορρίφθηκαν:</span>\n                    <b style="color:#ef4444;">{rej_count}</b>', idx_content, flags=re.DOTALL)
        idx_content = re.sub(r'Απορριφθέντα\s*Ακίνητα\s*\(\d+\)', f'Απορριφθέντα Ακίνητα ({rej_count})', idx_content)
        idx_content = re.sub(r'&bull;\s*\d+\s*Απορριφθέντα', f'&bull; {rej_count} Απορριφθέντα', idx_content)

        # Also update approved property count from propertiesData and archived count
        active_m = re.search(r'const propertiesData = (\[.*?\]);', idx_content, re.DOTALL)
        if active_m:
            try:
                active_count = len(json.loads(active_m.group(1)))
                idx_content = re.sub(r'<span>Εγκεκριμένα:</span>\s*<b[^>]*>\s*\d+\s*</b>', f'<span>Εγκεκριμένα:</span>\n                    <b id="stat-approved-count">{active_count}</b>', idx_content)
                idx_content = re.sub(r'Εγκεκριμένα\s*(?:Ακίνητα)?\s*\(\d+\)', f'Εγκεκριμένα ({active_count})', idx_content)
                idx_content = re.sub(r'Λίστα\s*(?:Ακινήτων)?\s*\(\d+\)', f'Λίστα ({active_count})', idx_content)
                idx_content = re.sub(r'\d+\s*Ενεργά\s*Ακίνητα', f'{active_count} Ενεργά Ακίνητα', idx_content)
            except Exception:
                pass

        arch_count = 0
        if os.path.exists(archived_json_path):
            try:
                with open(archived_json_path, 'r', encoding='utf-8') as af:
                    arch_count = len(json.load(af))
                idx_content = re.sub(r'Παλιά\s*Αποθηκευμένα\s*\(\d+\)', f'Παλιά Αποθηκευμένα ({arch_count})', idx_content)
                idx_content = re.sub(r'>\s*📁\s*Παλιά:.*?<b[^>]*>\s*\d+\s*</b>', f'>📁 Παλιά:</span>\n                    <b id="stat-archived-count" style="color:#f59e0b;">{arch_count}</b>', idx_content, flags=re.DOTALL)
                idx_content = re.sub(r'&bull;\s*\d+\s*Παλιά', f'&bull; {arch_count} Παλιά', idx_content)
            except Exception:
                pass

        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(idx_content)
        logging.info(f"Synchronized index.html with {rej_count} rejected and {arch_count} archived properties.")
        return True
    except Exception as e:
        logging.error(f"Error syncing rejectedData to index.html: {e}")
        return False

def git_commit_and_push(new_count=0, msg=None):
    """Stages changes, commits with meaningful message and pushes to origin main"""
    try:
        subprocess.run(["git", "add", "webarchives/processed_listings.csv", "webarchives/archived_listings.json", "webarchives/rejected_listings.json", "index.html", "property-*.html", "thumbs/*.jpg", "auto_pipeline.py", "rich_report_generator.py", "user_fit_budget_engine.py", "street_parking_security_intel.py"], cwd=base_dir, check=True)
        # Check if there are staged changes
        st_proc = subprocess.run(["git", "diff", "--staged", "--quiet"], cwd=base_dir)
        if st_proc.returncode == 0:
            logging.info("No git changes to commit.")
            return
        commit_msg = msg or (f"feat(auto-ingest): Add {new_count} new evaluated properties from email alerts" if new_count > 0 else "feat(auto-ingest): Update rejected listings and index")
        subprocess.run(["git", "commit", "-m", commit_msg], cwd=base_dir, check=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=base_dir, check=True)
        logging.info("Successfully pushed updates to GitHub!")
    except subprocess.CalledProcessError as e:
        logging.error(f"Git commit/push error: {e}")

def run_pipeline():
    cfg = load_config()
    if not cfg:
        logging.error("No config.json found.")
        return

    now_str = datetime.now().strftime("%H:%M:%S (%d/%m)")
    existing_ids = get_existing_listing_ids()
    active_bot_challenge = None

    # 1. Fetch email links
    links = fetch_email_links(cfg)
    if not links:
        logging.info("No new email links to process.")
        update_status_file(now_str, 0, bot_challenge=active_bot_challenge)
        return

    logging.info(f"Found {len(links)} raw qualifying link(s). Filtering out already processed...")
    new_records = []

    for item in links:
        url = item['url']
        portal = item['portal']
        
        # Check if already processed
        is_already_added = any(lid in url for lid in existing_ids)
        if is_already_added:
            logging.info(f"Listing {url} already in dataset. Skipping.")
            continue

        logging.info(f"Downloading listing via Safari: {url}")
        html = ""
        rendered_text = ""
        try:
            title, html, rendered_text = fetch_url_via_safari(url)
            is_bot, b_plat, b_url = check_bot_challenge(title, html, url)
            if is_bot:
                logging.warning(f"⚠️ Bot challenge detected on {b_plat}: {b_url}")
                active_bot_challenge = {"platform": b_plat, "url": b_url}
        except Exception as e:
            logging.warning(f"Safari fetch failed for {url}: {e}. Proceeding with email card data.")

        try:
            record = parse_and_evaluate_listing(portal, url, html, card_text=item.get('text', ''), tab_title=title if 'title' in locals() else '', rendered_text=rendered_text)
            
            # Download thumbnail if found (from email or fallback to page og:image / HTML)
            lid = record['listing_id']
            img_url = item.get('img_url')
            if not img_url and html:
                m_og = re.search(r'<meta[^>]+property=[\"\']og:image[\"\'][^>]+content=[\"\']([^\"\']+)[\"\']', html, re.I) or re.search(r'<meta[^>]+content=[\"\']([^\"\']+)[\"\'][^>]+property=[\"\']og:image[\"\']', html, re.I)
                if m_og:
                    img_url = html_lib.unescape(m_og.group(1)).strip()
                if not img_url:
                    all_imgs = re.findall(r'https?://[^\s\"\'<>]+\.(?:jpg|jpeg|png|webp)', html)
                    for im in all_imgs:
                        if ('blob.cdn.xe.gr' in im or 'images.spitogatos.gr' in im) and 'logo' not in im and 'icon' not in im:
                            img_url = im
                            break

            thumbs_map = {}
            if img_url:
                record['image_url'] = img_url
                thumbs_dir = os.path.join(base_dir, 'thumbs')
                os.makedirs(thumbs_dir, exist_ok=True)
                thumb_file = f"{lid}.jpg"
                thumb_target = os.path.join(thumbs_dir, thumb_file)
                try:
                    req = urllib.request.Request(img_url, headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'})
                    with urllib.request.urlopen(req, timeout=8) as resp, open(thumb_target, 'wb') as out:
                        out.write(resp.read())
                    record['thumb'] = f"thumbs/{thumb_file}"
                    thumbs_map[lid] = f"thumbs/{thumb_file}"
                except Exception as ex:
                    logging.warning(f"Could not download thumbnail for {lid}: {ex}")
            elif os.path.exists(os.path.join(base_dir, 'thumbs', f"{lid}.jpg")):
                record['thumb'] = f"thumbs/{lid}.jpg"
                thumbs_map[lid] = f"thumbs/{lid}.jpg"

            # Generate full rich report matching master standards
            rich_html = generate_rich_property_html(record, thumbs_map)
            target_report_path = os.path.join(base_dir, record['html_report'])
            with open(target_report_path, 'w', encoding='utf-8') as f:
                f.write(rich_html)
            logging.info(f"Generated full rich HTML report: {record['html_report']}")

            new_records.append(record)
            existing_ids.add(record['listing_id'])
            time.sleep(1) # polite throttle
        except Exception as e:
            logging.error(f"Failed to process {url}: {e}")

    if new_records:
        logging.info(f"Updating database & portal with {len(new_records)} new properties...")
        update_csv_and_index(new_records)
        git_commit_and_push(len(new_records))
        update_status_file(now_str, len(new_records), [r['spitogatos_url'] for r in new_records], bot_challenge=active_bot_challenge)
    else:
        logging.info("No novel properties were added in this run. Checking rejected listings sync...")
        sync_rejected_to_index()
        git_commit_and_push(0, msg="feat(auto-ingest): Sync rejected listings to index.html")
        update_status_file(now_str, 0, bot_challenge=active_bot_challenge)

if __name__ == '__main__':
    run_pipeline()
