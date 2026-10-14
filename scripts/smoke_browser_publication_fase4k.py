#!/usr/bin/env python3
"""Fase 4K — fluxo real da grade: duas contas, aprovação segregada e publicação.

Executar SOMENTE contra Next.js + FastAPI + PostgreSQL/RLS efêmeros do CI.
Parte do fixture escolar real da Fase 4J e exercita a UI de ponta a ponta;
requer também os testes críticos independentes de backend.
"""
import os
from urllib.parse import urljoin, urlsplit

from playwright.sync_api import expect
from smoke_browser_school_fase4j import BASE, main as school_flow


def _url(path):
    return urljoin(BASE.rstrip("/") + "/", path.lstrip("/"))


def _school_publish_flow(director_page, info):
    # Administrador da organização convida coordenador da escola.
    director_page.get_by_role("button", name="Convidar usuários").click()
    form = director_page.locator("form.grid-2")
    coordinator_email = "coordenador-4k-" + info["organization"].split()[-1] + "@example.com"
    coordinator_password = "SenhaCI-Coordenador-12345!"
    form.locator('input[type="email"]').fill(coordinator_email)
    form.locator("select").nth(0).select_option(label="Coordenador")
    form.locator("select").nth(1).select_option(label=info["school"])
    form.get_by_role("button", name="Enviar convite").click()
    expect(director_page.get_by_text("Convite criado.")).to_be_visible()
    invitation = director_page.locator(".code-link a").get_attribute("href")
    assert invitation and urlsplit(invitation).hostname in ("localhost", "127.0.0.1")

    # Sessões independentes: aceitar o convite não substitui o cookie do diretor.
    coordinator_context = director_page.context.browser.new_context(
        locale="pt-BR", viewport={"width": 1440, "height": 900})
    coordinator = coordinator_context.new_page()
    coordinator.set_default_timeout(18000)
    try:
        coordinator.goto(invitation, wait_until="domcontentloaded")
        expect(coordinator.get_by_role("heading", name="Ativar seu acesso")).to_be_visible()
        coordinator.locator("form input").nth(0).fill("Coordenador Escolar CI")
        coordinator.locator("form input").nth(1).fill(coordinator_password)
        coordinator.get_by_role("button", name="Aceitar convite").click()
        expect(coordinator.get_by_text("Acesso ativado com sucesso.")).to_be_visible()
        coordinator.get_by_role("link", name="Ir para o painel").click()
        expect(coordinator.get_by_role("button", name="Planejamento e grades")).to_be_visible()
        coordinator.get_by_role("button", name="Planejamento e grades").click()
        proposals = coordinator.locator('section[aria-label="Propostas para revisão"]')
        expect(proposals.get_by_role("heading", name="6. Propostas salvas e aprovação")).to_be_visible()
        proposals.get_by_role("button", name="Gerar e salvar nova proposta").click()
        expect(proposals.locator("tbody tr").first.get_by_text("Rascunho")).to_be_visible(timeout=45000)
        expect(proposals.get_by_role("button", name="Aprovar")).to_have_count(0)
        proposals.get_by_role("button", name="Enviar à revisão").click()
        expect(proposals.locator("tbody tr").first.get_by_text("Aguardando aprovação")).to_be_visible()
        assert proposals.locator("tbody tr").count() == 1, "CI deve ter somente uma proposta para a turma."

        # A UI do coordenador não pode expor publicação oficial.
        publication_coordinator = coordinator.locator('section[aria-label="Publicação oficial"]')
        expect(publication_coordinator.get_by_text(
            "Sua conta não possui permissão para publicação oficial.")).to_be_visible()
        expect(publication_coordinator.get_by_role(
            "button", name="Pré-validar publicação")).to_have_count(0)

        # Autorizações do backend também são verificadas, com CSRF real do usuário.
        me_response = coordinator_context.request.get(_url("/api/auth/me"))
        assert me_response.status == 200
        me = me_response.json()
        tenant_id = me["memberships"][0]["tenant_id"]
        csrf = me["csrf"]
        school_response = coordinator_context.request.get(_url(
            f"/api/tenants/{tenant_id}/schools"))
        assert school_response.status == 200
        school_id = next(s["id"] for s in school_response.json() if s["name"] == info["school"])
        pub_base = f"/api/tenants/{tenant_id}/publications"
        unauthorized = coordinator_context.request.post(_url(pub_base + "/publish"),
            data={"valid_from":"2028-02-07", "valid_to":"2028-02-11",
                  "parts":[{"school_id":school_id,"proposal_id":"invalid",
                            "class_ids":["invalid"]}]},
            headers={"X-CSRF-Token":csrf})
        assert unauthorized.status == 403, (
            "Coordenador sem grades.publish conseguiu tentar publicação: "
            + str(unauthorized.status) + " " + unauthorized.text()[:300])

        # Diretor é outra identidade: ele recebe e aprova a proposta.
        director_page.get_by_role("button", name="Planejamento e grades").click()
        director_proposals = director_page.locator('section[aria-label="Propostas para revisão"]')
        expect(director_proposals.locator("tbody tr").first.get_by_text(
            "Aguardando aprovação")).to_be_visible()
        director_proposals.locator("tbody tr").first.get_by_role(
            "button", name="Aprovar").click()
        expect(director_proposals.locator("tbody tr").first.get_by_text(
            "Aprovada (não publicada)")).to_be_visible()

        # Publicação é passo independente, apenas após a aprovação.
        official = director_page.locator('section[aria-label="Publicação oficial"]')
        # A aprovação deve atualizar a seção de publicação sem clique manual.
        expect(official.locator("#pub-proposal option")).to_have_count(2, timeout=18000)
        official.locator("#pub-proposal").select_option(index=1)
        official.locator('input[type="checkbox"]').first.check()
        official.locator("#pub-from").fill("2028-02-07")
        official.locator("#pub-to").fill("2028-02-11")
        official.get_by_role("button", name="Pré-validar publicação").click()
        expect(official.get_by_role("heading", name="Resultado da pré-validação")).to_be_visible()
        expect(official.get_by_text("1 aulas semanais", exact=False)).to_be_visible()
        official.get_by_label("Confirmo que revisei a vigência, a seleção e a autorização da publicação.").check()
        official.get_by_role("button", name="Publicar oficialmente (PostgreSQL)").click()
        expect(official.get_by_text("Lote publicado; consulte seu período de vigência no histórico.")).to_be_visible(timeout=30000)
        published_row = official.locator("tbody tr").filter(has_text="Completa")
        expect(published_row).to_have_count(1)
        assert "2028-02-07" in published_row.inner_text()

        # Os três relatórios devem ser servidos autenticados com conteúdo real.
        exports = (("CSV", "text/csv", b"\xef\xbb\xbf"),
                   ("PDF A4", "application/pdf", b"%PDF"),
                   ("Excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", b"PK"))
        for link_name, content_type, signature in exports:
            href = published_row.get_by_role("link", name=link_name).get_attribute("href")
            assert href and "/export." in href
            response = director_page.context.request.get(_url(href))
            assert response.status == 200, (link_name, response.status, response.text()[:150])
            assert content_type in response.headers.get("content-type", ""), (link_name,response.headers)
            body = response.body()
            assert body.startswith(signature), (link_name,body[:20])
            assert len(body) > 150, (link_name,len(body))

        # Repetir publicação da mesma turma/vigência não pode ser aceito.
        official.get_by_role("button", name="Pré-validar publicação").click()
        expect(official.get_by_text("vigência sobreposta", exact=False)).to_be_visible()
        expect(published_row).to_have_count(1)
        print("OFFICIAL_BROWSER_PASSED: coordenador sem permissão, segregação de aprovação, "
              "pré-validação, publicação, vigência exclusiva e exportações CSV/PDF/XLSX.")
    finally:
        coordinator_context.close()


if __name__ == "__main__":
    if urlsplit(BASE).hostname not in ("127.0.0.1", "localhost"):
        raise RuntimeError("O ensaio oficial exige ambiente local descartável.")
    school_flow(after_preview=_school_publish_flow)
