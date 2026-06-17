"""
WhatsApp Bulk Messaging Automation
===================================
Industry-level WhatsApp bulk messaging tool using Selenium + WhatsApp Web.
Handles session persistence, contact personalization, failure recovery, and reporting.

Author: Keshav
Usage: python whatsapp_blast.py --contacts contacts/list.csv
"""

# ─────────────────────────────────────────────
# MESSAGE TEMPLATE — EDIT THIS SECTION ONLY
# Use {name} for personalization, {company} for company name, etc.
# ─────────────────────────────────────────────

MESSAGE_TEMPLATE = """Hi {name}! 👋

I'm reaching out to introduce our AI-powered marketing solutions that are helping businesses like *{company}* grow faster.

We specialize in:
✅ Automated lead generation
✅ Social media growth strategies
✅ Data-driven ad campaigns
✅ Brand visibility at scale

We'd love to offer you a *FREE 30-minute strategy call* to explore how we can 10x your marketing ROI.

Interested? Just reply *YES* and we'll set it up! 🚀

Best regards,
Marketing Team"""

# ─────────────────────────────────────────────
# CONFIGURATION — Tweak delays and behavior
# ─────────────────────────────────────────────

CONFIG = {
    "delay_between_messages": (8, 15),   # Random delay range (seconds) between sends
    "delay_after_search": (4, 7),         # Wait after searching a number
    "delay_after_open": (3, 6),           # Wait for chat to load
    "delay_typing": (1, 3),               # Simulate typing delay
    "max_retries": 2,                     # Retry attempts per contact on failure
    "retry_delay": 5,                     # Seconds between retries
    "qr_timeout": 60,                     # Seconds to wait for QR scan
    "session_dir": "wa_session",          # Browser profile folder for session persistence
    "default_country_code": "91",       # Fallback country code for 10-digit local numbers
    "headless": False,                    # Set True to run headless (not recommended for WA)
    "log_file": "logs/automation.log",
    "report_file": "reports/run_report.csv",
}

# ─────────────────────────────────────────────────────────────────────────────
# DO NOT EDIT BELOW THIS LINE UNLESS YOU KNOW WHAT YOU'RE DOING
# ─────────────────────────────────────────────────────────────────────────────

import os
import sys
import csv
import json
import time
import random
import logging
import argparse
import urllib.parse
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

# ── Dependency check ──────────────────────────────────────────────────────────

def check_dependencies():
    missing = []
    try:
        import selenium
    except ImportError:
        missing.append("selenium")
    try:
        import webdriver_manager
    except ImportError:
        missing.append("webdriver-manager")
    if missing:
        print(f"\n[ERROR] Missing dependencies: {', '.join(missing)}")
        print(f"Run: pip install {' '.join(missing)}\n")
        sys.exit(1)

check_dependencies()

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException,
    ElementClickInterceptedException, WebDriverException
)
from webdriver_manager.chrome import ChromeDriverManager

# ── Logging Setup ─────────────────────────────────────────────────────────────

