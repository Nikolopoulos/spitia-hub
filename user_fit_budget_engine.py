# -*- coding: utf-8 -*-
"""
Budget, Loan Need, Neighborhood Risk & Adaptive User Fit Engine

User Requirements:
1. Available Equity: ~€180,000 cash in hand.
2. Loan Preference: Minimize or avoid bank mortgage completely.
   - If turnkey_diy <= 180,000: Zero mortgage needed! Full cash buy (+25 pts).
   - If turnkey_diy <= 220,000: Very small loan (<= €40,000) (+18 pts).
   - If turnkey_diy <= 280,000: Moderate loan (€40k - €100k) (+10 pts).
   - If turnkey_diy > 280,000: Heavy loan (> €100k).
     * EXCEPTION: If the property is a "Sensational Deal" (Risk <= 3.5 AND Deal Score >= 75.0),
       the user is explicitly open to a larger loan (+8 to +12 pts)!
     * Otherwise: Low score for heavy debt (+2 pts).
3. Neighborhood Risk Penalty:
   - High neighborhood risk directly penalizes the user match (up to -20 pts).
   - Low neighborhood risk (e.g. Marousi, Irakleio, Ano Korydallos) gets full points (+15 pts).
4. Physical & Layout Preferences:
   - Parking (25 pts): Private (25) or Easy street parking in safe area (18-20). Difficult street (0 + Dealbreaker).
   - Bathrooms (15 pts): 2+ baths/wc (15), 1 bath (0 + Dealbreaker).
   - Property Type (15 pts): Detached (15), Maisonette (12), Penthouse (10), Flat (4).
   - Bedrooms (10 pts): 3+ beds (10), 2 beds (5), 1 bed (0).
Total Max Base Points: 100.
"""

from street_parking_security_intel import STREET_PARKING_DATA

USER_CASH = 180000

