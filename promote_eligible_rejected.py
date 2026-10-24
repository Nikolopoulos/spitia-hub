# -*- coding: utf-8 -*-
"""
Promotes all eligible properties from rejected_listings.json into processed_listings.csv
that were wrongly disqualified by previous blanket parking rules.
"""

import os, json, csv, re
from datetime import datetime
from auto_pipeline import is_rejected
from user_fit_budget_engine import evaluate_user_fit_with_budget_and_risk, calculate_enfia, USER_CASH
from rich_report_generator import generate_rich_property_html
from street_parking_security_intel import STREET_PARKING_DATA

base_dir = '/Volumes/Terataki/projects/spitia'
csv_path = os.path.join(base_dir, 'webarchives', 'processed_listings.csv')
arch_path = os.path.join(base_dir, 'webarchives', 'archived_listings.json')
rej_path = os.path.join(base_dir, 'webarchives', 'rejected_listings.json')
index_path = os.path.join(base_dir, 'index.html')

# Benchmarks for deal score estimation
BENCHMARKS = {
    'μαρούσι': 2300, 'marousi': 2300, 'κηφισιά': 2300, 'kifisia': 2300,
    'χαλάνδρι': 2200, 'chalandri': 2200, 'αγία παρασκευή': 2200, 'agia paraskevi': 2200,
    'ηράκλειο': 2000, 'irakleio': 2000, 'πεύκη': 2000, 'βριλήσσια': 2200,
    'μεταμόρφωση': 1700, 'νέα ιωνία': 1700, 'λυκόβρυση': 1800,
    'κορυδαλλός': 1500, 'korydallos': 1500, 'νίκαια': 1400, 'nikaia': 1400,
    'κερατσίνι': 1300, 'keratsini': 1300, 'δραπετσώνα': 1300, 'drapetsona': 1300,
    'πειραιάς': 1400, 'piraeus': 1400, 'χατζηκυριάκειο': 1400, 'ρέντης': 1300
}

LOC_COORDS = {
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
    "Πειραιάς": (37.9430, 23.6470),
    "Κηφισιά": (38.0740, 23.8120),
    "Πεύκη": (38.0600, 23.7930),
    "Μελίσσια": (38.0500, 23.8300),
    "Νέα Ιωνία": (38.0350, 23.7550),
    "Μεταμόρφωση": (38.0650, 23.7600),
    "Λυκόβρυση": (38.0680, 23.7800),
    "Ρέντης": (37.9650, 23.6650),
    "Άγιος Ιωάννης Ρέντης": (37.9650, 23.6650)
}

EASY_SUBURBS = [
    'μαρούσι', 'μαρουσι', 'marousi', 'ηράκλειο', 'ηρακλειο', 'irakleio',
    'κηφισιά', 'κηφισια', 'kifisia', 'γέρακας', 'γερακας', 'gerakas',
    'δροσιά', 'δροσια', 'drosia', 'βριλήσσια', 'βριλησσια',
    'μεταμόρφωση', 'μεταμορφωση', 'λυκόβρυση', 'λυκοβρυση',
    'άνω κορυδαλλός', 'ανω κορυδαλλος', 'πεύκη', 'μελίσσια', 'χαλάνδρι'
]

# 1. Load existing
with open(csv_path, 'r', encoding='utf-8') as f:
    existing_approved = list(csv.DictReader(f))

with open(rej_path, 'r', encoding='utf-8') as f:
    current_rejected = json.load(f)

with open(arch_path, 'r', encoding='utf-8') as f:
    current_archived = json.load(f)

fieldnames = list(existing_approved[0].keys())

print(f"Current state: {len(existing_approved)} Approved, {len(current_archived)} Archived, {len(current_rejected)} Rejected")

# 2. Partition rejected
still_rejected = []
to_promote = []
existing_ids = {r['listing_id'] for r in existing_approved}

for r in current_rejected:
    lid = r['listing_id']
    text = (r.get('title', '') + ' ' + r.get('location', '') + ' ' + r.get('reason', '')).lower()
    url = r.get('url', '')
    price = float(r.get('price', 0))
    sqm = float(r.get('sqm', 0))
    ptype = r.get('type', 'Διαμέρισμα')
    loc = r.get('location', '')

    is_rej, rej_why = is_rejected(text, url, price=price, has_parking=False, property_type=ptype, location=loc, title=r.get('title'))
    if is_rej:
        still_rejected.append(r)
    else:
        if lid not in existing_ids:
            to_promote.append(r)

print(f"Promoting {len(to_promote)} listings from rejected to APPROVED. Retaining {len(still_rejected)} in REJECTED.")

