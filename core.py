import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

class LeadForgeCore:
    def __init__(self, yandex_email, yandex_pass):
        self.mail_user = yandex_email
        self.mail_pass = yandex_pass

    def send_email_from_web(self, to_email, subject, body_text, file_bytes=None, file_name=None, log_callback=None):
        def log(msg):
            if log_callback:
                log_callback(msg)
            else:
                print(msg)

        msg = MIMEMultipart()
        msg["From"] = self.mail_user
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body_text, "plain", "utf-8"))

        if file_bytes and file_name:
            try:
                part = MIMEApplication(file_bytes, Name=file_name)
                part['Content-Disposition'] = f'attachment; filename="{file_name}"'
                msg.attach(part)
            except Exception as e:
                log(f"⚠️ Ошибка прикрепления файла: {e}")

        try:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL("smtp.yandex.ru", 465, context=context) as server:
                server.login(self.mail_user, self.mail_pass)
                server.sendmail(self.mail_user, [to_email, self.mail_user], msg.as_string())
            log(f"✅ Успешно отправлено ➔ {to_email}")
            return True
        except Exception as e:
            log(f"❌ Ошибка отправки на {to_email}: {e}")
            return False