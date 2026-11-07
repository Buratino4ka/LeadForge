import os
import time
import smtplib
import imaplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from datetime import datetime

class LeadForgeCore:
    def __init__(self, yandex_user, yandex_password):
        self.mail_user = yandex_user
        self.mail_password = yandex_password

    def send_email_from_web(self, to_email, subject, body_text, file_bytes=None, file_name=None, log_callback=None):
        if not to_email or "@" not in to_email or len(to_email) < 6:
            if log_callback: log_callback(f"⚠️ Некорректный email: {to_email}")
            return False

        msg = MIMEMultipart()
        msg["From"] = self.mail_user
        msg["To"] = to_email
        msg["Subject"] = subject
        msg["Date"] = datetime.now().strftime("%a, %d %b %Y %H:%M:%S %z")
        msg.attach(MIMEText(body_text, "plain", "utf-8"))

        if file_bytes and file_name:
            part = MIMEApplication(file_bytes, Name=file_name)
            part['Content-Disposition'] = f'attachment; filename="{file_name}"'
            msg.attach(part)

        try:
            context = ssl.create_default_context()
            server = smtplib.SMTP_SSL("smtp.yandex.ru", 465, context=context)
            server.login(self.mail_user, self.mail_password)
            refused = server.sendmail(self.mail_user, [to_email], msg.as_string())
            server.quit()

            if refused:
                if log_callback: log_callback(f"❌ Ошибка SMTP для {to_email}: {refused}")
                return False

            try:
                mail_imap = imaplib.IMAP4_SSL("imap.yandex.ru", 993)
                mail_imap.login(self.mail_user, self.mail_password)
                mail_imap.append("Sent", '\\Seen', imaplib.Time2Internaldate(time.time()), msg.as_bytes())
                mail_imap.logout()
            except:
                pass

            if log_callback: log_callback(f"✅ Успешно отправлено ➔ {to_email}")
            return True
        except Exception as e:
            err = str(e)
            if log_callback: log_callback(f"❌ Ошибка отправки на {to_email}: {err}")
            return False

    def run_mailing_process(self, df_leads, subject, body_template, file_bytes, file_name, log_callback, update_status_callback):
        try:
            total = len(df_leads)
            log_callback(f"📊 Всего строк в базе: {total}")

            for idx, row in df_leads.iterrows():
                email = str(row.get("Email", ""))
                status = str(row.get("Статус", ""))
                channel_name = str(row.get("Канал", "автор"))

                if status == "В очереди" and email and "@" in email:
                    log_callback(f"⏳ Отправка для: {channel_name} ({email})...")
                    
                    personalized_body = body_template.replace("{channel_name}", channel_name)
                    
                    success = self.send_email_from_web(
                        to_email=email,
                        subject=subject,
                        body_text=personalized_body,
                        file_bytes=file_bytes,
                        file_name=file_name,
                        log_callback=log_callback
                    )

                    new_status = "Отправлено" if success else "Ошибка отправки"
                    update_status_callback(idx, new_status)
                    time.sleep(3) # Пауза против спам-фильтров
            
            log_callback("🎉 Рассылка по очереди завершена!")
        except Exception as e:
            log_callback(f"❌ Ошибка в процессе рассылки: {e}")