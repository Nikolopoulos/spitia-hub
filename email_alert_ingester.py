#!/usr/bin/env python3
"""
Real Estate Email Alert Ingestion & Parser
Monitors an email inbox for Spitogatos / XE saved search alerts,
extracts listing links, expands truncated digests, and passes them
to the evaluation pipeline.
"""

import imaplib
import email
from email.header import decode_header
import re
import os
import sys
import json
import logging
from html.parser import HTMLParser
from urllib.parse import urlparse, parse_qs, unquote


CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Target filters configuration & Smart Pre-Filtering
PREFERENCES = {
    "cash_budget": 180000,
    "max_acceptable_price_loan": 240000,
    "ideal_sqm": 120,
    "min_sqm_tolerated": 90,
    # Acceptable property types in Greek / English
    "accepted_property_types": [
        "μονοκατοικια", "μονοκατοικία", "detached", "house",
        "μεζονετα", "μεζονέτα", "maisonette",
        "ρετιρε", "ρετιρέ", "penthouse",
        "διαμερισμα", "διαμέρισμα", "apartment"  # Kept conditionally for large sqm / top floor
    ],
    # Rejected keywords (commercial, plots, tiny flats, ground floors in multi-unit buildings, blacklisted areas, auctions)
    "rejected_keywords": [
        "οικόπεδο", "οικοπεδο", "αγροτεμάχιο", "αγροτεμαχιο", "plot",
        "επαγγελματικός", "γραφείο", "γραφειο", "κατάστημα", "καταστημα", "commercial",
        "parking", "γκαράζ", "αποθήκη", "αποθηκη", "υπόγειο", "υπογειο",
        "αγία βαρβάρα", "αγια βαρβαρα", "agia varvara", "agia-varvara", "riminitika", "ριμινίτικα",
        "μενίδι", "μενιδι", "menidi", "αχαρνές", "αχαρνες", "acharnes",
        "ζεφύρι", "ζεφυρι", "zefyri", "άνω λιόσια", "ανω λιοσια", "ano liosia",
        "ασπρόπυργος", "ασπροπυργος", "aspropyrgos", "φυλή", "φυλη", "καματερό", "καματερο",
        "ενοικίαση", "ενοικιαση", "ενοικιάζεται", "ενοικιαζεται", "/μήνα", "/μηνα", "€ / μήνα", "€/μήνα",
        "πλειστηριασμ", "πλειστηριαζ", "εκπλειστηριασμ", "eauction", "e-auction",
        "κατάσχεση", "κατασχεση", "πρώτης προσφοράς", "πρωτης προσφορας"
    ],
    "clusters": {
        "POLOS_1_WEST_PIRAEUS": {
            "name": "Κερατσίνι & Δυτικά / Πειραιάς (Cash Goal <= 180k)",
            "areas": ["keratsini", "drapetsona", "korydallos", "nikaia", "tampouria", "kastella", "peiraiki",
                      "κερατσινι", "κερατσίνι", "δραπετσωνα", "δραπετσώνα", "κορυδαλλος", "κορυδαλλός", 
                      "νικαια", "νίκαια", "ταμπουρια", "ταμπούρια", "καστελλα", "καστέλλα", "πειραικη", "πειραϊκή"],
            "max_price": 185000,
            "min_sqm": 90,
        },
        "POLOS_2_NORTH_MAROUSI": {
            "name": "Μαρούσι / Χαλάνδρι & Όμοροι (Low Loan <= 235k)",
            "areas": ["marousi", "chalandri", "irakleio", "pefki", "vrilissia", "agia paraskevi", "melissia",
                      "μαρουσι", "μαρούσι", "χαλανδρι", "χαλάνδρι", "ηρακλειο", "ηράκλειο", "πευκη", "πεύκη", 
                      "βριλησσια", "βριλήσσια", "αγια παρασκευη", "αγία παρασκευή", "μελισσια", "μελίσσια"],
            "max_price": 235000,
            "min_sqm": 90,
        }
    }
}

class EmailHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.current_tag = None
        self.current_href = None
        self.current_text = []
        self.links = [] # list of (href, text)

    def handle_starttag(self, tag, attrs):
        self.current_tag = tag
        if tag == "a":
            attrs_dict = dict(attrs)
            self.current_href = attrs_dict.get("href")
            self.current_text = []

    def handle_data(self, data):
        if self.current_href is not None:
            self.current_text.append(data.strip())

    def handle_endtag(self, tag):
        if tag == "a" and self.current_href:
            full_text = " ".join([t for t in self.current_text if t])
            self.links.append((self.current_href, full_text))
            self.current_href = None
            self.current_text = []


class EmailAlertIngester:
    def __init__(self, imap_server, email_user, email_password, folder="INBOX"):
        self.imap_server = imap_server
        self.email_user = email_user
        self.email_password = email_password
        self.folder = folder

    def connect(self):
        self.mail = imaplib.IMAP4_SSL(self.imap_server)
        self.mail.login(self.email_user, self.email_password)
        self.mail.select(self.folder)
        logging.info(f"Connected to {self.imap_server} as {self.email_user}")


    def fetch_unprocessed_alerts(self, mark_as_read=True):
        """Search for unread emails from Spitogatos and XE"""
        status, messages = self.mail.search(None, '(UNSEEN)')
        if status != "OK":
            logging.warning("No messages or error checking inbox.")
            return []

        email_ids = messages[0].split()
        logging.info(f"Found {len(email_ids)} unread email(s).")
        
        extracted_listings = []

        for e_id in email_ids:
            res, msg_data = self.mail.fetch(e_id, "(RFC822)")
            if res != "OK":
                continue

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)
            
            sender = msg.get("From", "")
            subject = self._decode_str(msg.get("Subject", ""))
            
            logging.info(f"Processing email: '{subject}' from '{sender}'")

            html_body = self._extract_html_body(msg)
            if html_body:
                parsed_res = self.parse_email_html(html_body, sender)
                if isinstance(parsed_res, dict):
                    extracted_listings.extend(parsed_res.get("listings", []))
                elif isinstance(parsed_res, list):
                    extracted_listings.extend(parsed_res)

            if mark_as_read:
                self.mail.store(e_id, "+FLAGS", "\\Seen")

        return extracted_listings

    def _decode_str(self, header_value):
        decoded_list = decode_header(header_value)
        result = ""
        for bytes_or_str, enc in decoded_list:
            if isinstance(bytes_or_str, bytes):
                result += bytes_or_str.decode(enc or "utf-8", errors="replace")
            else:
                result += str(bytes_or_str)
        return result

    def _extract_html_body(self, msg):
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                if content_type == "text/html" and "attachment" not in content_disposition:
                    return part.get_payload(decode=True).decode(errors="replace")
        else:
            if msg.get_content_type() == "text/html":
                return msg.get_payload(decode=True).decode(errors="replace")
        return ""

    def parse_email_html(self, html_content, sender):
        """Extract individual listing links and 'see more / search' links with smart pre-filtering."""
        parser = EmailHTMLParser()
        try:
            parser.feed(html_content)
        except Exception as e:
            logging.warning(f"HTML parsing error: {e}")

        listings = []
        search_expansion_urls = []

        for href, text in parser.links:
            href = href.strip()
            text_lower = text.lower()

            # Check for Spitogatos direct listing
            if "spitogatos.gr/aggelia/" in href:
                clean_url = href.split("?")[0]
                if clean_url not in [l["url"] for l in listings]:
                    is_rejected, reason = self._is_pre_filtered_out(text_lower, clean_url)
                    if is_rejected:
                        logging.info(f"Skipping listing {clean_url}: {reason}")
                        continue

                    listings.append({
                        "portal": "spitogatos",
                        "type": "listing",
                        "url": clean_url,
                        "card_text": text[:200]
                    })
            # Check for Spitogatos search / view more link
            elif "spitogatos.gr" in href and any(k in href for k in ["/poliseis-", "/pwliseis-", "search"]):
                if href not in search_expansion_urls:
                    search_expansion_urls.append(href)

            # Check for XE direct listing (both /property/d/ and modern /p/<uuid>)
            elif "xe.gr/p/" in href or "xe.gr/property/d/" in href or ("xe.gr/property/" in href and any(c.isdigit() for c in href)):
                clean_url = href.split("?")[0]
                if clean_url not in [l["url"] for l in listings]:
                    is_rejected, reason = self._is_pre_filtered_out(text_lower, clean_url)
                    if is_rejected:
                        logging.info(f"Skipping listing {clean_url}: {reason}")
                        continue

                    listings.append({
                        "portal": "xe",
                        "type": "listing",
                        "url": clean_url,
                        "card_text": text[:200]
                    })
            # Check for XE search / view more link
            elif "xe.gr/property/r/" in href or "xe.gr/property/results" in href:
                if href not in search_expansion_urls:
                    search_expansion_urls.append(href)

        logging.info(f"Extracted {len(listings)} valid listing(s) and {len(search_expansion_urls)} expansion URL(s).")
        return {
            "listings": listings,
            "expansion_urls": search_expansion_urls
        }

    def _is_pre_filtered_out(self, text, url):
        """Pre-filter out non-residential, plots, tiny apartments or obvious non-matches from email text"""
        combined = (text + " " + url).lower()

        # Reject explicitly unwanted types (commercial, plots, garages, underground)
        for rej in PREFERENCES["rejected_keywords"]:
            if rej in combined:
                return True, f"Rejected keyword found: {rej}"

        # If sqm is clearly stated in email card (e.g. 50 τ.μ., 65τμ) and < 90, skip it!
        sqm_matches = re.findall(r'(\d+)\s*(?:τ\.?μ\.?|sqm|sq\.m)', combined)
        if sqm_matches:
            try:
                sqm = int(sqm_matches[0])
                if sqm < PREFERENCES["min_sqm_tolerated"]:
                    return True, f"Too small: {sqm} sqm < {PREFERENCES['min_sqm_tolerated']} sqm"
            except ValueError:
                pass

        return False, ""

    def close(self):
        try:
            self.mail.close()
            self.mail.logout()
        except Exception:
            pass


