import score


def filing(year, form="990", revenue=100_000, expenses=90_000, contributions=80_000,
           net_assets=50_000, officer_comp=10_000, fundraising_expense=0):
    return dict(
        tax_period=year * 100 + 12, tax_year=year, form=form, revenue=revenue,
        expenses=expenses, contributions=contributions, net_assets=net_assets,
        officer_comp=officer_comp, fundraising_expense=fundraising_expense,
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


def test_ez_filer_lacks_990_only_components():
    result = score.score([filing(2022, form="990EZ"), filing(2023, form="990EZ")],
                         current_year=2026)
    assert result["components"]["officer_comp"]["score"] is None
    assert result["components"]["fundraising_cost"]["score"] is None
    assert result["confidence"] == 0.75
    assert 0 <= result["score"] <= 100


def test_full_990_filer_has_full_confidence():
    fl = [filing(y) for y in range(2020, 2025)]
    result = score.score(fl, current_year=2026)
    assert result["confidence"] == 1.0
    assert result["years_on_file"] == 5
    assert result["latest_year"] == 2024
    assert result["components"]["filing_consistency"]["score"] == 100


def test_stale_filer_loses_consistency_points():
    result = score.score([filing(2018), filing(2019)], current_year=2026)
    assert result["components"]["filing_consistency"]["score"] == 0


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
    empty = tmp_path / "x.db"
    db.connect(empty).close()          # schema only, no scores
    assert not db.ensure_database(empty, url="http://127.0.0.1:9/nothing.gz")
    assert not empty.exists()          # the empty file is cleared for the next try
    full = tmp_path / "y.db"
    conn = db.connect(full)
    db.save_scores(conn, {"1": dict(score=1, confidence=1, components={}, latest_year=2024,
                                    latest_revenue=1, years_on_file=1, size_band="Unknown")})
    conn.close()
    assert db.ensure_database(full, url="http://127.0.0.1:9/nothing.gz")
