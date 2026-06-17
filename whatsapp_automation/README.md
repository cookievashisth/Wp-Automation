# WhatsApp Bulk Messaging Automation

Industry-grade Python tool for sending personalized WhatsApp messages at scale via WhatsApp Web + Selenium.

---

## Features

- **Session persistence** — scan QR once, stays logged in forever
- **Multi-format contacts** — CSV, TXT, or JSON input
- **Personalized messages** — `{name}`, `{company}`, any custom variable
- **Failure resilience** — per-contact try/except with configurable retries; one failure never stops the campaign
- **Dry-run mode** — preview all messages without sending
- **Auto-reporting** — CSV report in `reports/` after every run
- **Human-like delays** — randomized waits to avoid WhatsApp bans
- **Single template** — edit once at the top, applies to everyone
- **Anti-detection** — Chrome flags to bypass automation detection
- **CLI controls** — `--limit`, `--start-from`, `--dry-run`

---

## Setup (Windows)

### 1. Install Python
Download from https://www.python.org/downloads/ (Python 3.10+)
Make sure to check **"Add Python to PATH"** during install.

### 2. Install dependencies
```
pip install -r requirements.txt
```

### 3. Prepare your contacts
Edit one of the files in `contacts/`:
- `list.csv` — recommended
- `list.txt` — simple line-by-line
- `list.json` — structured

### 4. Edit your message template
Open `whatsapp_blast.py` and find the `MESSAGE_TEMPLATE` section at the top.
Edit the message once — it applies to all contacts automatically.

---

## Running

### Option A — Double-click
Double-click `run.bat` and enter your contact file path when prompted.

### Option B — Terminal
```cmd
python whatsapp_blast.py --contacts contacts\list.csv
```

### With options
```cmd
# Preview messages without sending
python whatsapp_blast.py --contacts contacts\list.csv --dry-run

# Only send to first 10 contacts
python whatsapp_blast.py --contacts contacts\list.csv --limit 10

# Resume from contact #25 (useful after crash)
python whatsapp_blast.py --contacts contacts\list.csv --start-from 25

# Combined
python whatsapp_blast.py --contacts contacts\list.csv --start-from 5 --limit 50
```

---

## Contact File Formats

### CSV (Recommended)
```csv
number,name,company
919876543210,Rahul Sharma,TechVentures Pvt Ltd
918765432109,Priya Mehta,DigitalFirst Agency
```
- Header row required: `number`, `name`, `company`
- Any extra columns become available as `{variable}` in the template
- Numbers: digits only, no `+`, no spaces, no dashes

### TXT
```
# Lines starting with # are comments
919876543210 Rahul Sharma | TechVentures
918765432109 Priya Mehta
```
- Format: `number Name | Company`
- Company is optional

### JSON
```json
[
  {"number": "919876543210", "name": "Rahul", "company": "Acme Corp"},
  {"number": "918765432109", "name": "Priya"}
]
```

---

## Message Template

Located at the top of `whatsapp_blast.py`:

```python
MESSAGE_TEMPLATE = """Hi {name}! 👋

Your personalized message for {company} here.

Best regards,
Your Team"""
```

**Available variables:**
- `{name}` — contact's name
- `{company}` — company name (falls back to name if empty)
- Any extra CSV column becomes a variable automatically

---

## Configuration

All settings are in the `CONFIG` dict at the top of `whatsapp_blast.py`:

| Key | Default | Description |
|-----|---------|-------------|
| `delay_between_messages` | `(8, 15)` | Random delay range (seconds) between sends |
| `delay_after_open` | `(3, 6)` | Wait for chat to load |
| `max_retries` | `2` | Retry attempts per contact |
| `qr_timeout` | `60` | Seconds to wait for QR scan |
| `session_dir` | `wa_session` | Chrome profile for login persistence |

---

## How It Works

1. Chrome opens with a persistent profile in `wa_session/`
2. WhatsApp Web loads — scan QR once on first run
3. For each contact, the tool opens:
   `https://web.whatsapp.com/send?phone={number}&text={encoded_message}`
4. WhatsApp pre-fills the message; the tool clicks Send
5. Randomized delay before the next contact
6. All results logged to `logs/automation.log` and `reports/run_report.csv`

---

## Output Files

```
logs/
  automation.log       ← Full execution log with timestamps

reports/
  run_report.csv       ← Per-contact result: success/failed/skipped

wa_session/            ← Chrome profile (auto-created, keeps you logged in)
```

---

## Safety & Best Practices

- **Keep delays at 8–15 seconds minimum** — lower delays risk WhatsApp banning your number
- **Don't send more than 200–300 messages per day** from a single number
- **Use a dedicated number** for bulk campaigns, not your personal number
- **Warm up new numbers** — start with 20-30/day, ramp up over 2 weeks
- This tool uses `https://web.whatsapp.com/send?phone=` — works for unsaved numbers too

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| QR code not appearing | Delete `wa_session/` folder and re-run |
| Messages not sending | WhatsApp UI changed; check Chrome is updated |
| `ChromeDriverManager` error | Run `pip install --upgrade webdriver-manager` |
| `selenium` not found | Run `pip install -r requirements.txt` |
| Contact skipped as "invalid" | Verify number format: country code + number, digits only |

---

## Project Structure

```
whatsapp_automation/
├── whatsapp_blast.py     ← Main script (edit template here)
├── run.bat               ← Windows launcher
├── requirements.txt      ← Dependencies
├── README.md
├── contacts/
│   ├── list.csv          ← Sample CSV contacts
│   ├── list.txt          ← Sample TXT contacts
│   └── list.json         ← Sample JSON contacts
├── logs/
│   └── automation.log    ← Auto-created on run
├── reports/
│   └── run_report.csv    ← Auto-created on run
└── wa_session/           ← Auto-created (Chrome profile)
```

---

## License

For personal and business use. Not affiliated with WhatsApp Inc.
Use responsibly and in compliance with WhatsApp's Terms of Service.
