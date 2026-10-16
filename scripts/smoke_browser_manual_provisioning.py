"""Browser smoke test for manual user provisioning without SMTP."""
import os
import uuid

from playwright.sync_api import expect, sync_playwright

from phase4x2d_test_support import assert_local_candidate_url, browser_launch_options


BASE = os.environ.get("HI_BROWSER_URL", "http://127.0.0.1:3000")
ADMIN_EMAIL = os.environ.get("HI_BROWSER_ADMIN_EMAIL", "admin-e2e@example.com")
ADMIN_PASSWORD = os.environ.get("HI_BROWSER_ADMIN_PASSWORD")


def login(page, email: str, password: str) -> None:
    page.goto(BASE, wait_until="domcontentloaded", timeout=30000)
    expect(page.get_by_role("heading", name="Boas-vindas de volta")).to_be_visible()
    page.get_by_placeholder("voce@escola.com.br").fill(email)
    page.get_by_placeholder("Sua senha").fill(password)
    page.get_by_role("button", name="Entrar na plataforma").click()


def logout(page) -> None:
    page.get_by_title("Sair").click()
    expect(page.get_by_role("heading", name="Boas-vindas de volta")).to_be_visible()


def change_temporary_password(page, credentials: tuple[str, str], new_password: str) -> None:
    login(page, credentials[0], credentials[1])
    expect(page.get_by_role("heading", name="Crie sua senha pessoal")).to_be_visible()
    expect(page.get_by_test_id("new-password-input")).to_be_visible()
    expect(page.get_by_role("button", name="Visão geral")).to_have_count(0)
    page.get_by_test_id("new-password-input").fill(new_password)
    page.get_by_test_id("confirm-password-input").fill(new_password)
    page.get_by_test_id("change-password-submit").click()


def main() -> None:
    if not ADMIN_PASSWORD:
        raise RuntimeError("Defina HI_BROWSER_ADMIN_PASSWORD somente no ambiente PostgreSQL descartável.")
    assert_local_candidate_url(BASE)
    suffix = uuid.uuid4().hex[:8]
    first_admin_email = f"admin-{suffix}@example.com"
    teacher_email = f"professor-{suffix}@example.com"
    organization = f"Homologação manual {suffix}"
    school = f"Unidade de teste {suffix}"
    permanent_password = "Senha-Pessoal-E2E-2026!"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**browser_launch_options())
        try:
            page = browser.new_page(locale="pt-BR", viewport={"width": 1440, "height": 900})
            page.set_default_timeout(15000)
            login(page, ADMIN_EMAIL, ADMIN_PASSWORD)
            expect(page.get_by_role("button", name="Organizações")).to_be_visible()
            page.get_by_role("button", name="Organizações").click()
            form = page.locator("form.grid-3")
            form.locator("input").nth(0).fill(organization)
            form.locator("input").nth(1).fill("Administração de teste")
            form.locator("input").nth(2).fill(first_admin_email)
            page.get_by_test_id("create-organization-submit").click()
            dialog = page.get_by_test_id("credential-dialog")
            expect(dialog).to_be_visible()
            expect(dialog.get_by_text("Conta criada com senha temporária")).to_be_visible()
            expect(page.get_by_test_id("temporary-password-expiry")).to_be_visible()
            expect(page.get_by_test_id("dev-invitation-link")).to_have_count(0)
            first_admin_password = page.get_by_test_id("temporary-password-value").inner_text()
            assert len(first_admin_password) >= 20
            page.get_by_test_id("credential-close").click()
            expect(page.get_by_test_id("credential-dialog")).to_have_count(0)
            expect(page.get_by_test_id("temporary-password-value")).to_have_count(0)

            logout(page)
            change_temporary_password(
                page,
                (first_admin_email, first_admin_password),
                permanent_password,
            )
            expect(page.get_by_role("button", name="Escolas")).to_be_visible()
            page.get_by_role("button", name="Escolas").click()
            school_form = page.locator("form.form-inline")
            school_form.locator("input").first.fill(school)
            page.get_by_role("button", name="Adicionar", exact=True).click()
            expect(page.get_by_role("cell", name=school)).to_be_visible()

            page.get_by_role("button", name="Usuários", exact=True).click()
            expect(page.get_by_role("heading", name="Usuários e permissões")).to_be_visible()
            page.get_by_test_id("user-name-input").fill("Professora de teste")
            page.get_by_test_id("user-email-input").fill(teacher_email)
            role_select = page.get_by_test_id("user-role-select")
            role_labels = role_select.locator("option").all_text_contents()
            teacher_role = next((label.strip() for label in role_labels if "Professor" in label), None)
            if not teacher_role:
                raise AssertionError("O perfil de professor não foi oferecido para este administrador.")
            role_select.select_option(label=teacher_role)
            page.get_by_test_id("user-school-select").select_option(label=school)
            page.get_by_test_id("create-user-submit").click()
            dialog = page.get_by_test_id("credential-dialog")
            expect(dialog).to_be_visible()
            expect(dialog.get_by_text("Conta criada com senha temporária")).to_be_visible()
            expect(page.get_by_test_id("temporary-password-expiry")).to_be_visible()
            expect(page.get_by_test_id("dev-invitation-link")).to_have_count(0)
            teacher_password = page.get_by_test_id("temporary-password-value").inner_text()
            assert len(teacher_password) >= 20
            page.get_by_test_id("credential-close").click()
            expect(page.get_by_test_id("credential-dialog")).to_have_count(0)
            expect(page.get_by_test_id("temporary-password-value")).to_have_count(0)

            logout(page)
            change_temporary_password(
                page,
                (teacher_email, teacher_password),
                "Senha-Docente-E2E-2026!",
            )
            expect(page.get_by_role("button", name="Meu acesso docente")).to_be_visible()
            print("MANUAL_PROVISIONING_BROWSER_PASSED: conta, senha única, expiração e troca obrigatória no Chromium.")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