STATUS_FILE = os.path.join(os.path.dirname(__file__), "alert_status.json")

def update_status(last_run, new_properties_count, total_unprocessed=0, last_listings=None):
    data = {
        "last_run": last_run,
        "new_properties_count": new_properties_count,
        "total_unprocessed": total_unprocessed,
        "last_listings": last_listings or []
    }
    try:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Failed to write status file: {e}")

if __name__ == "__main__":
    from datetime import datetime
    cfg = load_config()
    if not cfg:
        print("❌ No config.json found.")
        sys.exit(1)
        
    ingester = EmailAlertIngester(
        imap_server=cfg.get("imap_server", "imap.gmail.com"),
        email_user=cfg["email_user"],
        email_password=cfg["email_password"],
        folder=cfg.get("folder", "INBOX")
    )
    
    now_str = datetime.now().strftime("%H:%M:%S (%d/%m)")
    try:
        ingester.connect()
        logging.info("Listening for new Spitogatos / XE alerts...")
        results = ingester.fetch_unprocessed_alerts(mark_as_read=True)
        listings = results if isinstance(results, list) else results.get("listings", [])
        count = len(listings)
        print(f"Results: {count} new qualifying listings found.")
        update_status(last_run=now_str, new_properties_count=count, last_listings=[l["url"] for l in listings])
        ingester.close()
    except Exception as e:
        logging.error(f"Error during alert check: {e}")
        update_status(last_run=f"{now_str} (Error: {e})", new_properties_count=0)