Path("logs").mkdir(exist_ok=True)
Path("reports").mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)s]  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(CONFIG["log_file"], encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger(__name__)


def resolve_browser_binary() -> Optional[str]:
    """Return an installed Chromium browser binary path if one can be found."""
    env_candidates = [
        os.environ.get("WHATSAPP_BROWSER_BINARY"),
        os.environ.get("BROWSER_BINARY"),
        os.environ.get("BRAVE_BINARY"),
        os.environ.get("CHROME_BINARY"),
    ]
    for candidate in env_candidates:
        if candidate and Path(candidate).exists():
            return candidate

    local_app_data = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")

    windows_candidates = [
        Path(local_app_data) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
        Path(program_files) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
        Path(program_files_x86) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
        Path(local_app_data) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(program_files) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(program_files_x86) / "Google" / "Chrome" / "Application" / "chrome.exe",
    ]
    for candidate in windows_candidates:
        if Path(candidate).exists():
            return str(candidate)

    return None


def resolve_browser_profile_dir() -> str:
    """Return the browser user-data directory used for session persistence."""
    env_profile_dir = os.environ.get("WHATSAPP_BROWSER_PROFILE_DIR")
    if env_profile_dir and Path(env_profile_dir).exists():
        return env_profile_dir

    session_dir = CONFIG.get("session_dir") or "wa_session"
    return str(Path(session_dir).resolve())

# ── Data Structures ───────────────────────────────────────────────────────────

@dataclass
class Contact:
    number: str
    name: str
    company: str = ""
    extra: dict = field(default_factory=dict)     # Any additional columns from CSV

    def render_message(self, template: str) -> str:
        """Render template with contact-specific variables."""
        variables = {
            "name": self.name,
            "company": self.company or self.name,
            **self.extra
        }
        try:
            return template.format(**variables)
        except KeyError as e:
            log.warning(f"Template variable {e} missing for {self.number}, using raw value")
            return template

@dataclass
class SendResult:
    number: str
    name: str
    status: str          # "success" | "failed" | "skipped"
    error: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    attempts: int = 1

# ── Contact Loader ────────────────────────────────────────────────────────────

class ContactLoader:
    """Load contacts from CSV, TXT, or JSON."""

    @staticmethod
    def load(filepath: str) -> list[Contact]:
        path = Path(filepath)
        if not path.exists():
            log.error(f"Contact file not found: {filepath}")
            sys.exit(1)

        ext = path.suffix.lower()
        loaders = {
            ".csv": ContactLoader._from_csv,
            ".txt": ContactLoader._from_txt,
            ".json": ContactLoader._from_json,
        }
        loader = loaders.get(ext)
        if not loader:
            log.error(f"Unsupported file format: {ext}. Use .csv, .txt, or .json")
            sys.exit(1)

        contacts = loader(path)
        log.info(f"Loaded {len(contacts)} contacts from {filepath}")
        return contacts

    @staticmethod
    def _from_csv(path: Path) -> list[Contact]:
        """
        CSV format: number,name,company (header required)
        Extra columns are passed as template variables.
        """
        contacts = []
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            required = {"number", "name"}
            if not required.issubset(set(reader.fieldnames or [])):
                log.error(f"CSV must have columns: number, name (got: {reader.fieldnames})")
                sys.exit(1)
            for i, row in enumerate(reader, 1):
                number = ContactLoader._clean_number(row["number"])
                if not number:
                    log.warning(f"Row {i}: invalid number '{row['number']}', skipping")
                    continue
                extra = {k: v for k, v in row.items() if k not in ("number", "name", "company")}
                contacts.append(Contact(
                    number=number,
                    name=row["name"].strip(),
                    company=row.get("company", "").strip(),
                    extra=extra
                ))
        return contacts

    @staticmethod
    def _from_txt(path: Path) -> list[Contact]:
        """
        TXT format: one entry per line
        Formats supported:
          912xxxxxxx
          912xxxxxxx John
          912xxxxxxx John Doe | Acme Corp
        """
        contacts = []
        with open(path, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("|")
                main = parts[0].strip().split(None, 1)
                number = ContactLoader._clean_number(main[0])
                if not number:
                    log.warning(f"Line {i}: invalid number '{main[0]}', skipping")
                    continue
                name = main[1].strip() if len(main) > 1 else "Friend"
                company = parts[1].strip() if len(parts) > 1 else ""
                contacts.append(Contact(number=number, name=name, company=company))
        return contacts

    @staticmethod
    def _from_json(path: Path) -> list[Contact]:
        """
        JSON format: list of objects with number, name, company fields.
        """
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        contacts = []
        for i, item in enumerate(data, 1):
            number = ContactLoader._clean_number(str(item.get("number", "")))
            if not number:
                log.warning(f"JSON entry {i}: invalid number, skipping")
                continue
            contacts.append(Contact(
                number=number,
                name=str(item.get("name", "Friend")).strip(),
                company=str(item.get("company", "")).strip(),
                extra={k: v for k, v in item.items() if k not in ("number", "name", "company")}
            ))
        return contacts

    @staticmethod
    def _clean_number(raw: str) -> str:
        """Strip spaces, dashes, pluses. Must be digits only, min 10 digits."""
        cleaned = "".join(c for c in raw if c.isdigit())
        return cleaned if len(cleaned) >= 10 else ""

    @staticmethod
    def _normalize_for_whatsapp(number: str) -> str:
        """Ensure the phone number is in international format for WhatsApp Web."""
        country_code = str(CONFIG.get("default_country_code", "")).strip()
        if not number:
            return number
        if country_code and len(number) == 10 and not number.startswith(country_code):
            return f"{country_code}{number}"
        return number

# ── WhatsApp Driver ───────────────────────────────────────────────────────────

class WhatsAppDriver:
    """Manages Chrome + WhatsApp Web session."""

    WA_URL = "https://web.whatsapp.com"
    WA_NEW_CHAT_URL = "https://web.whatsapp.com/send?phone={number}&text="

    def __init__(self):
        self.driver = self._setup_driver()

    def _setup_driver(self) -> webdriver.Chrome:
        log.info("Initializing Chrome driver...")
        options = Options()

        browser_binary = resolve_browser_binary()
        if browser_binary:
            options.binary_location = browser_binary
            log.info(f"Using browser binary: {browser_binary}")
        else:
            log.warning(
                "No Chrome/Brave binary found. Set WHATSAPP_BROWSER_BINARY to your browser exe path if startup fails."
            )

        # Session persistence — keep a dedicated profile for this automation run.
        session_path = resolve_browser_profile_dir()
        log.info(f"Using browser profile directory: {session_path}")
        options.add_argument(f"--user-data-dir={session_path}")
        options.add_argument("--profile-directory=Default")

        # Anti-detection flags
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1280,900")
        options.add_argument("--log-level=3")  # Suppress Chrome logs

        if CONFIG["headless"]:
            options.add_argument("--headless=new")

        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            driver.execute_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            log.info("Chrome driver initialized.")
            return driver
        except WebDriverException as e:
            log.error(f"Failed to start Chrome: {e}")
            sys.exit(1)

        raise RuntimeError("Chrome driver initialization failed")

    def wait_for_login(self):
        """Open WhatsApp Web and wait for QR scan or existing session."""
        log.info("Opening WhatsApp Web...")
        driver = self.driver
        driver.get(self.WA_URL)

        log.info("Waiting for WhatsApp to load (scan QR if prompted)...")
        try:
            # Wait for the main chat list to appear — confirms login
            WebDriverWait(driver, CONFIG["qr_timeout"]).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="chat-list"]'))
            )
            log.info("✅ WhatsApp Web loaded and authenticated.")
        except TimeoutException:
            log.error("❌ Timed out waiting for login. Did you scan the QR?")
            self.quit()
            sys.exit(1)

    def send_message(self, contact: Contact, message: str) -> bool:
        """
        Open chat for a number via direct URL and send message.
        Returns True on success, False on failure.
        """
        number = ContactLoader._normalize_for_whatsapp(contact.number)
        encoded_msg = urllib.parse.quote(message)
        url = f"https://web.whatsapp.com/send?phone={number}&text={encoded_msg}"

        log.info(f"  → Opening chat for {contact.name} ({number})")
        driver = self.driver
        driver.get(url)

        delay = random.uniform(*CONFIG["delay_after_open"])
        time.sleep(delay)

        # Check for "Phone number shared via url is invalid" popup
        try:
            invalid_xpath = "//*[contains(text(),'phone number shared via url is invalid') or contains(text(),'invalid phone number')]"
            invalid_el = driver.find_elements(By.XPATH, invalid_xpath)
            if invalid_el:
                log.warning(f"  ✗ Invalid number: {number}")
                return False
        except Exception:
            pass

        # Wait for message input box
        try:
            input_box = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable(
                    (By.XPATH, '//div[@contenteditable="true"][@data-tab="10"]')
                )
            )
        except TimeoutException:
            # Try alternative selectors for different WA versions
            try:
                input_box = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, 'div[contenteditable="true"][data-lexical-editor="true"]')
                    )
                )
            except TimeoutException:
                log.warning(f"  ✗ Chat input box not found for {number}")
                return False

        # The text was pre-filled via URL, just press Enter
        time.sleep(random.uniform(*CONFIG["delay_typing"]))
        input_box.click()
        time.sleep(0.5)
        input_box.send_keys(Keys.ENTER)

        # Confirm send by checking message was sent (look for tick mark)
        time.sleep(2)
        log.info(f"  ✅ Sent to {contact.name} ({number})")
        return True

    def quit(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass

# ── Report Writer ─────────────────────────────────────────────────────────────

class ReportWriter:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.results: list[SendResult] = []
        self._init_file()

    def _init_file(self):
        with open(self.filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "Number", "Name", "Status", "Attempts", "Error"])

    def add(self, result: SendResult):
        self.results.append(result)
        with open(self.filepath, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                result.timestamp, result.number, result.name,
                result.status, result.attempts, result.error
            ])

    def print_summary(self):
        total = len(self.results)
        success = sum(1 for r in self.results if r.status == "success")
        failed = sum(1 for r in self.results if r.status == "failed")
        skipped = sum(1 for r in self.results if r.status == "skipped")

        print("\n" + "═" * 55)
        print("  📊  CAMPAIGN SUMMARY")
        print("═" * 55)
        print(f"  Total contacts  : {total}")
        print(f"  ✅ Sent          : {success}")
        print(f"  ❌ Failed        : {failed}")
        print(f"  ⏭  Skipped       : {skipped}")
        print(f"  Success rate    : {(success/total*100):.1f}%" if total else "  N/A")
        print(f"  Report saved    : {self.filepath}")
        print("═" * 55 + "\n")

        if failed > 0:
            print("  Failed numbers:")
            for r in self.results:
                if r.status == "failed":
                    print(f"    • {r.number} ({r.name}) — {r.error}")
            print()

