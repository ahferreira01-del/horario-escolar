"""SMTP de convites exige verificação de certificado e nome TLS."""
import ssl

import pytest

from app import emailer


class SMTPStub:
    last = None

    def __init__(self,host,port,timeout):
        self.host=host
        self.port=port
        self.timeout=timeout
        self.tls_context=None
        self.login_call=None
        self.messages=[]
        SMTPStub.last=self

    def __enter__(self):return self
    def __exit__(self,*args):return False

    def starttls(self,*,context=None):
        assert context is not None, "TLS must use verified SSLContext"
        self.tls_context=context

    def login(self,user,password):
        self.login_call=(user,password)

    def send_message(self,msg):
        self.messages.append(msg)


def test_invitation_requires_verified_starttls(monkeypatch):
    monkeypatch.setattr(emailer.settings,"environment","production")
    monkeypatch.setattr(emailer.settings,"smtp_host","smtp.school-test.org")
    monkeypatch.setattr(emailer.settings,"smtp_port",587)
    monkeypatch.setattr(emailer.settings,"smtp_user","mailer")
    monkeypatch.setattr(emailer.settings,"smtp_password","fake-pass")
    monkeypatch.setattr(emailer.settings,"smtp_from","convites@school-test.org")
    monkeypatch.setattr(emailer.smtplib,"SMTP",SMTPStub)
    ok=emailer.send_invitation("director@school-test.org","https://school-test.org/convite?token=abc")
    assert ok is True
    connection=SMTPStub.last
    assert connection.tls_context.verify_mode == ssl.CERT_REQUIRED
    assert connection.tls_context.check_hostname is True
    assert connection.login_call==("mailer","fake-pass")
    assert len(connection.messages)==1
    assert connection.messages[0]["To"]=="director@school-test.org"


def test_development_with_no_smtp_is_not_silently_sent(monkeypatch):
    monkeypatch.setattr(emailer.settings,"environment","development")
    monkeypatch.setattr(emailer.settings,"smtp_host","")
    monkeypatch.setattr(emailer.settings,"smtp_from","")
    assert emailer.send_invitation("a@example.org","https://example.org/convite") is False


def test_production_without_smtp_does_not_fall_back(monkeypatch):
    monkeypatch.setattr(emailer.settings,"environment","production")
    monkeypatch.setattr(emailer.settings,"smtp_host","")
    with pytest.raises(RuntimeError,match="Servidor de e-mail"):
        emailer.send_invitation("a@example.org","https://example.org/convite")
