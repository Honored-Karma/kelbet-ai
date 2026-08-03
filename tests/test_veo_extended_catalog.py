from kelbet.catalog.pricing import compute_user_credit_price
from kelbet.catalog.seeds import catalog_model_rows, feature_flag_rows


def test_veo_extended_catalog_is_off_by_default_and_truthful() -> None:
    flag = next(row for row in feature_flag_rows() if row["key"] == "veo_extended")
    assert flag["enabled"] is False

    model = next(
        row
        for row in catalog_model_rows()
        if row["slug"] == "google-veo31-fast-extended-video"
    )
    assert model["feature_flag"] == "veo_extended"
    assert model["provider_model_id"] == "veo-3.1-fast-generate-preview"
    assert model["capabilities"]["durations_sec"] == [8, 15, 22, 29]
    assert model["capabilities"]["resolutions"] == ["720p"]
    assert model["capabilities"]["supports_seed"] is False
    assert model["capabilities"]["workflow"] == {
        "type": "veo_extend",
        "initial_duration_sec": 8,
        "extension_duration_sec": 7,
        "cumulative_durations_sec": [8, 15, 22, 29],
        "final_output_only": True,
        "fallback": False,
    }
    assert "fallback" not in model["capabilities"]


def test_veo_extended_price_tracks_output_seconds() -> None:
    """Each extend call bills only its own 7 new seconds, so price is linear.

    Provider cost is $0.10 per output second on Veo 3.1 Fast, and one credit covers
    $0.004 of provider cost, so an 8s base clip is 200 credits and every additional
    second is 25 credits. The previous 1x/2x/3x/4x duration steps charged 2000 credits
    for a 29s clip against a $2.90 cost — roughly 3x over, which priced long video out
    of the market rather than protecting margin.
    """
    model = next(
        row
        for row in catalog_model_rows()
        if row["slug"] == "google-veo31-fast-extended-video"
    )
    assert model["user_credit_price"] == 200

    expected = {8: 200, 15: 375, 22: 550, 29: 725}
    for duration, credits in expected.items():
        assert (
            compute_user_credit_price(
                model["user_credit_price"],
                params={"duration_sec": duration},
                pricing_rules=model["pricing_rules"],
            )
            == credits
        )
        # 25 credits per output second, at $0.004 of cost per credit.
        assert credits == 25 * duration
