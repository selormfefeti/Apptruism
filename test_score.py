import score


def filing(year, form="990", revenue=100_000, expenses=90_000, contributions=80_000,
           net_assets=50_000, officer_comp=10_000):
    return dict(
        tax_period=year * 100 + 12, tax_year=year, form=form, revenue=revenue,
        expenses=expenses, contributions=contributions, net_assets=net_assets,
        officer_comp=officer_comp,
    )


def test_piecewise_clamps_and_interpolates():
    knots = [(0, 0), (10, 100)]
    assert score.piecewise(-5, knots) == 0
    assert score.piecewise(50, knots) == 100
    assert score.piecewise(5, knots) == 50


def test_donor_growth_is_cagr_over_first_and_last_year():
    fl = [filing(2020, contributions=100_000), filing(2021, contributions=1),
          filing(2022, contributions=144_000)]
    assert abs(score.donor_growth(fl) - 0.20) < 1e-9


def test_donor_growth_needs_two_years():
    assert score.donor_growth([filing(2022)]) is None
    assert score.donor_growth([]) is None


def test_margin_is_the_median_of_the_last_three_years():
    fl = [filing(2020, expenses=200_000), filing(2021, expenses=95_000),
          filing(2022, expenses=90_000), filing(2023, expenses=150_000)]
    # last three: -0.5 (2021? no: 2021 +0.05, 2022 +0.10, 2023 -0.50) -> median 0.05
    assert abs(score.median_margin(score.one_per_year(fl)) - 0.05) < 1e-9


def test_weights_sum_to_one_for_each_form():
    for form, weights in score.WEIGHTS.items():
        assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_ez_filer_can_reach_full_confidence():
    fl = [filing(y, form="990EZ", net_assets=50_000 + 10_000 * (y - 2019)) for y in range(2019, 2025)]
    result = score.score(fl, current_year=2026)
    assert "officer_comp" not in result["components"]
    assert result["confidence_factors"]["coverage"] == 1.0
    assert result["confidence"] == 1.0


def test_thin_history_lowers_confidence_not_score():
    one = score.score([filing(2024)], current_year=2026)
    assert one["confidence_factors"]["depth"] == 0.4
    assert one["confidence"] < 0.5
    assert one["score"] is not None


def test_old_return_lowers_confidence():
    result = score.score([filing(2019), filing(2020)], current_year=2026)
    assert result["confidence_factors"]["recency"] == 0.2


def test_zero_officer_pay_at_a_large_org_is_unknown():
    big = score.score([filing(2024, expenses=2_000_000, revenue=2_100_000, officer_comp=0)])
    assert big["components"]["officer_comp"]["score"] is None
    small = score.score([filing(2024, officer_comp=0)])
    assert small["components"]["officer_comp"]["score"] == 100


def test_reconciliation_flags_numbers_that_do_not_add_up():
    clean = [filing(2022, net_assets=50_000), filing(2023, net_assets=60_000)]  # +10k surplus, +10k assets
    assert score.reconciliation(clean) == 1.0
    off = [filing(2022, net_assets=50_000), filing(2023, net_assets=500_000)]
    assert score.reconciliation(off) == 0.7


def test_private_foundations_are_ignored():
    assert score.score([filing(2023, form="990PF")]) is None


def test_size_bands():
    assert score.size_band(None) == "Unknown"
    assert score.size_band(50_000) == "Under $100k"
    assert score.size_band(5_000_000) == "$1M to $10M"
    assert score.size_band(50_000_000) == "Over $10M"


def test_cause_percentiles_rank_within_each_cause():
    scores = {"a": 90.0, "b": 70.0, "c": 50.0, "d": 80.0, "e": None}
    causes = {"a": "Animal Rights", "b": "Animal Rights", "c": "Animal Rights", "d": "Environmental"}
    out = score.cause_percentiles(scores, causes)
    assert out["a"] == (1, 3, 100.0)
    assert out["b"] == (2, 3, round(100 * 2 / 3, 1))
    assert out["c"] == (3, 3, round(100 / 3, 1))
    assert out["d"] == (1, 1, 100.0)
    assert "e" not in out


