# -*- coding: utf-8 -*-
"""
Execution script to re-evaluate and re-distribute properties across
Approved, Archived, and Rejected sets according to the updated criteria:
1. Hard reject any property with petty crime/theft, Roma/Gypsy encampments, scrap routes.
2. Allow properties up to €500,000 all-inclusive if they are good deals.
3. Critically evaluate parking in easy suburban areas without auto-disqualifying.
"""

import os, json, csv, re
from user_fit_budget_engine import evaluate_user_fit_with_budget_and_risk, calculate_enfia, calculate_mortgage_plan, USER_CASH
from rich_report_generator import generate_rich_property_html
from street_parking_security_intel import STREET_PARKING_DATA

base_dir = '/Volumes/Terataki/projects/spitia'
csv_path = os.path.join(base_dir, 'webarchives', 'processed_listings.csv')
arch_path = os.path.join(base_dir, 'webarchives', 'archived_listings.json')
rej_path = os.path.join(base_dir, 'webarchives', 'rejected_listings.json')
index_path = os.path.join(base_dir, 'index.html')

# 1. Load data
with open(csv_path, 'r', encoding='utf-8') as f:
    current_approved = list(csv.DictReader(f))

with open(arch_path, 'r', encoding='utf-8') as f:
    current_archived = json.load(f)

with open(rej_path, 'r', encoding='utf-8') as f:
    current_rejected = json.load(f)

print(f"Loaded: {len(current_approved)} approved, {len(current_archived)} archived, {len(current_rejected)} rejected")

# IDs of properties to hard reject due to crime / encampment / scrap routes
CRIME_SCRAP_REJECT_IDS = {
    '1117601164', # Kaminia - scrap, petty theft, vehicle/catalyst break-ins
    '1117965593', # Korydallos/Agia Varvara border - scrap, peddlers, petty theft
    '1119897356', # Keratsini - scrap dealers, peddlers, old vulnerable doors
    '1117657681', # Kato Amfiali - scrap, vulnerable 1960 house
    '1120173802', # Kokkinovrachos - Schisto foothills escape routes
    'xe-15010'    # Evgeneia - scrap trucks transit, break-in vulnerability
}

# Suburbs where street parking is easy/moderate and safe
EASY_SUBURBS = [
    'μαρούσι', 'μαρουσι', 'marousi', 'ηράκλειο', 'ηρακλειο', 'irakleio',
    'κηφισιά', 'κηφισια', 'kifisia', 'γέρακας', 'γερακας', 'gerakas',
    'δροσιά', 'δροσια', 'drosia', 'βριλήσσια', 'βριλησσια',
    'μεταμόρφωση', 'μεταμορφωση', 'λυκόβρυση', 'λυκοβρυση',
    'άνω κορυδαλλός', 'ανω κορυδαλλος', 'πεύκη', 'μελίσσια', 'χαλάνδρι'
]

# Separate approved into remaining vs rejected
remaining_approved = []
for p in current_approved:
    lid = str(p['listing_id'])
    if lid in CRIME_SCRAP_REJECT_IDS:
        print(f"Moving {lid} ({p.get('location')}) to REJECTED due to crime/scrap risk.")
        current_rejected.append({
            'listing_id': lid,
            'title': p.get('title', ''),
            'location': p.get('location', ''),
            'type': p.get('type', ''),
            'price': float(p.get('price', 0)),
            'sqm': float(p.get('sqm', 0)),
            'url': p.get('spitogatos_url', ''),
            'reason': "Απορρίφθηκε: Αυξημένη εγκληματικότητα / μικροκλοπές / γειτνίαση με άτυπους καταυλισμούς ή διαδρομές scrap"
        })
    else:
        remaining_approved.append(p)

# Clean up rejected_listings.json: un-reject 1121127864 (Kifisia 200m2 detached house)
cleaned_rejected = []
for r in current_rejected:
    if str(r.get('listing_id')) == '1121127864':
        print("Un-rejecting 1121127864 (Kifisia detached house mistakenly rejected for parking)")
        continue
    cleaned_rejected.append(r)
current_rejected = cleaned_rejected

# Inspect archived and identify those to promote
promoted_to_approved = []
remaining_archived = []

for p in current_archived:
    lid = str(p['listing_id'])
    price = float(p.get('price', 0))
    turnkey = float(p.get('turnkey_diy', p.get('turnkey_low', price)))
    reason = p.get('archive_reason', '')
    loc_l = (p.get('location', '') + ' ' + p.get('title', '')).lower()
    
    # Check if exceeds 500k ceiling
    if price > 500000:
        p['archive_reason'] = f"Υπέρβαση Ορίου Budget (€{int(price):,} > €500.000)"
        remaining_archived.append(p)
        continue

    # Check if Difficult street parking in Keratsini without private parking
    if 'Difficult Street' in reason and lid != 'xe-f02d4305':
        remaining_archived.append(p)
        continue

    # Otherwise, price <= 500,000 and good deal / good area -> PROMOTE!
    print(f"Promoting {lid} ({p.get('location')}, €{int(price):,}, Turnkey: €{int(turnkey):,}) to APPROVED")
    promoted_to_approved.append(p)