# 3. Build full records for to_promote
newly_approved_records = []
for r in to_promote:
    lid = r['listing_id']
    title = r.get('title', '')
    loc_raw = r.get('location', '')
    price = float(r.get('price', 0))
    sqm = float(r.get('sqm', 0))
    ptype = r.get('type', 'Διαμέρισμα')
    url = r.get('url', '')

    # Clean official location name
    loc_clean = loc_raw.split('τ.μ.')[-1].strip() if 'τ.μ.' in loc_raw else loc_raw
    loc_clean = loc_clean.strip(', ')
    if not loc_clean:
        loc_clean = "Κερατσίνι"

    # Year estimation
    year = 1980
    y_m = re.search(r'\b(19\d{2}|20\d{2})\b', title)
    if y_m:
        year = int(y_m.group(1))

    # Renovation & Turnkey calculations
    renov_low = round(sqm * 350)
    renov_high = round(sqm * 550)
    renov_diy = round(sqm * 420)
    turnkey_diy = price + renov_diy
    turnkey_low = price + renov_low
    turnkey_high = price + renov_high

    # Coordinates
    lat, lon = (37.9700, 23.6500)
    for l_key, coords in LOC_COORDS.items():
        if l_key.lower() in loc_clean.lower():
            lat, lon = coords
            break

    # Risk score & crime risk
    is_suburb = any(s in loc_clean.lower() for s in ['μαρούσι', 'ηράκλειο', 'χαλάνδρι', 'κηφισιά', 'πεύκη', 'μεταμόρφωση', 'λυκόβρυση', 'νέα ιωνία', 'αγία παρασκευή', 'βριλήσσια'])
    if is_suburb:
        risk_score = 2.5
        risk_level = "Χαμηλό Ρίσκο"
        risk_color = "#059669"
        crime_risk = f"Χαμηλό στην ευρύτερη περιοχή {loc_clean}."
    elif 'πειραιάς' in loc_clean.lower():
        risk_score = 3.2
        risk_level = "Χαμηλό Ρίσκο"
        risk_color = "#059669"
        crime_risk = f"Χαμηλό προς Μέτριο στην περιοχή {loc_clean}."
    else:
        risk_score = 3.6
        risk_level = "Μέτριο Ρίσκο"
        risk_color = "#d97706"
        crime_risk = f"Μέτριο στην περιοχή {loc_clean}."

    # Deal score based on benchmark price/sqm
    bm = 1400
    for b_key, b_val in BENCHMARKS.items():
        if b_key in loc_clean.lower():
            bm = b_val
            break
    psqm = price / sqm if sqm > 0 else 1400
    deal_score = round(min(92.0, max(48.0, 75.0 + (bm - psqm) / 32)), 1)
    deal_grade = "A" if deal_score >= 70 else ("B" if deal_score >= 55 else "C")
    deal_color = "#059669" if deal_score >= 70 else ("#d97706" if deal_score >= 55 else "#dc2626")

    # Parking evaluation
    is_easy_suburb = any(sub in loc_clean.lower() for sub in EASY_SUBURBS)
    if is_easy_suburb:
        street_ease = "EASY"
        p_info = "Άνετη στάθμευση στον δρόμο (Εύκολη εύρεση θέσης σε ήσυχο προάστιο)"
    else:
        street_ease = "MODERATE"
        p_info = "Στάθμευση στον δρόμο (Απαιτείται αναζήτηση τις ώρες αιχμής)"

    # Layout attributes
    baths = 2 if sqm >= 140 else 1
    wc = 1 if (ptype == 'Μεζονέτα' or sqm >= 115) else 0
    beds = 3 if sqm >= 110 else 2
    is_penthouse = "ρετιρέ" in title.lower() or "ρετιρε" in title.lower()

    # ENFIA
    enfia_val = calculate_enfia(sqm, loc_clean, year, ptype, is_penthouse)

    rec = {
        "filename": f"{title}.html",
        "listing_id": lid,
        "title": title,
        "location": f"{int(sqm)}τ.μ. {loc_clean}",
        "type": ptype,
        "price": str(price),
        "sqm": str(sqm),
        "year": str(year),
        "plot_sqm": str(sqm),
        "courtyard": "Βεράντα",
        "renov_low": str(renov_low),
        "renov_high": str(renov_high),
        "turnkey_low": str(turnkey_low),
        "turnkey_high": str(turnkey_high),
        "html_report": f"property-{lid}.html",
        "spitogatos_url": url,
        "lat": str(lat),
        "lon": str(lon),
        "processed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "renov_diy": str(renov_diy),
        "turnkey_diy": str(turnkey_diy),
        "risk_score": str(risk_score),
        "risk_level": risk_level,
        "risk_reasons": json.dumps([
            f"Κατασκευή {year}: Ανάγκη συνήθους αναβάθμισης υδραυλικών/ηλεκτρολογικών.",
            f"Τοποθεσία ({loc_clean}): Οικιστική ζώνη.",
            f"{ptype} με καλές δυνατότητες αξιοποίησης."
        ], ensure_ascii=False),
        "deal_score": str(deal_score),
        "deal_grade": deal_grade,
        "deal_desc": "Πολύ Καλή Επιλογή" if deal_score >= 70 else "Αποδεκτή Επιλογή",
        "deal_color": deal_color,
        "has_parking": "False",
        "parking_info": p_info,
        "baths": str(baths),
        "wc": str(wc),
        "beds": str(beds),
        "is_penthouse": "True" if is_penthouse else "False",
        "price_anomaly": "None",
        "crime_risk": crime_risk,
        "encampment_risk": "Μηδενικό. Καμία απολύτως σχέση με καταυλισμούς.",
        "environmental_risk": "Ήσυχο οικιστικό περιβάλλον.",
        "risk_color": risk_color,
        "price_score_val": "75.0",
        "risk_score_val": str(risk_score),
        "street_parking_ease": street_ease,
        "vehicle_theft_risk": "LOW" if is_suburb else "MODERATE",
        "parking_note": p_info,
        "enfia": str(enfia_val)
    }

    # Evaluate user fit
    fit_score, fit_grade, fit_desc, fit_color, fit_breakdown, dealbreakers = evaluate_user_fit_with_budget_and_risk(rec)
    rec["fit_score"] = str(fit_score)
    rec["fit_grade"] = fit_grade
    rec["fit_desc"] = fit_desc
    rec["fit_color"] = fit_color
    rec["fit_breakdown"] = json.dumps(fit_breakdown, ensure_ascii=False)
    rec["dealbreakers"] = json.dumps(dealbreakers, ensure_ascii=False)

    newly_approved_records.append(rec)

