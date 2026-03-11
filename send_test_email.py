import os
import smtplib
from email.message import EmailMessage
from pathlib import Path


def load_dotenv(dotenv_path=".env"):
    env_file = Path(dotenv_path)
    if not env_file.exists():
        return

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def main():
    load_dotenv()

    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USERNAME", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    smtp_from = os.getenv("SMTP_FROM", smtp_user or "noreply@example.com")
    smtp_to = os.getenv("TEST_EMAIL_TO", smtp_user).strip()
    use_tls = os.getenv("SMTP_USE_TLS", "1") == "1"

    if not smtp_host or not smtp_user or not smtp_password or not smtp_to:
        raise SystemExit(
            "Configuration SMTP incomplete. Renseigne SMTP_HOST, SMTP_USERNAME, "
            "SMTP_PASSWORD et TEST_EMAIL_TO ou SMTP_USERNAME."
        )

    message = EmailMessage()
    message["Subject"] = "Test SMTP CRM"
    message["From"] = smtp_from
    message["To"] = smtp_to
    message.set_content(
        "Cet email confirme que la configuration SMTP du CRM fonctionne."
    )

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        if use_tls:
            server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(message)

    print(f"Email de test envoye a {smtp_to}.")


if __name__ == "__main__":
    main()