def test_ensure_database_retries_when_local_db_is_empty(tmp_path):
    import db
    bad = "http://127.0.0.1:9/nothing.gz"
    empty = tmp_path / "x.db"
    db.connect(empty).close()          # schema only, no scores
    assert db.ensure_database(empty, url=bad, check_remote=False) is None
    assert not empty.exists()          # the empty file is cleared for the next try

    full = tmp_path / "y.db"
    conn = db.connect(full)
    db.save_scores(conn, {"1": dict(score=1, confidence=1, components={}, latest_year=2024,
                                    latest_revenue=1, years_on_file=1, size_band="Unknown")})
    assert db.ensure_database(full, url=bad, check_remote=False) == "present"

    conn.execute("UPDATE scores SET computed_at = '2020-01-01T00:00:00+00:00'")
    conn.commit()
    conn.close()
    # Stale, but the download fails, so the old file stays in use.
    assert db.ensure_database(full, url=bad, max_age_days=35, check_remote=False) == "present"
    assert full.exists()


def test_ntee_maps_to_causes():
    import db
    assert db.ntee_cause("P20") == "Human Services"
    assert db.ntee_cause("W30") == "Military & Veterans"
    assert db.ntee_cause("W20") == "Public & Societal Benefit"
    assert db.ntee_cause("") is None
    # NTEE wins when present; the 2019 tag is only a fallback
    assert db.cause_for("Educational Institutions and Related Activities", "A65") == ("Arts, Culture & Humanities", "NTEE")
    assert db.cause_for("Animal Rights", None) == ("Animals", "2019 tag")
    assert db.cause_for("Other", None) == ("Uncategorized", "none")
    # veterans' posts are coded all over NTEE; the name wins for that cause
    assert db.cause_for(None, "B90", "Veterans Of Foreign Wars Post 123") == ("Military & Veterans", "name")
    assert db.cause_for(None, "P20", "American Legion Auxiliary Unit 5") == ("Military & Veterans", "name")
    assert db.cause_for(None, "P20", "Veterinary Fund") == ("Human Services", "NTEE")
    assert db.cause_for("Uncategorized", None) == ("Uncategorized", "none")


def _bmf_row(ein, subsection="03", filing_req="01", income="120000", ntee="P20", name="X"):
    return {"EIN": ein, "NAME": name, "CITY": "C", "STATE": "NJ", "ZIP": "07000", "SUBSECTION": subsection,
            "FILING_REQ_CD": filing_req, "INCOME_AMT": income, "REVENUE_AMT": income, "ASSET_AMT": "0",
            "RULING": "202301", "NTEE_CD": ntee}


def test_universe_target_filter():
    import universe
    assert universe.is_target(_bmf_row("1"))
    assert not universe.is_target(_bmf_row("2", subsection="06"))
    assert not universe.is_target(_bmf_row("3", filing_req="02"))
    assert not universe.is_target(_bmf_row("4", income="20000"))
    assert not universe.is_target(_bmf_row("5", income=""))


def test_universe_refresh_feeds_fetch_and_marks_absent_orgs_inactive(tmp_path):
    import db, universe
    conn = db.connect(tmp_path / "u.db")
    # two orgs already fetched: one still in the master file, one gone
    db.save_org(conn, "000000001", {"ein": "000000001", "name": "Stays"}, [], "ok")
    db.save_org(conn, "000000002", {"ein": "000000002", "name": "Gone"}, [], "ok")
    rows = [_bmf_row("000000001"), _bmf_row("000000003", name="New target"),
            _bmf_row("000000004", filing_req="02")]  # postcard filer: present but not a target
    counts = universe.refresh(conn, rows, stamp="2026-09-08T00:00:00+00:00")
    assert counts["in_target"] == 2
    assert counts["fetched_now_inactive"] == 1
    assert db.pending_eins(conn) == ["000000003"]
    active = {r["ein"]: r["active"] for r in conn.execute("SELECT ein, active FROM orgs")}
    assert active == {"000000001": 1, "000000002": 0}
    # a later refresh without org 3 drops it from the universe
    universe.refresh(conn, [_bmf_row("000000001")], stamp="2026-10-08T00:00:00+00:00")
    assert conn.execute("SELECT COUNT(*) FROM universe").fetchone()[0] == 1
    # refetching an inactive org keeps it inactive
    db.save_org(conn, "000000002", {"ein": "000000002", "name": "Gone"}, [], "ok")
    assert conn.execute("SELECT active FROM orgs WHERE ein='000000002'").fetchone()[0] == 0
