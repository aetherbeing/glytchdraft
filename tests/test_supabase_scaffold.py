from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATION = REPO_ROOT / "backend" / "supabase" / "migrations" / "202605270001_trace_economy_persistence.sql"
SETUP_DOC = REPO_ROOT / "SUPABASE_SETUP.md"


def read_text(path: Path) -> str:
    assert path.exists(), f"missing expected file: {path}"
    return path.read_text(encoding="utf-8")


def test_supabase_setup_doc_exists_and_covers_core_topics():
    text = read_text(SETUP_DOC)

    assert "Supabase Project" in text
    assert "backend/supabase/migrations/202605270001_trace_economy_persistence.sql" in text
    assert "backend/supabase/functions" in text
    assert "SUPABASE_URL" in text
    assert "SUPABASE_SERVICE_ROLE_KEY" in text
    assert "TRACE_ADMIN_API_KEY" in text
    assert "Stripe" in text
    assert "crypto/tokenomics" in text
    assert "AI companion" in text


def test_supabase_migration_declares_required_tables_views_and_rpcs():
    text = read_text(MIGRATION)

    required_tables = [
        "create table if not exists public.users",
        "create table if not exists public.structures",
        "create table if not exists public.trace_balances",
        "create table if not exists public.trace_transactions",
        "create table if not exists public.claimed_structures",
        "create table if not exists public.claim_history",
        "create table if not exists public.geosocial_posts",
    ]
    for needle in required_tables:
        assert needle in text

    assert "create or replace view public.structure_claim_status" in text
    assert "create or replace function public.create_structure_claim" in text
    assert "create or replace function public.record_trace_transaction" in text
    assert "create or replace function public.create_geosocial_post" in text


def test_supabase_migration_enforces_core_validation_and_claim_rules():
    text = read_text(MIGRATION)

    assert "charity_allocation_percentage >= 0 and charity_allocation_percentage <= 50" in text
    assert "claimed_structures_one_active_claim_per_structure" in text
    assert "where claim_status = 'active'" in text
    assert "Structure already has an active claim" in text
    assert "Trace transaction amount must be non-zero" in text
    assert "Insufficient Trace balance" in text


def test_supabase_functions_reference_expected_scaffold_endpoints():
    functions_root = REPO_ROOT / "backend" / "supabase" / "functions"
    expected = {
        "create-claim",
        "create-geosocial-post",
        "create-transaction-record",
        "get-structure-social-state",
        "get-user-balance",
        "list-claimed-structures",
        "update-charity-allocation",
    }

    actual = {path.name for path in functions_root.iterdir() if path.is_dir()}
    assert expected <= actual