def evaluate_user_fit_with_budget_and_risk(p):
    lid = p['listing_id']
    score = 0.0
    breakdown = []
    dealbreakers = []

    turnkey_cost = float(p.get('turnkey_diy', p.get('turnkey_low', p.get('price', 0))))
    loan_needed = max(0.0, turnkey_cost - USER_CASH)
    risk_score = float(p.get('risk_score', 5.0))
    deal_score = float(p.get('deal_score', 60.0))
    is_sensational = (risk_score <= 3.5 and deal_score >= 75.0)

    # -------------------------------------------------------------
    # 0. CRIME / ENCAMPMENT / PETTY THEFT HARD REJECT CHECK
    # -------------------------------------------------------------
    crime_txt = (str(p.get('crime_risk', '')) + " " + str(p.get('encampment_risk', '')) + " " + str(p.get('risk_reasons', ''))).lower()
    has_crime_risk = any(k in crime_txt for k in ['μικροκλοπ', 'μικροεγκληματικ', 'μικροπαραβατικ', 'καταυλισμ', 'τσιγκάν', 'τσιγγάν', 'γύφτ', 'scrap', 'πλανόδι', 'σχιστ', 'εμπόριο μετάλλων']) and (risk_score >= 4.0 or 'αυξημένο' in crime_txt or 'μέτριο προς αυξημένο' in crime_txt or 'θύλακες' in crime_txt)
    if has_crime_risk:
        dealbreakers.append("🚨 Απορρίπτεται: Αυξημένη εγκληματικότητα / μικροκλοπές / γειτνίαση με καταυλισμούς ή διαδρομές scrap")

    # -------------------------------------------------------------
    # 0b. AUCTION / SEIZURE / DISTRESSED ASSET HARD REJECT CHECK
    # -------------------------------------------------------------
    raw_desc = (str(p.get('title', '')) + " " + str(p.get('description', '')) + " " + str(p.get('risk_reasons', '')) + " " + str(p.get('spitogatos_url', ''))).lower()
    trans = str.maketrans("άέήίόύώϊϋΐΰΆΈΉΊΌΎΏΪΫ", "αεηιουωιυιυαεηιουωιυ")
    norm_desc = raw_desc.translate(trans)
    if any(k in norm_desc for k in ['πλειστηριασμ', 'πλειστηριαζ', 'εκπλειστηριασμ', 'eauction', 'e-auction', 'κατασχεσ', 'αναγκαστικη εκτελεσ', 'αναγκαστικη εκποιησ', 'πρωτης προσφορας', '1ης προσφορας', 'δημοπρασι']):
        dealbreakers.append("🚨 Απορρίπτεται: Πλειστηριασμός / Αναγκαστική εκτέλεση / Κατάσχεση")

    # -------------------------------------------------------------
    # 1. BUDGET & LOAN COMPONENT (25 pts max) - Ceiling up to €500k
    # -------------------------------------------------------------
    if loan_needed <= 0:
        b_pts = 25.0
        score += b_pts
        breakdown.append(f"💰 Ίδια Κεφάλαια / Χωρίς Δάνειο (+{int(b_pts)}/25): Τελικό turnkey €{int(turnkey_cost):,} καλύπτεται πλήρως από τα €180.000 μετρητά!")
    elif loan_needed <= 45000:
        b_pts = 19.0
        score += b_pts
        breakdown.append(f"💶 Ελάχιστο Δάνειο (+{int(b_pts)}/25): Απαιτείται μικρή χρηματοδότηση μόλις €{int(loan_needed):,} (πολύ χαμηλή μηνιαία δόση).")
    elif loan_needed <= 100000:
        b_pts = 13.0
        score += b_pts
        breakdown.append(f"🏦 Μεσαίο Δάνειο (+{int(b_pts)}/25): Απαιτείται δανεισμός €{int(loan_needed):,} πάνω από τα €180.000 μετρητά.")
    else: # Loan > 100,000
        # User allows up to €500k all-inclusive if it's a good deal
        if turnkey_cost <= 500000 and (deal_score >= 50.0 or risk_score <= 4.5):
            if is_sensational or (deal_score >= 70.0 and risk_score <= 4.0):
                b_pts = 14.0
                score += b_pts
                breakdown.append(f"⭐ Συνταρακτική Ευκαιρία &bull; Ανοιχτό σε Μεγαλύτερο Δάνειο (+{int(b_pts)}/25): Turnkey €{int(turnkey_cost):,} (Δάνειο €{int(loan_needed):,}), χαμηλό ρίσκο ({risk_score}/10) και κορυφαίο deal ({deal_score}/100) εντός του ορίου €500k!")
            else:
                b_pts = 10.0
                score += b_pts
                breakdown.append(f"🏦 Μεγαλύτερο Δάνειο Εντός Ορίου €500k (+{int(b_pts)}/25): Turnkey €{int(turnkey_cost):,} (Δάνειο €{int(loan_needed):,}) &bull; Αποδεκτό ως αξιόλογη ευκαιρία.")
        else:
            b_pts = 3.0
            score += b_pts
            dealbreakers.append(f"⚠️ Μεγάλο Δάνειο (> €{int(loan_needed):,}) ή υπέρβαση ορίου €500k")
            breakdown.append(f"📉 Υψηλό Δάνειο (+{int(b_pts)}/25): Απαιτείται βαρύς δανεισμός €{int(loan_needed):,} πάνω από το διαθέσιμο κεφάλαιο των €180.000.")

    # -------------------------------------------------------------
    # 2. NEIGHBORHOOD RISK & SAFETY COMPONENT (15 pts max)
    # -------------------------------------------------------------
    # Low risk (<= 3.0) -> 15 pts
    # Med risk (3.1 - 5.5) -> 9-11 pts
    # High risk (5.6 - 7.5) -> 4-6 pts
    # Extreme risk (> 7.5) -> 0 pts + Dealbreaker alert
    if risk_score <= 2.5:
        r_pts = 15.0
        score += r_pts
        breakdown.append(f"🛡️ Ασφαλής Γειτονιά & Ελάχιστο Ρίσκο (+{int(r_pts)}/15): Ήσυχη περιοχή με χαμηλό δείκτη κινδύνου ({risk_score}/10).")
    elif risk_score <= 4.0:
        r_pts = 12.0
        score += r_pts
        breakdown.append(f"🛡️ Ελεγχόμενο Ρίσκο Περιοχής (+{int(r_pts)}/15): Ικανοποιητικό επίπεδο ασφάλειας ({risk_score}/10).")
    elif risk_score <= 6.0:
        r_pts = 7.0
        score += r_pts
        breakdown.append(f"⚠️ Μέτριο/Αυξημένο Ρίσκο Περιοχής (+{int(r_pts)}/15): Χρειάζεται προσοχή σε τοπικούς παράγοντες/περιβάλλον ({risk_score}/10).")
    else:
        r_pts = 0.0
        score += r_pts
        dealbreakers.append(f"🚨 Υψηλό Ρίσκο Περιοχής/Κτιρίου ({risk_score}/10)")
        breakdown.append(f"🚨 Υψηλό Ρίσκο Περιοχής/Κτιρίου (0/15 - Ποινή): Σοβαροί κίνδυνοι ασφάλειας, παλαιότητας ή περιβάλλοντος ({risk_score}/10).")

    # -------------------------------------------------------------
    # 3. PARKING & VEHICLE THEFT (25 pts max) - Critical Judgment
    # -------------------------------------------------------------
    has_private = p.get('has_parking', 'False') == 'True' or p.get('has_parking') is True
    loc_l = (str(p.get('location', '')) + ' ' + str(p.get('title', ''))).lower()
    easy_suburbs = ['μαρούσι', 'μαρουσι', 'ηράκλειο', 'ηρακλειο', 'κηφισιά', 'κηφισια', 'γέρακας', 'γερακας', 'δροσιά', 'δροσια', 'βριλήσσια', 'βριλησσια', 'μεταμόρφωση', 'μεταμορφωση', 'λυκόβρυση', 'λυκοβρυση', 'άνω κορυδαλλός', 'ανω κορυδαλλος', 'πεύκη', 'πευκη', 'μελίσσια', 'μελισσια', 'χαλάνδρι', 'χαλανδρι']
    is_easy_area = any(sub in loc_l for sub in easy_suburbs)

    if has_private:
        p_pts = 25.0
        score += p_pts
        p_info = p.get('parking_info', 'Ιδιωτική Θέση Στάθμευσης')
        breakdown.append(f"✅ Ιδιωτική Θέση Στάθμευσης (+{int(p_pts)}/25): {p_info}")
    else:
        if lid in STREET_PARKING_DATA:
            s_data = STREET_PARKING_DATA[lid]
            if s_data['street_parking_ease'] == 'EASY':
                p_pts = 19.0
                score += p_pts
                breakdown.append(f"🟢 Στάθμευση στον Δρόμο (+{int(p_pts)}/25 - Αποδεκτό): {s_data['summary']}. Άνετοι δρόμοι, εύκολη εύρεση θέσης χωρίς καθημερινό άγχος.")
            elif s_data['street_parking_ease'] == 'MODERATE':
                p_pts = 14.0
                score += p_pts
                breakdown.append(f"🟡 Στάθμευση στον Δρόμο (+{int(p_pts)}/25 - Μέτριο): {s_data['summary']}. Βρίσκεις θέση με λίγο ψάξιμο.")
            else:
                p_pts = 0.0
                dealbreakers.append("❌ Χωρίς Parking & Οξύ Πρόβλημα Στάθμευσης/Κλοπών στον Δρόμο")
                breakdown.append(f"🔴 Χωρίς Parking (0/25 - Dealbreaker): {s_data['summary']}. Πολύ δύσκολη εύρεση θέσης & υψηλός κίνδυνος κλοπής οχημάτων/μηχανών.")
        elif is_easy_area:
            p_pts = 18.0
            score += p_pts
            breakdown.append(f"🟢 Στάθμευση στον Δρόμο (+{int(p_pts)}/25 - Ήσυχο Προάστιο): Εύκολη εύρεση θέσης στάθμευσης σε φαρδείς, ήσυχους δρόμους χωρίς πίεση.")
        else:
            # Urban area without private parking: penalize points, but do not auto-disqualify unless severe
            p_pts = 8.0
            score += p_pts
            breakdown.append(f"🟡 Χωρίς Ιδιωτικό Parking (+{int(p_pts)}/25 - Απαιτείται Έλεγχος): Έλλειψη ιδιωτικής θέσης, πιθανή δυσκολία στάθμευσης τις ώρες αιχμής.")

    # -------------------------------------------------------------
    # 4. BATHROOMS & WC (15 pts max)
    # -------------------------------------------------------------
    baths = int(p.get('baths', 1))
    wc = int(p.get('wc', 0))
    if (baths + wc) >= 2:
        bth_pts = 15.0
        score += bth_pts
        breakdown.append(f"✅ 2+ Μπάνια/WC (+{int(bth_pts)}/15): {baths} Μπάνιο/α + {wc} WC")
    else:
        dealbreakers.append("❌ Μόνο 1 Μπάνιο (Απαιτούνται 2+)")
        breakdown.append("❌ Μόνο 1 Μπάνιο (0/15)")

    # -------------------------------------------------------------
    # 5. PROPERTY TYPE & PENTHOUSE (15 pts max)
    # -------------------------------------------------------------
    ptype = p.get('type', '').lower()
    is_penthouse = p.get('is_penthouse', 'False') == 'True'
    if 'μονοκατοικία' in ptype:
        score += 15.0
        breakdown.append("💎 Μονοκατοικία (+15/15): Κορυφαία προτίμηση τύπου κατοικίας")
    elif 'μεζονέτα' in ptype:
        score += 12.0
        breakdown.append("✨ Μεζονέτα (+12/15): Υψηλή προτίμηση")
    elif 'συγκρότημα' in ptype:
        score += 11.0
        breakdown.append("✨ Συγκρότημα / Μεζονέτα (+11/15)")
    elif 'διαμέρισμα' in ptype:
        if is_penthouse:
            score += 10.0
            breakdown.append("🌟 Διαμέρισμα Ρετιρέ (+10/15): Προτιμητέος όροφος")
        else:
            score += 4.0
            breakdown.append("🏢 Απλό Διαμέρισμα (+4/15)")

    # -------------------------------------------------------------
    # 6. BEDROOMS (10 pts max)
    # -------------------------------------------------------------
    beds = int(p.get('beds', 2))
    if beds >= 3:
        score += 10.0
        breakdown.append(f"🛏️ {beds} Υπνοδωμάτια (+10/10): Υπερκαλύπτει την ανάγκη για 3 Υ/Δ")
    elif beds == 2:
        score += 5.0
        breakdown.append("🛏️ 2 Υπνοδωμάτια (+5/10): Επιθυμητά 3 Υ/Δ")
    else:
        breakdown.append("🛏️ 1 Υπνοδωμάτιο (0/10)")

    final_score = round(min(100.0, max(0.0, score)), 1)

    # Grades
    if final_score >= 85:
        grade = "A+"
        desc = "Ιδανικό Ταίριασμα &bull; Εντός budget ή συνταρακτικό deal & ασφαλής περιοχή"
        color = "#047857"
    elif final_score >= 70:
        grade = "A"
        desc = "Πολύ Καλό Ταίριασμα &bull; Καλύπτει ανάγκες, λογικό δάνειο & ελεγχόμενο ρίσκο"
        color = "#059669"
    elif final_score >= 55:
        grade = "B"
        desc = "Μέτριο Ταίριασμα &bull; Απαιτεί συμβιβασμούς σε δάνειο, χώρους ή ρίσκο"
        color = "#d97706"
    elif final_score >= 40:
        grade = "C"
        desc = "Οριακό Ταίριασμα &bull; Σημαντικές αποκλίσεις σε budget ή ασφάλεια"
        color = "#ea580c"
    else:
        grade = "D"
        desc = "Χαμηλό Ταίριασμα &bull; Μεγάλο δάνειο, υψηλό ρίσκο περιοχής ή dealbreakers"
        color = "#dc2626"

    return final_score, grade, desc, color, breakdown, dealbreakers