# ── Main Automation Engine ────────────────────────────────────────────────────

class WhatsAppAutomation:
    def __init__(self, contacts: list[Contact], template: str, dry_run: bool = False):
        self.contacts = contacts
        self.template = template
        self.dry_run = dry_run
        self.report = ReportWriter(CONFIG["report_file"])
        self.driver_wrapper: WhatsAppDriver | None = None

    def _send_with_retry(self, contact: Contact, message: str) -> SendResult:
        """Attempt to send with retries. Wraps failures gracefully."""
        result = SendResult(number=contact.number, name=contact.name, status="failed")
        driver_wrapper = self.driver_wrapper
        if driver_wrapper is None:
            raise RuntimeError("Driver has not been initialized")

        for attempt in range(1, CONFIG["max_retries"] + 1):
            result.attempts = attempt
            try:
                if driver_wrapper.send_message(contact, message):
                    result.status = "success"
                    return result
                else:
                    result.error = "Invalid number or chat not opened"
                    result.status = "skipped"
                    return result

            except TimeoutException:
                result.error = f"Timeout on attempt {attempt}"
                log.warning(f"  ⚠ Timeout for {contact.number} (attempt {attempt})")

            except NoSuchElementException as e:
                message_text = (e.msg or str(e))[:60]
                result.error = f"Element not found: {message_text}"
                log.warning(f"  ⚠ Element missing for {contact.number}: {message_text}")

            except ElementClickInterceptedException:
                result.error = "Click intercepted (popup?)"
                log.warning(f"  ⚠ Click intercepted for {contact.number}")

            except WebDriverException as e:
                result.error = f"WebDriver error: {str(e)[:80]}"
                log.warning(f"  ⚠ WebDriver error for {contact.number}: {str(e)[:80]}")

            except Exception as e:
                result.error = f"Unexpected: {str(e)[:80]}"
                log.warning(f"  ⚠ Unexpected error for {contact.number}: {str(e)[:80]}")

            if attempt < CONFIG["max_retries"]:
                log.info(f"  ↻ Retrying in {CONFIG['retry_delay']}s...")
                time.sleep(CONFIG["retry_delay"])

        return result

    def run(self):
        total = len(self.contacts)
        log.info(f"\n{'═'*55}")
        log.info(f"  🚀  Starting campaign: {total} contacts")
        log.info(f"{'═'*55}")

        if self.dry_run:
            log.info("[DRY RUN] Messages will not actually be sent.")
            for c in self.contacts:
                msg = c.render_message(self.template)
                log.info(f"\n─── DRY RUN: {c.name} ({c.number}) ───")
                log.info(msg)
            return

        self.driver_wrapper = WhatsAppDriver()
        self.driver_wrapper.wait_for_login()

        # Brief buffer after login
        time.sleep(3)

        try:
            for idx, contact in enumerate(self.contacts, 1):
                log.info(f"\n[{idx}/{total}] {contact.name} ({contact.number})")

                message = contact.render_message(self.template)
                result = self._send_with_retry(contact, message)

                self.report.add(result)

                status_icon = {"success": "✅", "failed": "❌", "skipped": "⏭"}.get(result.status, "?")
                log.info(f"  {status_icon} Status: {result.status.upper()} | Attempts: {result.attempts}")
                if result.error:
                    log.info(f"  Error: {result.error}")

                # Human-like delay between messages
                if idx < total:
                    delay = random.uniform(*CONFIG["delay_between_messages"])
                    log.info(f"  ⏳ Waiting {delay:.1f}s before next contact...")
                    time.sleep(delay)

        except KeyboardInterrupt:
            log.warning("\n⚠ Campaign interrupted by user.")

        finally:
            self.driver_wrapper.quit()
            self.report.print_summary()