# Merge remaining_approved + promoted_to_approved
new_approved_pool = remaining_approved + promoted_to_approved

# Standardize fields and re-evaluate each approved property
all_approved_records = []
fieldnames = list(current_approved[0].keys())

for p in new_approved_pool:
    lid = str(p['listing_id'])
    price = float(p.get('price', 0))
    sqm = float(p.get('sqm', 0))
    year = int(float(p.get('year', 1980))) if str(p.get('year', '')).isdigit() else 1980
    ptype = p.get('type', 'Διαμέρισμα')
    loc = p.get('location', '')
    loc_l = (loc + ' ' + p.get('title', '')).lower()
    
    has_p = p.get('has_parking') == 'True' or p.get('has_parking') is True
    is_easy_suburb = any(sub in loc_l for sub in EASY_SUBURBS)
    
    # Parking Ease & Note
    if has_p:
        street_ease = "PRIVATE"
        p_info = p.get('parking_info', 'Ιδιωτική Θέση Στάθμευσης')
    elif lid in STREET_PARKING_DATA:
        s_data = STREET_PARKING_DATA[lid]
        street_ease = s_data['street_parking_ease']
        p_info = s_data['summary']
    elif is_easy_suburb:
        street_ease = "EASY"
        p_info = "Άνετη στάθμευση στον δρόμο (Εύκολη εύρεση θέσης σε ήσυχο προάστιο)"
    else:
        street_ease = "MODERATE"
        p_info = "Στάθμευση στον δρόμο (Απαιτείται αναζήτηση τις ώρες αιχμής)"

    p['has_parking'] = "True" if has_p else "False"
    p['parking_info'] = p_info
    p['street_parking_ease'] = street_ease
    
    # Recalculate ENFIA
    is_penth = p.get('is_penthouse') == 'True' or p.get('is_penthouse') is True or 'ρετιρέ' in loc_l
    enfia_val = calculate_enfia(sqm, loc, year, ptype, is_penth)
    p['enfia'] = str(enfia_val)
    
    # Re-evaluate user fit
    fit_score, fit_grade, fit_desc, fit_color, fit_breakdown, dealbreakers = evaluate_user_fit_with_budget_and_risk(p)
    p['fit_score'] = str(fit_score)
    p['fit_grade'] = fit_grade
    p['fit_desc'] = fit_desc
    p['fit_color'] = fit_color
    p['fit_breakdown'] = json.dumps(fit_breakdown, ensure_ascii=False)
    p['dealbreakers'] = json.dumps(dealbreakers, ensure_ascii=False)
    
    # Ensure default fields are present
    cleaned = {}
    for fn in fieldnames:
        cleaned[fn] = p.get(fn, "")
    cleaned['has_parking'] = "True" if has_p else "False"
    cleaned['is_penthouse'] = "True" if is_penth else "False"
    cleaned['enfia'] = str(enfia_val)
    cleaned['street_parking_ease'] = street_ease
    cleaned['parking_info'] = p_info
    cleaned['fit_score'] = str(fit_score)
    cleaned['fit_grade'] = fit_grade
    cleaned['fit_desc'] = fit_desc
    cleaned['fit_color'] = fit_color
    cleaned['fit_breakdown'] = json.dumps(fit_breakdown, ensure_ascii=False)
    cleaned['dealbreakers'] = json.dumps(dealbreakers, ensure_ascii=False)
    all_approved_records.append(cleaned)

# Re-evaluate remaining archived records
for p in remaining_archived:
    sqm = float(p.get('sqm', 0))
    year = int(float(p.get('year', 1980))) if str(p.get('year', '')).isdigit() else 1980
    ptype = p.get('type', 'Διαμέρισμα')
    loc = p.get('location', '')
    is_penth = p.get('is_penthouse') == 'True' or p.get('is_penthouse') is True or 'ρετιρέ' in loc.lower()
    p['enfia'] = calculate_enfia(sqm, loc, year, ptype, is_penth)
    fit_score, fit_grade, fit_desc, fit_color, fit_breakdown, dealbreakers = evaluate_user_fit_with_budget_and_risk(p)
    p['fit_score'] = fit_score
    p['fit_grade'] = fit_grade
    p['fit_desc'] = fit_desc
    p['fit_color'] = fit_color

print(f"\nFinal Distribution:")
print(f"  Approved: {len(all_approved_records)}")
print(f"  Archived: {len(remaining_archived)}")
print(f"  Rejected: {len(current_rejected)}")