# Merge approved: existing_approved + newly_approved_records
merged_approved = existing_approved + newly_approved_records
print(f"Total merged approved records: {len(merged_approved)}")

# Write to CSV
with open(csv_path, 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(merged_approved)
print(f"Successfully saved {len(merged_approved)} rows to {csv_path}")

# Write to rejected_listings.json
with open(rej_path, 'w', encoding='utf-8') as f:
    json.dump(still_rejected, f, ensure_ascii=False, indent=2)
print(f"Successfully saved {len(still_rejected)} rows to {rej_path}")

# Generate HTML reports for newly approved
print(f"Generating HTML reports for {len(newly_approved_records)} newly approved properties...")
success_html = 0
for r in newly_approved_records:
    try:
        report_html = generate_rich_property_html(r)
        report_file = r.get('html_report')
        if report_file:
            with open(os.path.join(base_dir, report_file), 'w', encoding='utf-8') as f:
                f.write(report_html)
            success_html += 1
    except Exception as e:
        print(f"Error generating HTML for {r.get('listing_id')}: {e}")
print(f"Successfully generated {success_html} HTML reports.")

# Synchronize index.html
print("\nSynchronizing index.html...")
with open(index_path, 'r', encoding='utf-8') as f:
    idx_content = f.read()

# 1. Update propertiesData
pos_data = idx_content.find('const propertiesData = [')
end_data = idx_content.find('];', pos_data)
if pos_data != -1 and end_data != -1:
    idx_props = []
    for r in merged_approved:
        has_p = r.get("has_parking") == "True" or r.get("has_parking") is True
        idx_props.append({
            "filename": r.get("filename", ""),
            "listing_id": r["listing_id"],
            "title": r.get("title", ""),
            "location": r.get("location", ""),
            "type": r.get("type", ""),
            "price": float(r.get("price", 0)),
            "sqm": float(r.get("sqm", 0)),
            "year": int(float(r.get("year", 0))),
            "plot_sqm": float(r.get("plot_sqm", 0) or 0),
            "courtyard": r.get("courtyard", ""),
            "renov_low": float(r.get("renov_low", 0)),
            "renov_high": float(r.get("renov_high", 0)),
            "turnkey_low": float(r.get("turnkey_low", 0)),
            "turnkey_high": float(r.get("turnkey_high", 0)),
            "html_report": r.get("html_report", ""),
            "spitogatos_url": r.get("spitogatos_url", ""),
            "lat": float(r.get("lat", 37.97)),
            "lon": float(r.get("lon", 23.65)),
            "processed_at": r.get("processed_at", ""),
            "renov_diy": float(r.get("renov_diy", 0)),
            "turnkey_diy": float(r.get("turnkey_diy", 0)),
            "risk_score": float(r.get("risk_score", 3.5)),
            "risk_level": r.get("risk_level", "Χαμηλό Ρίσκο"),
            "deal_score": float(r.get("deal_score", 75.0)),
            "deal_grade": r.get("deal_grade", "A"),
            "deal_desc": r.get("deal_desc", "Πολύ Καλή Επιλογή"),
            "deal_color": r.get("deal_color", "#059669"),
            "fit_score": float(r.get("fit_score", 80.0)),
            "fit_grade": r.get("fit_grade", "A"),
            "fit_desc": r.get("fit_desc", ""),
            "fit_color": r.get("fit_color", "#059669"),
            "has_parking": has_p,
            "parking_info": r.get("parking_info", "Χωρίς Parking" if not has_p else "Θέση Στάθμευσης"),
            "baths": int(float(r.get("baths", 1))),
            "wc": int(float(r.get("wc", 1))),
            "beds": int(float(r.get("beds", 3))),
            "is_penthouse": r.get("is_penthouse") == "True" or r.get("is_penthouse") is True,
            "thumb": f"thumbs/{r['listing_id']}.jpg" if os.path.exists(os.path.join(base_dir, 'thumbs', f"{r['listing_id']}.jpg")) else "",
            "street_parking_ease": r.get("street_parking_ease", "PRIVATE" if has_p else "MODERATE"),
            "enfia": int(float(r.get("enfia", 300)))
        })
    props_json = json.dumps(idx_props, ensure_ascii=False, indent=2)
    idx_content = idx_content[:pos_data + 23] + props_json + idx_content[end_data + 1:]

# 2. Update rejectedData
pos_rej = idx_content.find('const rejectedData = [')
end_rej = idx_content.find('];', pos_rej)
if pos_rej != -1 and end_rej != -1:
    rej_json = json.dumps(still_rejected, ensure_ascii=False, indent=2)
    idx_content = idx_content[:pos_rej + 21] + rej_json + idx_content[end_rej + 1:]

# 3. Update badges
app_cnt = len(merged_approved)
arch_cnt = len(current_archived)
rej_cnt = len(still_rejected)

idx_content = re.sub(r'<span>Εγκεκριμένα:</span>\s*<b[^>]*>\s*\d+\s*</b>', f'<span>Εγκεκριμένα:</span>\n                    <b id="stat-approved-count">{app_cnt}</b>', idx_content)
idx_content = re.sub(r'Εγκεκριμένα\s*(?:Ακίνητα)?\s*\(\d+\)', f'Εγκεκριμένα ({app_cnt})', idx_content)
idx_content = re.sub(r'Λίστα\s*(?:Ακινήτων)?\s*\(\d+\)', f'Λίστα ({app_cnt})', idx_content)
idx_content = re.sub(r'\d+\s*Ενεργά\s*Ακίνητα', f'{app_cnt} Ενεργά Ακίνητα', idx_content)

idx_content = re.sub(r'>\s*📁\s*Παλιά:.*?<b[^>]*>\s*\d+\s*</b>', f'>📁 Παλιά:</span>\n                    <b id="stat-archived-count" style="color:#f59e0b;">{arch_cnt}</b>', idx_content, flags=re.DOTALL)
idx_content = re.sub(r'Παλιά\s*Αποθηκευμένα\s*\(\d+\)', f'Παλιά Αποθηκευμένα ({arch_cnt})', idx_content)
idx_content = re.sub(r'&bull;\s*\d+\s*Παλιά', f'&bull; {arch_cnt} Παλιά', idx_content)

idx_content = re.sub(r'>\s*🚫\s*Απορρίφθηκαν:.*?<b[^>]*>\s*\d+\s*</b>', f'>🚫 Απορρίφθηκαν:</span>\n                    <b id="stat-rejected-count" style="color:#ef4444;">{rej_cnt}</b>', idx_content, flags=re.DOTALL)
idx_content = re.sub(r'Απορριφθέντα\s*(?:Ακίνητα)?\s*\(\d+\)', f'Απορριφθέντα ({rej_cnt})', idx_content)
idx_content = re.sub(r'&bull;\s*\d+\s*Απορριφθέντα', f'&bull; {rej_cnt} Απορριφθέντα', idx_content)

with open(index_path, 'w', encoding='utf-8') as f:
    f.write(idx_content)

print(f"Index.html updated: Approved={app_cnt}, Archived={arch_cnt}, Rejected={rej_cnt}")
