#!/usr/bin/env python3
"""Fase 4J: fluxo escolar pela interface real Next.js + FastAPI + PostgreSQL.

Ambiente descartável do CI. Nenhum dado escolar real. Exige sessão de admin
da plataforma e URLs do ambiente de homologação, não roda em produção.
"""
import os
import uuid

from playwright.sync_api import expect, sync_playwright
from phase4x2d_test_support import assert_local_candidate_url, browser_launch_options, invitation_url
from smoke_browser_manual_provisioning import logout, change_temporary_password

BASE = os.environ.get("HI_BROWSER_URL", "http://127.0.0.1:3000")
EMAIL = os.environ.get("HI_BROWSER_ADMIN_EMAIL", "admin-e2e@example.com")
PASSWORD = os.environ.get("HI_BROWSER_ADMIN_PASSWORD")

def main(after_preview=None):
    if not PASSWORD:
        raise RuntimeError("HI_BROWSER_ADMIN_PASSWORD é obrigatória para teste descartável.")
    assert_local_candidate_url(BASE)
    uid = uuid.uuid4().hex[:8]
    org = "Rede Escolar CI " + uid
    email = "diretor-escolar-" + uid + "@example.com"
    secret = "SenhaForteCI-Convite-12345!"
    school = "Unidade Centro " + uid
    teacher = "Professora Ana " + uid
    subject = "Matematica " + uid
    klass = "6o Ano A " + uid

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**browser_launch_options())
        try:
            page = browser.new_page(locale="pt-BR", viewport={"width": 1440, "height": 900})
            page.set_default_timeout(18000)
            page.goto(BASE, wait_until="domcontentloaded", timeout=30000)
            expect(page.get_by_role("heading", name="Boas-vindas de volta")).to_be_visible()
            page.get_by_placeholder("voce@escola.com.br").fill(EMAIL)
            page.get_by_placeholder("Sua senha").fill(PASSWORD)
            page.get_by_role("button", name="Entrar na plataforma").click()
            page.get_by_role("button", name="Organizações").click()
            form = page.locator("form.grid-3")
            form.locator("input").nth(0).fill(org)
            form.locator("input").nth(1).fill("Diretora Escolar CI")
            form.locator("input").nth(2).fill(email)
            page.get_by_test_id("create-organization-submit").click()
            expect(page.get_by_text("Organização criada: " + org)).to_be_visible()
            credential_dialog = page.get_by_test_id("credential-dialog")
            manual_provisioning = bool(credential_dialog.count())
            if manual_provisioning:
                expect(credential_dialog).to_be_visible()
                temporary_password = page.get_by_test_id("temporary-password-value").inner_text()
                assert len(temporary_password) >= 20
                page.get_by_test_id("credential-close").click()
                expect(credential_dialog).to_have_count(0)
                logout(page)
                change_temporary_password(page, (email, temporary_password), secret)
            else:
                # Fluxo legado por convite, somente no ambiente descartável.
                invite_url = invitation_url(page, email, BASE)
                assert "/convite?" in invite_url
                page.goto(invite_url, wait_until="domcontentloaded")
                expect(page.get_by_role("heading", name="Ativar seu acesso")).to_be_visible()
                page.locator("form input").nth(0).fill("Diretora Escolar CI")
                page.locator("form input").nth(1).fill(secret)
                page.get_by_role("button", name="Aceitar convite").click()
                expect(page.get_by_text("Acesso ativado com sucesso.")).to_be_visible()
                page.get_by_role("link", name="Ir para o painel").click()

            # A administração escolar nunca deve exibir gestão global de organizações.
            expect(page.get_by_role("button", name="Escolas")).to_be_visible()
            expect(page.get_by_role("button", name="Organizações")).to_have_count(0)
            page.get_by_role("button", name="Escolas").click()
            school_form = page.locator("form.form-inline")
            school_form.locator("input").nth(0).fill(school)
            page.get_by_role("button", name="Adicionar", exact=True).click()
            expect(page.get_by_role("cell", name=school)).to_be_visible()

            page.get_by_role("button", name="Professores").click()
            teacher_form = page.locator("form.form-inline")
            teacher_form.locator("input").first.fill(teacher)
            teacher_form.locator("select").select_option(label=school)
            teacher_form.get_by_role("button", name="Cadastrar").click()
            expect(page.get_by_role("cell", name=teacher)).to_be_visible()
            page.get_by_role("button", name="Visualizar / editar").click()
            page.get_by_role("button", name="Adicionar faixa").click()
            page.get_by_role("button", name="Salvar disponibilidade").click()
            expect(page.get_by_text("Disponibilidade registrada.")).to_be_visible()

            page.get_by_role("button", name="Planejamento e grades").click()
            expect(page.get_by_role("heading", name="1. Selecione a escola e o ano letivo")).to_be_visible()
            section_year = page.get_by_role("heading", name="1. Selecione a escola e o ano letivo").locator("..")
            section_year.locator("form input[type=number]").fill("2028")
            section_year.locator("form input:not([type=number])").fill("Ano Letivo CI " + uid)
            section_year.get_by_role("button", name="Adicionar ano").click()
            expect(page.get_by_role("heading", name="2. Disciplinas e turmas")).to_be_visible()
            page.get_by_placeholder("Ex.: Matemática").fill(subject)
            page.get_by_role("button", name="Adicionar disciplina").click()
            expect(page.get_by_text("Disciplinas: " + subject)).to_be_visible()
            page.get_by_placeholder("Ex.: 6º Ano A").fill(klass)
            page.get_by_role("button", name="Adicionar turma").click()
            expect(page.get_by_role("heading", name="3. Horários de aula — " + klass)).to_be_visible()
            page.get_by_role("button", name="Salvar períodos").click()
            expect(page.get_by_text("Períodos salvos.")).to_be_visible()
            assignments = page.get_by_role("heading", name="4. Atribuir aulas semanais").locator("..")
            ass_form = assignments.locator("form")
            ass_form.locator("select").nth(0).select_option(label=subject)
            ass_form.locator("select").nth(1).select_option(label=teacher)
            ass_form.locator('input[type="number"]').first.fill("1")
            ass_form.get_by_role("button", name="Vincular carga horária").click()
            expect(assignments.get_by_role("cell", name=subject)).to_be_visible()
            page.get_by_role("button", name="Gerar prévia experimental").click()
            expect(page.get_by_text("Prévia calculada. Verifique pendências e limitações abaixo.")).to_be_visible(timeout=45000)
            expect(page.locator(".card").filter(has_text="Aulas distribuídas").locator(".metric")).to_have_text("1 aulas")
            expect(page.get_by_text("Cobertura completa")).to_be_visible()
            if after_preview is not None:
                after_preview(page, {"organization": org, "director_email": email,
                                     "director_password": secret, "manual_provisioning": manual_provisioning, "school": school,
                                     "teacher": teacher, "subject": subject,
                                     "class": klass, "year": 2028})
            print("SCHOOL_BROWSER_PASSED: convite, escopo do admin, escola, professor, disponibilidade, turma, atribuição e prévia.")
        finally:
            browser.close()

if __name__ == "__main__":
    main()
