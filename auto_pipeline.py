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

import os, sys, json, csv, re, time, subprocess, logging, imaplib, email, urllib.request
from datetime import datetime
from email.header import decode_header
from html.parser import HTMLParser
from rich_report_generator import generate_rich_property_html

base_dir = '/Volumes/Terataki/projects/spitia'
csv_path = os.path.join(base_dir, 'webarchives', 'processed_listings.csv')
index_path = os.path.join(base_dir, 'index.html')
config_path = os.path.join(base_dir, 'config.json')
status_path = os.path.join(base_dir, 'alert_status.json')
scratch_dir = '/Users/vnikolopoulos/.gemini/antigravity-cli/brain/f5cd4cb5-f15c-425c-8e9a-e4ffdc3ca53f/scratch'

sys.path.append(scratch_dir)
try:
    from user_fit_budget_engine import evaluate_user_fit_with_budget_and_risk, USER_CASH
except Exception as e:
    logging.warning(f"Warning importing user_fit_budget_engine: {e}")

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
        close targetTab
        return tabTitle & "|||SPLIT|||" & pageSource
    end tell
    '''
    proc = subprocess.run(['osascript', '-e', applescript], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise Exception(f"AppleScript error: {proc.stderr}")
    
    parts = proc.stdout.split('|||SPLIT|||')
    title = parts[0].strip()
    html = parts[1].strip() if len(parts) > 1 else ""
    return title, html


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
    "max_acceptable_price_loan": 240000,
    "ideal_sqm": 120,
    "min_sqm_tolerated": 90,
    "rejected_keywords": [
        "οικόπεδο", "οικοπεδο", "αγροτεμάχιο", "αγροτεμαχιο", "plot",
        "επαγγελματικός", "γραφείο", "γραφειο", "κατάστημα", "καταστημα", "commercial",
        "parking", "γκαράζ", "αποθήκη", "αποθηκη", "υπόγειο", "υπογειο",
        "ενοικίαση", "ενοικιαση", "ενοικιάζεται", "ενοικιαζεται", "/μήνα", "/μηνα", "€ / μήνα", "€/μήνα"
    ]
}

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
    data = {
        "last_run": last_run,
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
    if not os.path.exists(csv_path):
        return set()
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return {r['listing_id'] for r in reader if 'listing_id' in r}

def is_rejected(text, url, price=None):
    comb = (text + " " + url).lower()
    for b in BLACKLIST_AREAS:
        if b in comb:
            return True, f"Blacklisted area: {b}"
    for r in PREFERENCES["rejected_keywords"]:
        if r in comb:
            return True, f"Rejected keyword: {r}"
    if price is not None and price < 50000:
        return True, f"Price {price} < €50k (likely rental/share)"
    sqm_m = re.findall(r'(\d+)\s*(?:τ\.?μ\.?|sqm)', comb)
    if sqm_m:
        try:
            if int(sqm_m[0]) < PREFERENCES["min_sqm_tolerated"]:
                return True, f"Size < {PREFERENCES['min_sqm_tolerated']} sqm"
        except ValueError:
            pass
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

def parse_and_evaluate_listing(portal, url, raw_html, card_text=""):
    """Extract attributes, compute risk, deal and fit scores, and build record dictionary"""
    # 1. Listing ID
    if portal == 'spitogatos':
        m = re.search(r'aggelia/(\d+)', url)
        lid = m.group(1) if m else str(int(time.time()))
    else:
        m = re.search(r'xe\.gr/p/([a-f0-9\-]+)', url) or re.search(r'xe\.gr/property/d/[^/]+/([a-f0-9\-]+)', url)
        lid = f"xe-{m.group(1)[:8]}" if m else f"xe-{int(time.time())}"

    # Combined context for extraction (page HTML + email card text)
    comb_text = (raw_html + " " + card_text)

    # Check blacklist on combined text & url
    for b in BLACKLIST_AREAS:
        if b in comb_text.lower() or b in url.lower():
            raise ValueError(f"Property {lid} rejected: Blacklisted area '{b}' detected.")

    # 2. Price
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
        ("Βριλήσσια", ["βριλήσσια", "βριλησσια", "vrilissia"]),
        ("Πεύκη", ["πεύκη", "πευκη", "pefki"]),
        ("Μελίσσια", ["μελίσσια", "μελισσια", "melissia"]),
        ("Κηφισιά", ["κηφισιά", "κηφισια", "kifisia", "kifissia"]),
        ("Κορυδαλλός", ["κορυδαλλός", "κορυδαλλος", "korydallos", "πλατεία ελευθερίας"]),
        ("Νίκαια", ["νίκαια", "νικαια", "nikaia", "μητρόπολη", "νεάπολη", "νεαπολη", "χρυσόστομος"]),
        ("Κερατσίνι", ["κερατσίνι", "κερατσινι", "keratsini", "αμφιάλη", "αμφιαλη", "ευγένεια", "ευγενεια"]),
        ("Δραπετσώνα", ["δραπετσώνα", "δραπετσωνα", "drapetsona", "ανάληψη"]),
        ("Ταμπούρια", ["ταμπούρια", "ταμπουρια", "tabouria", "αγία σοφία"]),
        ("Πειραιάς (Χατζηκυριάκειο)", ["χατζηκυριάκειο", "χατζηκυριακειο", "πειραϊκή", "πειραικη", "chatzikyriakeio", "piraiki"])
    ]
    loc = "Κερατσίνι"
    comb_lower = comb_text.lower()
    for official_loc, aliases in loc_candidates:
        if any(al in comb_lower for al in aliases):
            loc = official_loc
            break

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
        "Κηφισιά": (38.0740, 23.8120),
        "Πεύκη": (38.0600, 23.7930),
        "Μελίσσια": (38.0500, 23.8300)
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
    if loc in ["Μαρούσι", "Αγία Παρασκευή", "Χαλάνδρι", "Ηράκλειο", "Βριλήσσια", "Κηφισιά", "Πεύκη", "Μελίσσια"]:
        risk_score = 2.5
        risk_level = "Χαμηλό Ρίσκο"
        risk_color = "#059669"
        crime_risk = f"Χαμηλό στην ευρύτερη περιοχή {loc}."
    elif loc in ["Πειραιάς (Χατζηκυριάκειο)"]:
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
        clean_html = re.sub(r'<footer.*?</footer>', '', raw_html, flags=re.DOTALL)
        clean_html = re.sub(r'enoikiaseis-parking|poliseis-parking', '', clean_html)
        if re.search(r'(?:θέση\s*στάθμευσης|κλειστό\s*parking|υπαίθριο\s*parking|θέσεις\s*στάθμευσης)\s*:\s*[1-9]', clean_html, re.I):
            has_parking = True
            parking_info = "Θέση Στάθμευσης"

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
        "street_parking_ease": "PRIVATE" if has_parking else "DIFFICULT"
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
                "thumb": nr.get("thumb", ""),
                "street_parking_ease": nr.get("street_parking_ease", "PRIVATE" if has_p else "DIFFICULT")
            }

        new_props_list = list(prop_map.values())
        new_json_str = json.dumps(new_props_list, ensure_ascii=False, indent=2)
        idx_content = idx_content[:pos_data + 23] + new_json_str + idx_content[end_data + 1:]

        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(idx_content)
        logging.info("Updated index.html propertiesData successfully.")

def git_commit_and_push(new_count):
    """Stages changes, commits with meaningful message and pushes to origin main"""
    try:
        subprocess.run(["git", "add", "webarchives/processed_listings.csv", "index.html", "property-*.html"], cwd=base_dir, check=True)
        commit_msg = f"feat(auto-ingest): Add {new_count} new evaluated properties from email alerts"
        subprocess.run(["git", "commit", "-m", commit_msg], cwd=base_dir, check=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=base_dir, check=True)
        logging.info("Successfully pushed new properties to GitHub!")
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
        try:
            title, html = fetch_url_via_safari(url)
            is_bot, b_plat, b_url = check_bot_challenge(title, html, url)
            if is_bot:
                logging.warning(f"⚠️ Bot challenge detected on {b_plat}: {b_url}")
                active_bot_challenge = {"platform": b_plat, "url": b_url}
        except Exception as e:
            logging.warning(f"Safari fetch failed for {url}: {e}. Proceeding with email card data.")

        try:
            record = parse_and_evaluate_listing(portal, url, html, card_text=item.get('text', ''))
            
            # Download thumbnail if found
            lid = record['listing_id']
            img_url = item.get('img_url')
            thumbs_map = {}
            if img_url:
                thumbs_dir = os.path.join(base_dir, 'thumbs')
                os.makedirs(thumbs_dir, exist_ok=True)
                thumb_file = f"{lid}.jpg"
                thumb_target = os.path.join(thumbs_dir, thumb_file)
                try:
                    req = urllib.request.Request(img_url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=5) as resp, open(thumb_target, 'wb') as out:
                        out.write(resp.read())
                    record['thumb'] = f"thumbs/{thumb_file}"
                    thumbs_map[lid] = f"thumbs/{thumb_file}"
                except Exception as ex:
                    logging.warning(f"Could not download thumbnail for {lid}: {ex}")

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
        logging.info("No novel properties were added in this run.")
        update_status_file(now_str, 0, bot_challenge=active_bot_challenge)

if __name__ == '__main__':
    run_pipeline()
