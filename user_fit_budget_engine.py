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
    # 1. BUDGET & LOAN COMPONENT (25 pts max)
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
        if is_sensational:
            b_pts = 14.0
            score += b_pts
            breakdown.append(f"⭐ Συνταρακτική Ευκαιρία &bull; Ανοιχτό σε Μεγαλύτερο Δάνειο (+{int(b_pts)}/25): Παρότι απαιτείται δάνειο €{int(loan_needed):,}, το ακίνητο συνδυάζει χαμηλό ρίσκο ({risk_score}/10) και κορυφαίο deal ({deal_score}/100)!")
        else:
            b_pts = 3.0
            score += b_pts
            dealbreakers.append(f"⚠️ Μεγάλο Δάνειο (> €{int(loan_needed):,}) χωρίς συνταρακτικό deal")
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
    # 3. PARKING & VEHICLE THEFT (25 pts max)
    # -------------------------------------------------------------
    has_private = p.get('has_parking', 'False') == 'True'
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
                p_pts = 12.0
                score += p_pts
                breakdown.append(f"🟡 Στάθμευση στον Δρόμο (+{int(p_pts)}/25 - Μέτριο): {s_data['summary']}. Απαιτείται αναζήτηση σε γειτονικά στενά.")
            else:
                p_pts = 0.0
                dealbreakers.append("❌ Χωρίς Parking & Οξύ Πρόβλημα Στάθμευσης/Κλοπών στον Δρόμο")
                breakdown.append(f"🔴 Χωρίς Parking (0/25 - Dealbreaker): {s_data['summary']}. Πολύ δύσκολη εύρεση θέσης & υψηλός κίνδυνος κλοπής οχημάτων/μηχανών.")
        else:
            dealbreakers.append("❌ Χωρίς Parking")
            breakdown.append("❌ Χωρίς Parking (0/25)")

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
