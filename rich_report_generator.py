#!/usr/bin/env python3
"""
Full Rich Report Generator for Property Listings
Produces the identical in-depth 3-tier budget, engineering permits,
viewing guide checklists, user fit, risk breakdown, and image galleries.
"""

import os, json, csv, re, base64

def generate_rich_property_html(record, thumbs_map=None):
    """
    Builds the complete, rich engineering and financial report matching
    the master property format.
    """
    lid = record['listing_id']
    title = record['title']
    loc = record.get('location', '')
    ptype = record.get('type', 'Μονοκατοικία')
    price = int(float(record.get('price', 150000)))
    sqm = int(float(record.get('sqm', 120)))
    year = int(float(record.get('year', 1975))) if str(record.get('year', '')).isdigit() else 1975
    url = record.get('spitogatos_url', '')

    transfer_fees = int(price * 0.08)
    r_low = int(float(record.get('renov_low', sqm * 350)))
    r_high = int(float(record.get('renov_high', sqm * 550)))
    r_cash = int(float(record.get('renov_diy', sqm * 420)))

    is_multi_unit = "2 σπίτια" in title.lower() or "ενοποίηση" in title.lower() or ("μονοκατοικία" in ptype.lower() and sqm >= 120 and year < 1975)

    # Breakdown calculations
    permits_low = int(8500 if is_multi_unit else 3500)
    permits_high = int(14000 if is_multi_unit else 6500)
    permits_cash = permits_low

    demo_low = int(r_low * 0.12)
    demo_high = int(r_high * 0.12)
    demo_cash = int(demo_low * 0.65)

    drywall_low = int(r_low * 0.10)
    drywall_high = int(r_high * 0.10)
    drywall_cash = int(drywall_low * 0.70)

    elec_low = int(r_low * 0.14)
    elec_high = int(r_high * 0.14)
    elec_cash = int(elec_low * 0.80)

    plumb_low = int(r_low * 0.16)
    plumb_high = int(r_high * 0.16)
    plumb_cash = int(plumb_low * 0.70)

    insul_low = int(r_low * 0.18)
    insul_high = int(r_high * 0.18)
    insul_cash = int(insul_low * 0.90)

    hvac_low = int(r_low * 0.15)
    hvac_high = int(r_high * 0.15)
    hvac_cash = int(hvac_low * 0.95)

    carp_low = int(r_low * 0.15)
    carp_high = int(r_high * 0.15)
    carp_cash = int(carp_low * 0.70)

    tot_low = permits_low + demo_low + drywall_low + elec_low + plumb_low + insul_low + hvac_low + carp_low
    tot_high = permits_high + demo_high + drywall_high + elec_high + plumb_high + insul_high + hvac_high + carp_high
    tot_cash = permits_cash + demo_cash + drywall_cash + elec_cash + plumb_cash + insul_cash + hvac_cash + carp_cash

    turnkey_cash = price + transfer_fees + tot_cash
    turnkey_low = price + transfer_fees + tot_low
    turnkey_high = price + transfer_fees + tot_high

    # Fit & Risk
    fit_score = record.get('fit_score', '80.0')
    fit_grade = record.get('fit_grade', 'A')
    fit_desc = record.get('fit_desc', 'Πολύ Καλό Ταίριασμα')
    fit_color = record.get('fit_color', '#059669')

    fit_items = []
    try:
        raw_fb = record.get('fit_breakdown', '[]')
        fit_items = json.loads(raw_fb) if raw_fb else []
    except Exception:
        pass
    fit_items_html = "".join([f"<li style='margin-bottom:6px;'>{it}</li>" for it in fit_items])

    risk_score = record.get('risk_score', '3.5')
    risk_level = record.get('risk_level', 'Χαμηλό Ρίσκο')
    risk_color = record.get('risk_color', '#059669')

    risk_reasons = []
    try:
        raw_rr = record.get('risk_reasons', '[]')
        risk_reasons = json.loads(raw_rr) if raw_rr else []
    except Exception:
        pass
    risk_reasons_html = "".join([f"<li style='margin-bottom:8px;'>{r}</li>" for r in risk_reasons])

    # Gallery image
    thumb_path = (thumbs_map or {}).get(lid, '')
    gallery_html = ""
    if thumb_path and os.path.exists(thumb_path):
        gallery_html = f'''
        <div class="card">
            <h2>📸 Φωτογραφίες Ακινήτου</h2>
            <div class="gallery">
                <div class="photo-card">
                    <img src="{os.path.basename(thumb_path) if '/' not in thumb_path else thumb_path}" alt="{title}" loading="lazy" />
                    <p class="photo-cap">Πρόσοψη / Κύρια όψη ακινήτου</p>
                </div>
            </div>
        </div>
        '''

    html_code = f'''<!DOCTYPE html>
<html lang="el">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Τεχνική & Οικονομική Μελέτη: {title} ({lid})</title>
    <style>
        :root {{
            --primary: #1e3a8a;
            --primary-light: #2563eb;
            --accent: #f59e0b;
            --danger: #dc2626;
            --success: #16a34a;
            --bg: #f8fafc;
            --card-bg: #ffffff;
            --text-main: #0f172a;
            --text-muted: #64748b;
            --border: #e2e8f0;
            --cash-green: #047857;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: var(--bg);
            color: var(--text-main);
            line-height: 1.6;
            padding: 24px;
        }}
        .container {{ max-width: 1100px; margin: 0 auto; }}
        .nav-back {{
            display: inline-flex; align-items: center; gap: 6px; color: var(--primary-light);
            text-decoration: none; font-weight: 700; font-size: 0.9rem; margin-bottom: 16px;
        }}
        .nav-back:hover {{ text-decoration: underline; }}
        header {{
            background: linear-gradient(135deg, #1e3a8a 0%, #0f172a 100%);
            color: white; padding: 32px; border-radius: 16px; margin-bottom: 24px;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.1);
        }}
        .badge {{
            display: inline-block; background: #dbeafe; color: #1e40af; font-weight: 600;
            font-size: 0.85rem; padding: 4px 12px; border-radius: 9999px; margin-bottom: 12px;
        }}
        h1 {{ font-size: 1.85rem; margin-bottom: 8px; line-height: 1.3; }}
        .header-meta {{
            display: flex; flex-wrap: wrap; gap: 16px; font-size: 0.95rem; color: #cbd5e1; margin-top: 12px;
        }}
        .spitogatos-btn {{
            display: inline-flex; align-items: center; gap: 8px; background: #f59e0b; color: #111827;
            font-weight: 700; text-decoration: none; padding: 10px 20px; border-radius: 8px; margin-top: 16px;
        }}
        .grid-stats {{
            display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px;
        }}
        .stat-card {{
            background: var(--card-bg); padding: 18px; border-radius: 12px; border: 1px solid var(--border); text-align: center;
        }}
        .stat-val {{ font-size: 1.5rem; font-weight: 800; color: var(--primary); }}
        .stat-val-cash {{ color: var(--cash-green) !important; }}
        .stat-lbl {{ font-size: 0.82rem; color: var(--text-muted); text-transform: uppercase; font-weight: 600; margin-top: 4px; }}
        .card {{
            background: var(--card-bg); border-radius: 16px; border: 1px solid var(--border); padding: 28px; margin-bottom: 24px;
        }}
        .card h2 {{
            font-size: 1.35rem; color: var(--primary); margin-bottom: 16px; border-bottom: 2px solid #f1f5f9; padding-bottom: 10px;
        }}
        .gallery {{
            display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; margin: 16px 0;
        }}
        .photo-card {{
            background: #f1f5f9; border-radius: 10px; overflow: hidden; border: 1px solid var(--border);
        }}
        .photo-card img {{ width: 100%; height: 260px; object-fit: cover; display: block; }}
        .photo-cap {{ padding: 10px; font-size: 0.85rem; color: var(--text-muted); }}

        /* Table & Permit Badges */
        table {{ width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 0.92rem; }}
        th, td {{ padding: 12px 14px; text-align: left; border-bottom: 1px solid var(--border); }}
        th {{ background: #f8fafc; font-weight: 700; color: var(--primary); }}
        .badge-permit {{
            display: inline-block; font-size: 0.72rem; font-weight: 700; padding: 3px 8px; border-radius: 6px;
        }}
        .permit-required {{ background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; }}
        .permit-free {{ background: #dcfce7; color: #166534; border: 1px solid #86efac; }}
        .permit-mixed {{ background: #fef3c7; color: #92400e; border: 1px solid #fcd34d; }}
        
        .total-row {{ font-weight: 800; background: #f0fdf4 !important; color: #166534; font-size: 1.05rem; }}
        
        .permit-note-box {{
            background: #f0fdf4; border-left: 4px solid #059669; border-radius: 8px; padding: 16px; margin-bottom: 20px;
            font-size: 0.9rem; line-height: 1.6; color: #064e3b;
        }}
        .permit-note-title {{ font-weight: 800; margin-bottom: 4px; display: flex; align-items: center; gap: 6px; }}
        
        .footer {{ text-align: center; font-size: 0.85rem; color: var(--text-muted); margin-top: 36px; padding-bottom: 24px; }}
    </style>
</head>
<body>
    <div class="container">
        <a href="index.html" class="nav-back">← Επιστροφή στο Master Hub Ακινήτων</a>
        <header>
            <span class="badge">Μελέτη Εκμοντερνισμού 2026 &bull; 3-Tier Budget Analysis</span>
            <h1>{title}</h1>
            <div class="header-meta">
                <span>📍 {loc}</span>
                <span>📅 Έτος: {year}</span>
                <span>📐 Επιφάνεια: {sqm} τ.μ.</span>
                <span>🏷️ Τύπος: {ptype}</span>
            </div>
            <a href="{url}" target="_blank" class="spitogatos-btn">
                🔗 Άνοιγμα Αγγελίας στο Portal (ID: {lid})
            </a>
        </header>

        <div class="grid-stats">
            <div class="stat-card">
                <div class="stat-val">€{price:,}</div>
                <div class="stat-lbl">Τιμή Πώλησης</div>
            </div>
            <div class="stat-card">
                <div class="stat-val stat-val-cash">€{turnkey_cash:,}</div>
                <div class="stat-lbl">Turnkey (Μαύρα / Friends)</div>
            </div>
            <div class="stat-card">
                <div class="stat-val">€{turnkey_low:,}</div>
                <div class="stat-lbl">Turnkey (Standard Low)</div>
            </div>
            <div class="stat-card">
                <div class="stat-val">€{turnkey_high:,}</div>
                <div class="stat-lbl">Turnkey (High-End 2026)</div>
            </div>
        </div>

        <!-- User Fit Match Card -->
        <div class="card" style="border: 2px solid {fit_color}; background: #fcfdfd;">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
                <div>
                    <h2 style="margin: 0; border: none; padding: 0; color: {fit_color};">🎯 Προσωπικό Ταίριασμα: {fit_score} / 100</h2>
                    <p style="font-size: 0.88rem; color: var(--text-muted); margin-top: 4px;">{fit_desc}</p>
                </div>
                <div style="background: {fit_color}; color: white; padding: 8px 18px; border-radius: 12px; font-weight: 900; font-size: 1.3rem;">
                    Match: {fit_grade}
                </div>
            </div>
            <div style="margin-top: 14px; font-size: 0.88rem; color: #1e293b;">
                <ul style="list-style-type: none; padding-left: 0; line-height: 1.6;">
                    {fit_items_html}
                </ul>
            </div>
        </div>

        <!-- Risk Assessment Card -->
        <div class="card" style="border-left: 6px solid {risk_color};">
            <h2>🛡️ Ανάλυση Ρίσκου Ακινήτου & Περιοχής ({risk_score} / 10 - {risk_level})</h2>
            <ul style="line-height: 1.6; padding-left: 20px; color: #334155;">
                {risk_reasons_html}
            </ul>
        </div>

        {gallery_html}

        <div class="card">
            <h2>🏗️ Αναλυτικός Προϋπολογισμός Ανακαίνισης 2026 ανά Εργασία</h2>
            
            <div class="permit-note-box">
                <div class="permit-note-title">⚖️ Κανόνας Αδειοδότησης & Μαύρων (Strict Compliance)</div>
                Διαχωρισμός εργασιών σε υποχρεωτικά τιμολογημένες (άδειες, σκαλωσιές, εγγυήσεις αντλίας θερμότητας) και εργασίες με μεροκάματα χωρίς άδεια (γκρεμίσματα, πλακάκια, ξυλουργικά).
            </div>

            <table>
                <thead>
                    <tr>
                        <th>Κατηγορία Εργασίας</th>
                        <th>Καθεστώς Άδειας</th>
                        <th>💵 Μαύρα / Friends</th>
                        <th>📋 Standard Low</th>
                        <th>💎 High-End 2026</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td><strong>Άδειες, Μηχανικός & Έλεγχοι</strong><br><small style="color:var(--text-muted)">Άδεια Μικρής Κλίμακας / ΕΕΔΜΚ, επιβλέψεις</small></td>
                        <td><span class="badge-permit permit-required">⚖️ Υποχρεωτική Άδεια (0% Έκπτωση)</span></td>
                        <td><b>€{permits_cash:,}</b></td>
                        <td>€{permits_low:,}</td>
                        <td>€{permits_high:,}</td>
                    </tr>
                    <tr>
                        <td><strong>Καθαιρέσεις, Αποξηλώσεις & Μπάζα</strong><br><small style="color:var(--text-muted)">Γκρεμίσματα, απομάκρυνση παλαιών πλακιδίων</small></td>
                        <td><span class="badge-permit permit-free">💵 Χωρίς Άδεια (Μεροκάματο)</span></td>
                        <td><b>€{demo_cash:,}</b></td>
                        <td>€{demo_low:,}</td>
                        <td>€{demo_high:,}</td>
                    </tr>
                    <tr>
                        <td><strong>Γυψοσανίδες & Διαρρυθμίσεις</strong><br><small style="color:var(--text-muted)">Νέα χωρίσματα, ψευδοροφές, κρυφοί φωτισμοί</small></td>
                        <td><span class="badge-permit permit-free">💵 Χωρίς Άδεια (Μεροκάματο)</span></td>
                        <td><b>€{drywall_cash:,}</b></td>
                        <td>€{drywall_low:,}</td>
                        <td>€{drywall_high:,}</td>
                    </tr>
                    <tr>
                        <td><strong>Ηλεκτρολογική Εγκατάσταση</strong><br><small style="color:var(--text-muted)">Νέος πίνακας, καλωδιώσεις, πιστοποιητικό ΔΕΔΔΗΕ</small></td>
                        <td><span class="badge-permit permit-mixed">⚠️ Μικτό (Υποχρεωτικό Πιστοποιητικό)</span></td>
                        <td><b>€{elec_cash:,}</b></td>
                        <td>€{elec_low:,}</td>
                        <td>€{elec_high:,}</td>
                    </tr>
                    <tr>
                        <td><strong>Υδραυλικά & 2 Μπάνια/WC</strong><br><small style="color:var(--text-muted)">Νέες σωληνώσεις πολυστρωματικές, είδη υγιεινής</small></td>
                        <td><span class="badge-permit permit-free">💵 Χωρίς Άδεια (Φίλοι / Μεροκάματο)</span></td>
                        <td><b>€{plumb_cash:,}</b></td>
                        <td>€{plumb_low:,}</td>
                        <td>€{plumb_high:,}</td>
                    </tr>
                    <tr>
                        <td><strong>Κουφώματα & Θερμοπρόσοψη</strong><br><small style="color:var(--text-muted)">Σκαλωσιές εξωτερικά & εργοστασιακή εγγύηση αλουμινίων</small></td>
                        <td><span class="badge-permit permit-required">⚖️ Υποχρεωτική Άδεια (Σκαλωσιά / Εγγύηση)</span></td>
                        <td><b>€{insul_cash:,}</b></td>
                        <td>€{insul_low:,}</td>
                        <td>€{insul_high:,}</td>
                    </tr>
                    <tr>
                        <td><strong>HVAC (Αντλία Θερμότητας / AC)</strong><br><small style="color:var(--text-muted)">Επίσημη εγγύηση 5-10 ετών μηχανημάτων & τιμολόγια</small></td>
                        <td><span class="badge-permit permit-required">🛡️ Επίσημα (Εγγύηση Εισαγωγέα)</span></td>
                        <td><b>€{hvac_cash:,}</b></td>
                        <td>€{hvac_low:,}</td>
                        <td>€{hvac_high:,}</td>
                    </tr>
                    <tr>
                        <td><strong>Δάπεδα, Κουζίνα & Ξυλουργικά</strong><br><small style="color:var(--text-muted)">Πλακάκια, ντουλάπες, κουζίνα από γνωστό επιπλοποιό</small></td>
                        <td><span class="badge-permit permit-free">💵 Χωρίς Άδεια (Φίλοι / Μεροκάματο)</span></td>
                        <td><b>€{carp_cash:,}</b></td>
                        <td>€{carp_low:,}</td>
                        <td>€{carp_high:,}</td>
                    </tr>
                    <tr class="total-row">
                        <td colspan="2">ΣΥΝΟΛΟ ΑΝΑΚΑΙΝΙΣΗΣ 2026</td>
                        <td style="color:#047857; font-weight:900;">€{tot_cash:,}</td>
                        <td>€{tot_low:,}</td>
                        <td>€{tot_high:,}</td>
                    </tr>
                </tbody>
            </table>
        </div>

        <div class="card">
            <h2>📊 Τελική Επένδυση (Turnkey Analysis 3 Σεναρίων)</h2>
            <table>
                <thead>
                    <tr>
                        <th>Στοιχείο Κόστους</th>
                        <th>💵 Μαύρα / Friends</th>
                        <th>📋 Standard Low</th>
                        <th>💎 High-End 2026</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td><strong>Τιμή Αγοράς Ακινήτου</strong></td>
                        <td>€{price:,}</td>
                        <td>€{price:,}</td>
                        <td>€{price:,}</td>
                    </tr>
                    <tr>
                        <td><strong>Φόροι & Έξοδα Μεταβίβασης (~8%)</strong></td>
                        <td>€{transfer_fees:,}</td>
                        <td>€{transfer_fees:,}</td>
                        <td>€{transfer_fees:,}</td>
                    </tr>
                    <tr>
                        <td><strong>Κόστος Ανακαίνισης 2026</strong></td>
                        <td style="color:#047857; font-weight:700;">€{tot_cash:,}</td>
                        <td>€{tot_low:,}</td>
                        <td>€{tot_high:,}</td>
                    </tr>
                    <tr class="total-row">
                        <td>ΤΕΛΙΚΟ ΚΟΣΤΟΣ TURNKEY</td>
                        <td style="color:#047857; font-weight:900;">€{turnkey_cash:,}</td>
                        <td>€{turnkey_low:,}</td>
                        <td>€{turnkey_high:,}</td>
                    </tr>
                    <tr style="font-weight:700; color:var(--primary);">
                        <td>Τελικό Κόστος ανά τ.μ.</td>
                        <td style="color:#047857;">€{int(turnkey_cash/sqm):,} / τ.μ.</td>
                        <td>€{int(turnkey_low/sqm):,} / τ.μ.</td>
                        <td>€{int(turnkey_high/sqm):,} / τ.μ.</td>
                    </tr>
                </tbody>
            </table>
        </div>

        <div class="footer">
            Real Estate Hub &bull; Τεχνική & Οικονομική Μελέτη Ακινήτου &bull; 2026
        </div>
    </div>
</body>
</html>
'''
    return html_code
