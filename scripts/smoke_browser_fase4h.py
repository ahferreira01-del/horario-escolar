#!/usr/bin/env python3
"""Smoke real no Chromium para interface Next.js + API local.

Preparação feita pelo CI: frontend e FastAPI iniciados, banco descartável.
NÃO valida PostgreSQL ou RLS sozinho. Falha caso login, proxy de cookies,
menu da plataforma ou cadastro administrativo não funcionem no browser.
"""
import os
import uuid
from playwright.sync_api import sync_playwright, expect

BASE = os.environ.get('HI_BROWSER_URL', 'http://127.0.0.1:3000')
EMAIL = os.environ.get('HI_BROWSER_ADMIN_EMAIL', 'admin-e2e@example.com')
PASSWORD = os.environ.get('HI_BROWSER_ADMIN_PASSWORD')


def main():
    if not PASSWORD:
        raise RuntimeError('Defina HI_BROWSER_ADMIN_PASSWORD apenas no ambiente descartável de teste.')
    suffix = uuid.uuid4().hex[:8]
    org_name = 'Escola Homologacao ' + suffix
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(locale='pt-BR', viewport={'width': 1280,'height': 800})
            page.goto(BASE, wait_until='domcontentloaded', timeout=30000)
            expect(page.get_by_role('heading', name='Boas-vindas de volta')).to_be_visible(timeout=15000)
            page.get_by_placeholder('voce@escola.com.br').fill(EMAIL)
            page.get_by_placeholder('Sua senha').fill(PASSWORD)
            page.get_by_role('button',name='Entrar na plataforma').click()
            expect(page.get_by_role('button',name='Organizações')).to_be_visible(timeout=15000)
            page.get_by_role('button',name='Organizações').click()
            expect(page.get_by_role('heading',name='Cadastrar organização')).to_be_visible()
            fields = page.locator('form.grid-3 input')
            assert fields.count() == 3, 'Formulário de organização mudou de contrato.'
            fields.nth(0).fill(org_name)
            fields.nth(1).fill('Administrador CI')
            fields.nth(2).fill(f'admin-{suffix}@example.com')
            page.get_by_role('button', name='Criar e convidar').click()
            expect(page.get_by_text('Organização criada: '+org_name)).to_be_visible(timeout=15000)
            expect(page.get_by_role('cell',name=org_name)).to_be_visible()
            print('BROWSER_PASSED: login, sessão, navegação, CSRF e cadastro de organização no Next.js')
        finally:
            browser.close()


if __name__ == '__main__':
    main()