def calculate_enfia(sqm, location, year, ptype="Διαμέρισμα", is_penthouse=False):
    """
    Calculates Greek ENFIA property tax based on Law 4916/2022
    """
    loc_l = (location or "").lower()
    if any(k in loc_l for k in ['κηφισι', 'kifisia', 'εκάλη', 'ekali', 'ψυχικ']):
        base_rate = 4.60
    elif any(k in loc_l for k in ['μαρούσι', 'marousi', 'ηράκλειο', 'irakleio', 'γέρακας', 'gerakas', 'χαλάνδρι', 'δροσι', 'drosia']):
        base_rate = 3.70
    elif any(k in loc_l for k in ['κορυδαλλ', 'korydallos', 'νίκαια', 'nikaia', 'πειραι', 'piraeus', 'καμίνια', 'kaminia']):
        base_rate = 2.80
    else:
        base_rate = 2.80
        
    current_year = 2026
    try:
        yr = int(year) if year and str(year).isdigit() and int(year) > 1900 else 1980
    except Exception:
        yr = 1980
    age = max(0, current_year - yr)
    
    if age >= 26:
        sp = 1.00
    elif age >= 20:
        sp = 1.05
    elif age >= 15:
        sp = 1.10
    elif age >= 10:
        sp = 1.15
    elif age >= 5:
        sp = 1.20
    else:
        sp = 1.25
        
    ptype_l = (ptype or "").lower()
    is_p = is_penthouse is True or str(is_penthouse).lower() == 'true' or 'ρετιρέ' in loc_l or 'ρετιρε' in ptype_l
    if 'μονοκατοικία' in ptype_l or 'μονοκατοικια' in ptype_l or 'detached' in ptype_l:
        so = 1.02
    elif is_p:
        so = 1.02
    elif 'μεζονέτα' in ptype_l or 'μεζονετα' in ptype_l:
        so = 1.01
    else:
        so = 1.01
        
    spr = 1.02 if ('μονοκατοικ' in ptype_l or 'μεζονετ' in ptype_l or is_p) else 1.01
    main_tax = float(sqm or 100) * base_rate * sp * so * spr
    return round(main_tax)

def calculate_mortgage_plan(total_cost, user_cash=USER_CASH, annual_rate=0.0372):
    """
    Calculates required loan and monthly installments for 5, 10, 15, 20, and 30 years at 3.72% interest
    """
    loan_needed = max(0.0, float(total_cost) - float(user_cash))
    if loan_needed <= 0:
        return {
            'loan_needed': 0,
            'installments': {5: 0, 10: 0, 15: 0, 20: 0, 30: 0}
        }
    
    monthly_rate = annual_rate / 12.0
    installments = {}
    for years in [5, 10, 15, 20, 30]:
        n = years * 12
        m = loan_needed * (monthly_rate * ((1.0 + monthly_rate) ** n)) / (((1.0 + monthly_rate) ** n) - 1.0)
        installments[years] = round(m)
        
    return {
        'loan_needed': round(loan_needed),
        'installments': installments
    }

