#!/usr/bin/env python3
import json
import imaplib
import sys
import os

config_path = os.path.join(os.path.dirname(__file__), "config.json")
if not os.path.exists(config_path):
    print(f"❌ Error: {config_path} not found.")
    sys.exit(1)

with open(config_path, "r", encoding="utf-8") as f:
    cfg = json.load(f)

email_user = cfg.get("email_user", "").strip()
email_pass = cfg.get("email_password", "").strip()
imap_server = cfg.get("imap_server", "imap.gmail.com")

if "YOUR_GMAIL" in email_user or "YOUR_16_CHAR" in email_pass:
    print("⚠️ Παρακαλώ συμπληρώστε πρώτα το email_user και το email_password στο config.json")
    sys.exit(1)

print(f"🔄 Δοκιμή σύνδεσης στο {imap_server} για τον χρήστη: {email_user} ...")

try:
    mail = imaplib.IMAP4_SSL(imap_server)
    mail.login(email_user, email_pass)
    print("✅ ΕΠΙΤΥΧΙΑ! Η σύνδεση στο Gmail IMAP έγινε κανονικά.")
    
    status, counts = mail.select("INBOX")
    if status == "OK":
        total_msgs = counts[0].decode()
        print(f"📬 Συνολικά μηνύματα στα εισερχόμενα (INBOX): {total_msgs}")
    mail.logout()
except imaplib.IMAP4.error as e:
    print(f"❌ Αποτυχία σύνδεσης: {e}")
    print("\n👉 Σημείωση για Gmail:")
    print("1. Πρέπει να χρησιμοποιήσετε 'App Password' (Κωδικό πρόσβασης εφαρμογής) και όχι τον κανονικό κωδικό του Google account.")
    print("2. Βεβαιωθείτε ότι το 2-Step Verification είναι ενεργοποιημένο.")
    print("3. Δημιουργήστε App Password από: https://myaccount.google.com/apppasswords")
except Exception as ex:
    print(f"❌ Απρόβλεπτο σφάλμα: {ex}")
