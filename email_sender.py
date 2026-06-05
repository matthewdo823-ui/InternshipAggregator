"""
Email sender for LinkedIn comment automation.

WORKFLOW:
  1. You manually (or via script) collect emails from LinkedIn post comments
  2. Run this script to send everyone the resource link

SETUP:
  1. Enable Gmail API: https://console.cloud.google.com/
  2. Download credentials.json → save to config/gmail_credentials.json
  3. Run once — it'll open a browser to auth, then save token.json

  pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client
"""
import os
import base64
import csv
import re
import yaml
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path


def load_config():
    with open("config/config.yaml") as f:
        return yaml.safe_load(f)


def get_gmail_service():
    """Authenticate and return Gmail API service."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
    creds = None

    if os.path.exists("config/token.json"):
        creds = Credentials.from_authorized_user_file("config/token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "config/gmail_credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open("config/token.json", "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def build_email(to: str, subject: str, resource_url: str, sender: str) -> dict:
    """Build a personalized HTML email."""
    html = f"""
    <html><body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
      <h2 style="color: #0077b5;">Your Engineering Internship List is Here 🚀</h2>
      <p>Thanks for commenting! Here's the link to the live-updated list:</p>
      <p style="text-align: center;">
        <a href="{resource_url}"
           style="background: #0077b5; color: white; padding: 12px 24px;
                  text-decoration: none; border-radius: 6px; font-weight: bold;">
          View the Full List →
        </a>
      </p>
      <p style="color: #666; font-size: 14px;">
        The list is updated daily. Bookmark it and check back often — new roles
        get added and some close fast.
      </p>
      <p style="color: #666; font-size: 14px;">
        Good luck with your applications! 💪
      </p>
      <hr style="border: none; border-top: 1px solid #eee;" />
      <p style="color: #999; font-size: 12px;">
        You're receiving this because you commented on a LinkedIn post requesting this list.
        Reply to unsubscribe.
      </p>
    </body></html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg.attach(MIMEText(html, "html"))

    return {"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode()}


def send_to_list(emails: list[str], config: dict):
    """Send resource email to a list of addresses."""
    email_cfg = config["email"]
    service = get_gmail_service()

    sent = 0
    failed = 0

    for email in emails:
        email = email.strip().lower()
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            print(f"  Skipping invalid: {email}")
            continue

        try:
            msg = build_email(
                to=email,
                subject=email_cfg["subject"],
                resource_url=email_cfg["resource_url"],
                sender=email_cfg["sender_email"],
            )
            service.users().messages().send(userId="me", body=msg).execute()
            print(f"  ✓ Sent to {email}")
            sent += 1
        except Exception as e:
            print(f"  ✗ Failed {email}: {e}")
            failed += 1

    print(f"\nDone. Sent: {sent}, Failed: {failed}")


def parse_emails_from_text(text: str) -> list[str]:
    """
    Extract emails from pasted LinkedIn comment text.

    Usage:
      1. Open your LinkedIn post
      2. Scroll through comments, copy all text
      3. Paste into a .txt file and pass the path here
    """
    # Match standard emails and .edu emails
    pattern = r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
    found = re.findall(pattern, text)
    # Deduplicate
    return list(set(found))


def load_emails_from_file(path: str) -> list[str]:
    """Load from a .txt (one per line or pasted comments) or .csv file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    text = path.read_text()

    if path.suffix == ".csv":
        # Assume first column is email
        import csv, io
        reader = csv.reader(io.StringIO(text))
        return [row[0].strip() for row in reader if row and "@" in row[0]]
    else:
        # Plain text — extract all email-shaped strings
        return parse_emails_from_text(text)


# ─── CLI ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    config = load_config()

    if not config["email"]["enabled"]:
        print("Email sending is disabled in config.yaml.")
        print("Set email.enabled: true and fill in your details to use this.")
        sys.exit(0)

    if len(sys.argv) < 2:
        print("Usage: python email_sender.py <path_to_comments_file>")
        print("  The file can be a .txt with pasted LinkedIn comments")
        print("  or a .csv with emails in the first column.")
        sys.exit(1)

    emails = load_emails_from_file(sys.argv[1])
    print(f"Found {len(emails)} email(s) to send to:")
    for e in emails:
        print(f"  {e}")

    confirm = input("\nSend? (y/n): ")
    if confirm.lower() == "y":
        send_to_list(emails, config)