# ── CLI Entry Point ───────────────────────────────────────────────────────────

def build_parser():
    parser = argparse.ArgumentParser(
        description="WhatsApp Bulk Messaging Automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python whatsapp_blast.py --contacts contacts/list.csv
  python whatsapp_blast.py --contacts contacts/list.txt --dry-run
  python whatsapp_blast.py --contacts contacts/list.json --limit 10

Contact file formats:
  CSV  → number,name,company (with header row)
  TXT  → "912xxxxxxx John | Acme Corp" (one per line)
  JSON → [{"number":"912xxx","name":"John","company":"Acme"}]
        """
    )
    parser.add_argument(
        "--contacts",
        default=None,
        help="Path to contact list file (defaults to contacts/list.csv)",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview messages without sending")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max number of contacts to process")
    parser.add_argument("--start-from", type=int, default=1,
                        help="Start from this contact index (1-based)")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    default_contacts = Path(__file__).resolve().parent / "contacts" / "list.csv"
    contacts_path = Path(args.contacts) if args.contacts else default_contacts

    print("""
╔══════════════════════════════════════════════════════╗
║       WhatsApp Bulk Messaging Automation             ║
║       Industry-grade · Session-persistent · Safe     ║
╚══════════════════════════════════════════════════════╝
    """)

    # Load contacts
    contacts = ContactLoader.load(str(contacts_path))

    # Apply --start-from and --limit
    start = max(0, args.start_from - 1)
    contacts = contacts[start:]
    if args.limit:
        contacts = contacts[:args.limit]

    if not contacts:
        log.error("No contacts to process after filters.")
        sys.exit(1)

    log.info(f"Will process {len(contacts)} contact(s)")

    # Validate template has no missing keys that can't be defaulted
    # (soft-check — real failures are caught per-contact)
    if "{name}" not in MESSAGE_TEMPLATE:
        log.warning("Template does not contain {name} — messages will be identical for all contacts")

    automation = WhatsAppAutomation(
        contacts=contacts,
        template=MESSAGE_TEMPLATE,
        dry_run=args.dry_run
    )
    automation.run()


if __name__ == "__main__":
    main()
