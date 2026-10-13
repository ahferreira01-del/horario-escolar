"""Tests Phase 4A review proposal (no publication)."""
from test_app import context, tenant_with_admin, school, invitation, accept, login
from test_planning import pfx, configure, set_periods, teacher, availability, assign
from app.workflow import safe_csv


def ready(client, suffix, lessons=3, possible=True):
    tid, admin = tenant_with_admin(client, suffix)
    sid = school(client, tid, admin)
    prefix = pfx(tid, sid)
    year, subj, klass = configure(client, tid, sid, admin)
    assert set_periods(client, prefix, klass, admin).status_code == 200
    prof = teacher(client, tid, sid, admin)
    assert availability(client, tid, prof, admin, "07:00" if possible else "10:45", "11:00" if possible else "12:00").status_code == 200
    assert assign(client, prefix, klass, subj, prof, admin, lessons=lessons).status_code == 201
    return tid, sid, year, prof, admin


def proposals(client, tid, sid):
    return pfx(tid, sid) + "/proposals"


def create(client, tid, sid, year, headers):
    return client.post(proposals(client, tid, sid), headers=headers,
                       json={"academic_year_id": year, "time_limit": 5})


def coordinator(client, tid, sid, admin, email="coord@example.com"):
    token = invitation(client, tid, admin, "coordinator", sid, email)
    return accept(client, tid, token, "Coordenador")


def test_create_list_and_export_are_school_scoped(context):
    client, _ = context
    tid, sid, year, teacher_id, admin = ready(client, "proposal")
    p = create(client, tid, sid, year, admin)
    assert p.status_code == 201, p.text
    data = p.json()
    assert data["status"] == "draft" and data["published"] is False
    pid = data["id"]
    uri = proposals(client, tid, sid)
    got = client.get(uri + "/" + pid)
    assert got.status_code == 200 and got.json()["snapshot"]["total_assigned"] == 3
    csv_file = client.get(uri + f"/{pid}/export.csv")
    assert csv_file.status_code == 200
    assert "PROPOSTA NÃO PUBLICADA" in csv_file.content.decode("utf-8-sig")
    assert len(client.get(uri + "?academic_year_id=" + year).json()) == 1
    sid2 = school(client, tid, admin, "Outra")
    assert client.get(proposals(client, tid, sid2) + "/" + pid).status_code == 404
    assert client.get(proposals(client, tid, sid2) + f"/{pid}/export.csv").status_code == 404
    assert client.post(uri + "/" + pid + "/publish", headers=admin).status_code == 404


def test_separation_and_approval(context):
    client, _ = context
    tid, sid, year, _, admin = ready(client, "approval")
    coord = coordinator(client, tid, sid, admin)
    uri = proposals(client, tid, sid)
    r = create(client, tid, sid, year, coord)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    r = client.post(uri + f"/{pid}/submit", json={}, headers=coord)
    assert r.status_code == 200, r.text
    assert client.post(uri + f"/{pid}/approve", json={}, headers=coord).status_code == 403
    admin = login(client, "diretor-approval@example.com", "Senha-forte-diretor-123")
    r = client.post(uri + f"/{pid}/approve", json={"note": "Conferido"}, headers=admin)
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert client.post(uri + f"/{pid}/approve", json={}, headers=admin).status_code == 409
    assert client.post(uri + f"/{pid}/submit", json={}, headers=admin).status_code == 409
    assert client.get(uri + f"/{pid}").json()["snapshot"]["result"] == "complete"
    # Org admin created grade: cannot self-approve either.
    own = create(client, tid, sid, year, admin)
    assert own.status_code == 201
    ownid = own.json()["id"]
    assert client.post(uri + f"/{ownid}/submit", json={}, headers=admin).status_code == 200
    assert client.post(uri + f"/{ownid}/approve", json={}, headers=admin).status_code == 403