# Write to CSV
with open(csv_path, 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(all_approved_records)
print("Updated processed_listings.csv successfully.")

# Write to archived_listings.json
with open(arch_path, 'w', encoding='utf-8') as f:
    json.dump(remaining_archived, f, ensure_ascii=False, indent=2)
print("Updated archived_listings.json successfully.")

# Write to rejected_listings.json
with open(rej_path, 'w', encoding='utf-8') as f:
    json.dump(current_rejected, f, ensure_ascii=False, indent=2)
print("Updated rejected_listings.json successfully.")

# Regenerate HTML reports for all approved and archived records
print("\nRegenerating HTML reports...")
for rec in all_approved_records + remaining_archived:
    try:
        report_html = generate_rich_property_html(rec)
        report_file = rec.get('html_report')
        if report_file:
            target_path = os.path.join(base_dir, report_file)
            with open(target_path, 'w', encoding='utf-8') as f:
                f.write(report_html)
    except Exception as e:
        print(f"Error generating report for {rec.get('listing_id')}: {e}")
print("HTML reports regenerated.")

# Synchronize index.html
print("\nSynchronizing index.html...")
with open(index_path, 'r', encoding='utf-8') as f:
    idx_content = f.read()

# 1. Update propertiesData
pos_data = idx_content.find('const propertiesData = [')
end_data = idx_content.find('];', pos_data)
if pos_data != -1 and end_data != -1:
    idx_props = []
    for r in all_approved_records:
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

# 2. Update archivedData
pos_arch = idx_content.find('const archivedData = [')
end_arch = idx_content.find('];', pos_arch)
if pos_arch != -1 and end_arch != -1:
    arch_json = json.dumps(remaining_archived, ensure_ascii=False, indent=2)
    idx_content = idx_content[:pos_arch + 21] + arch_json + idx_content[end_arch + 1:]

# 3. Update rejectedData
pos_rej = idx_content.find('const rejectedData = [')
end_rej = idx_content.find('];', pos_rej)
if pos_rej != -1 and end_rej != -1:
    rej_json = json.dumps(current_rejected, ensure_ascii=False, indent=2)
    idx_content = idx_content[:pos_rej + 21] + rej_json + idx_content[end_rej + 1:]

# 4. Update badge numbers
approved_cnt = len(all_approved_records)
archived_cnt = len(remaining_archived)
rejected_cnt = len(current_rejected)

idx_content = re.sub(r'<span>Εγκεκριμένα:</span>\s*<b[^>]*>\s*\d+\s*</b>', f'<span>Εγκεκριμένα:</span>\n                    <b id="stat-approved-count">{approved_cnt}</b>', idx_content)
idx_content = re.sub(r'Εγκεκριμένα\s*(?:Ακίνητα)?\s*\(\d+\)', f'Εγκεκριμένα ({approved_cnt})', idx_content)
idx_content = re.sub(r'Λίστα\s*(?:Ακινήτων)?\s*\(\d+\)', f'Λίστα ({approved_cnt})', idx_content)
idx_content = re.sub(r'\d+\s*Ενεργά\s*Ακίνητα', f'{approved_cnt} Ενεργά Ακίνητα', idx_content)

idx_content = re.sub(r'>\s*📁\s*Παλιά:.*?<b[^>]*>\s*\d+\s*</b>', f'>📁 Παλιά:</span>\n                    <b id="stat-archived-count" style="color:#f59e0b;">{archived_cnt}</b>', idx_content, flags=re.DOTALL)
idx_content = re.sub(r'Παλιά\s*Αποθηκευμένα\s*\(\d+\)', f'Παλιά Αποθηκευμένα ({archived_cnt})', idx_content)
idx_content = re.sub(r'&bull;\s*\d+\s*Παλιά', f'&bull; {archived_cnt} Παλιά', idx_content)

idx_content = re.sub(r'>\s*🚫\s*Απορρίφθηκαν:.*?<b[^>]*>\s*\d+\s*</b>', f'>🚫 Απορρίφθηκαν:</span>\n                    <b id="stat-rejected-count" style="color:#ef4444;">{rejected_cnt}</b>', idx_content, flags=re.DOTALL)
idx_content = re.sub(r'Απορριφθέντα\s*(?:Ακίνητα)?\s*\(\d+\)', f'Απορριφθέντα ({rejected_cnt})', idx_content)
idx_content = re.sub(r'&bull;\s*\d+\s*Απορριφθέντα', f'&bull; {rejected_cnt} Απορριφθέντα', idx_content)

with open(index_path, 'w', encoding='utf-8') as f:
    f.write(idx_content)

print(f"Updated index.html: Approved={approved_cnt}, Archived={archived_cnt}, Rejected={rejected_cnt}")
