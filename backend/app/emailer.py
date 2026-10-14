import smtplib
import ssl
from email.message import EmailMessage
from .config import settings


def send_invitation(email: str, url: str):
    if not settings.smtp_host or not settings.smtp_from:
        if settings.environment != "development":
            raise RuntimeError("Servidor de e-mail não configurado")
        return False
    msg = EmailMessage()
    msg["Subject"] = "Convite para o Horário Inteligente"
    msg["From"] = settings.smtp_from
    msg["To"] = email
    msg.set_content(f"Você recebeu um convite para o Horário Inteligente. Acesse o endereço abaixo para ativar seu acesso:\n\n{url}\n\nO convite expira em 48 horas.")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        # Verificar identidade e certificado do servidor SMTP (anti-MITM).
        # Sem fallback para SMTP sem TLS ou certificado inválido.
        smtp.starttls(context=ssl.create_default_context())
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)
    return True
