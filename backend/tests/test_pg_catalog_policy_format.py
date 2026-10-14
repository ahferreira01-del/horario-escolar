"""Regressão: pg_policies faz cast da coluna VARCHAR para TEXT ao serializar a expressão.

O controle continua aceitando apenas uma igualdade canônica; não libera OR/AND.
"""
import pytest
from app.runtime_checks import _policy_has_context


@pytest.mark.parametrize("column, setting", [
    ("tenant_id", "app.tenant_id"),
    ("user_id", "app.user_id"),
])
def test_pg_policies_canonical_varchar_cast_is_accepted(column, setting):
    expression = (
        f"(({column})::text = NULLIF(current_setting('{setting}'::text, true), ''::text))"
    )
    assert _policy_has_context(expression, setting, column)


@pytest.mark.parametrize("bad_expression", [
    "((tenant_id)::text = NULLIF(current_setting('app.tenant_id'::text, true), ''::text)) OR true",
    "((tenant_id)::text = NULLIF(current_setting('app.user_id'::text, true), ''::text))",
    "tenant_id = tenant_id AND current_setting('app.tenant_id', true) IS NOT NULL",
    "((tenant_id)::text = NULLIF(current_setting('app.tenant_id'::text, true), ''::text)) AND true",
])
def test_pg_policies_rejects_bypass_or_wrong_setting(bad_expression):
    assert not _policy_has_context(bad_expression, "app.tenant_id", "tenant_id")