def test_partial_requires_reason_and_exceptional_permission(context):
    client, _ = context
    tid, sid, year, _, admin = ready(client, "partial", lessons=2, possible=False)
    coord = coordinator(client, tid, sid, admin, "coord-partial@example.com")
    uri = proposals(client, tid, sid)
    r = create(client, tid, sid, year, coord)
    assert r.status_code == 201, r.text
    assert r.json()["result"] == "partial"
    pid = r.json()["id"]
    assert client.post(uri + f"/{pid}/submit", json={}, headers=coord).status_code == 422
    assert client.post(uri + f"/{pid}/submit", json={"justification": "Aguardando ampliação da disponibilidade."}, headers=coord).status_code == 200
    admin = login(client, "diretor-partial@example.com", "Senha-forte-diretor-123")
    r = client.post(uri + f"/{pid}/approve", json={}, headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved" and r.json()["pending_count"] >= 1


def test_school_admin_cannot_approve_partial_without_special_privilege(context):
    client, _ = context
    tid, sid, year, _, admin = ready(client, "partialrole", possible=False)
    coord = coordinator(client, tid, sid, admin, "coordinator2@example.com")
    p = create(client, tid, sid, year, coord)
    pid = p.json()["id"]
    assert client.post(proposals(client, tid, sid) + f"/{pid}/submit", headers=coord, json={"justification": "Falta disponibilidade."}).status_code == 200
    admin = login(client, "diretor-partialrole@example.com", "Senha-forte-diretor-123")
    token = invitation(client, tid, admin, "school_admin", sid, "escolar@example.com")
    school_admin = accept(client, tid, token, "Admin escola")
    assert client.post(proposals(client, tid, sid) + f"/{pid}/approve", headers=school_admin, json={}).status_code == 403


def test_stale_proposal_cannot_submit_or_approve(context):
    client, _ = context
    tid, sid, year, teacher_id, admin = ready(client, "stale")
    coord = coordinator(client, tid, sid, admin, "coord-stale@example.com")
    uri = proposals(client, tid, sid)
    saved = create(client, tid, sid, year, coord)
    pid = saved.json()["id"]
    admin = login(client, "diretor-stale@example.com", "Senha-forte-diretor-123")
    change = client.put(f"/api/tenants/{tid}/teachers/{teacher_id}/availability", headers=admin,
                        json={"intervals": [{"weekday": 0, "start": "07:10", "end": "08:40"}]})
    assert change.status_code == 200
    coord = login(client, "coord-stale@example.com", "senha-super-segura-123")
    assert client.post(uri + f"/{pid}/submit", headers=coord, json={}).status_code == 409
    pid2 = create(client, tid, sid, year, coord).json()["id"]
    assert client.post(uri + f"/{pid2}/submit", headers=coord, json={"justification": "Nova condição."}).status_code == 200
    admin = login(client, "diretor-stale@example.com", "Senha-forte-diretor-123")
    assert client.put(f"/api/tenants/{tid}/teachers/{teacher_id}/availability", headers=admin,
                      json={"intervals": [{"weekday": 0, "start": "09:00", "end": "09:45"}]}).status_code == 200
    assert client.post(uri + f"/{pid2}/approve", headers=admin, json={}).status_code == 409


def test_reject_requires_reason_and_audit(context):
    client, _ = context
    tid, sid, year, _, admin = ready(client, "reject")
    coord = coordinator(client, tid, sid, admin, "coord-reject@example.com")
    uri = proposals(client, tid, sid)
    pid = create(client, tid, sid, year, coord).json()["id"]
    assert client.post(uri + f"/{pid}/submit", headers=coord, json={}).status_code == 200
    admin = login(client, "diretor-reject@example.com", "Senha-forte-diretor-123")
    assert client.post(uri + f"/{pid}/reject", headers=admin, json={}).status_code == 422
    r = client.post(uri + f"/{pid}/reject", headers=admin, json={"note": "Rever distribuição"})
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert client.post(uri + f"/{pid}/approve", headers=admin, json={}).status_code == 409
    actions = [a["action"] for a in client.get(f"/api/tenants/{tid}/audit").json()]
    assert "grade.proposal.rejected" in actions


def test_no_cross_tenant_proposal_access(context):
    client, _ = context
    a, sa, ya, _, a_admin = ready(client, "alpha4")
    pid = create(client, a, sa, ya, a_admin).json()["id"]
    b, sb, yb, _, b_admin = ready(client, "beta4")
    uri = proposals(client, a, sa) + "/" + pid
    assert client.get(uri).status_code == 403
    assert client.get(uri + "/export.csv").status_code == 403
    assert client.post(uri + "/submit", headers=b_admin, json={}).status_code == 403
    assert client.get(proposals(client, b, sb) + "/" + pid).status_code == 404


def test_csv_formula_protection():
    assert safe_csv('=HYPERLINK("x")').startswith("'")
    assert safe_csv("  +danger").startswith("'")
    assert safe_csv("Normal") == "Normal"
