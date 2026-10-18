import fmt
import ui


def test_fmt_inr_uses_indian_grouping():
    assert fmt.inr(1234567) == "₹12,34,567"
    assert fmt.inr(3999) == "₹3,999"
    assert fmt.inr(0) == "₹0"
    assert fmt.inr(None) == "–"


def test_fmt_pct_and_num():
    assert fmt.pct(0.1234) == "12.3%"
    assert fmt.pct(0) == "0.0%"
    assert fmt.pct(None) == "–"
    assert fmt.num(1234) == "1,234"
    assert fmt.num(None) == "–"


def test_tile_escapes_everything_and_marks_status_with_a_label():
    html = ui.tile("<script>x</script>", "<b>1</b>", sub="a & b", status="off_track")
    assert "<script>" not in html and "&lt;script&gt;" in html and "&lt;b&gt;1&lt;/b&gt;" in html and "a &amp; b" in html
    assert "Off track" in html                                           # a status is never colour alone
    assert "\n" not in html                                              # one line: Markdown would treat indented HTML as code


def test_banner_says_dummy_data():
    assert "Dummy data" in ui.banner()


def test_missing_values_include_nan():
    nan = float("nan")
    assert fmt.inr(nan) == "–" and fmt.pct(nan) == "–" and fmt.num(nan) == "–"


def test_table_escapes_cells_and_applies_formatters():
    html = ui.table([{"name": "<i>x</i>", "spend": 1234567, "gap": None}],
                    [("name", "Campaign", None), ("spend", "Spend", fmt.inr), ("gap", "Gap", fmt.pct)])
    assert "<i>" not in html and "&lt;i&gt;x&lt;/i&gt;" in html and "₹12,34,567" in html and "–" in html
    assert html.count("<th>") == 3 and "\n" not in html


def test_table_with_no_rows_says_so():
    assert "Nothing to show" in ui.table([], [("name", "Campaign", None)])


def test_chip_keeps_the_label_and_never_relies_on_colour():
    html = ui.chip("<b>Needs a change</b>", "off_track")
    assert "&lt;b&gt;" in html and "✕" in html


def test_meter_clamps_the_bar_and_reports_the_real_share():
    assert 'style="width:100%"' in ui.meter(150, 100) and "150%" in ui.meter(150, 100)
    assert 'style="width:40%"' in ui.meter(40, 100)
    assert "No target" in ui.meter(40, None)


def test_css_hides_the_deploy_toolbar_and_keeps_tiles_the_same_height():
    assert 'data-testid="stToolbar"' in ui.CSS and "stAppDeployButton" in ui.CSS
    assert "stHeader" in ui.CSS and "transparent" in ui.CSS            # the header stays (it holds the sidebar toggle) but no longer covers the page
    assert "min-height: 128px" in ui.CSS


def test_small_whole_number_counts_get_whole_number_ticks():
    from views import charts
    assert charts.whole_ticks([2, 4]) is True
    assert charts.whole_ticks([2.5, 4]) is False
    assert charts.whole_ticks([1200, 3400]) is False                   # big counts keep the default ticks
    assert charts.whole_ticks([]) is False


def test_css_lets_the_page_use_the_full_width():
    assert "max-width: none !important" in ui.CSS and 'data-testid="stMainBlockContainer"' in ui.CSS
    assert "max-width: 1180px" not in ui.CSS


def test_css_spaces_the_overview_links_from_the_tiles():
    assert "stPageLink" in ui.CSS


def test_facts_escapes_and_shows_a_dash_for_missing_values():
    html = ui.facts([("Parent", "<b>x</b>"), ("City", None)])
    assert "&lt;b&gt;x&lt;/b&gt;" in html and "<b>" not in html and "–" in html and "\n" not in html


def test_css_gives_tile_rows_charts_and_tables_room_so_nothing_touches_the_block_before_it():
    assert 'data-testid="stHorizontalBlock"' in ui.CSS and "margin-bottom: 1.4rem" in ui.CSS            # a row of tiles keeps clear of what follows
    assert "stVegaLiteChart" in ui.CSS and "margin: 1rem 0" in ui.CSS                                    # a chart has air above and below it
    assert ".gt-table { margin-top: .4rem" in ui.CSS.replace(".gt-table {  ", ".gt-table { ") or "margin-top: .4rem" in ui.CSS
    assert "stExpander" in ui.CSS                                                                          # the table-view expander is separated from its chart


def test_verdict_chip_uses_an_icon_and_a_word_never_colour_alone():
    assert "✓" in ui.verdict_chip("Scale") and "✕" in ui.verdict_chip("Pause") and "–" in ui.verdict_chip("Too early") and "!" in ui.verdict_chip("Refresh") and "!" in ui.verdict_chip("Hold")
    assert "Hold: recent acquisition cost worsening" in ui.verdict_chip("Hold", "Hold: recent acquisition cost worsening")


def test_verdict_table_keeps_the_action_the_reasons_the_flags_and_the_evidence_apart_and_escapes_everything():
    rows = [dict(campaign_id="<b>C</b>", name="A <i>name</i>", verdict="Pause", label="Pause", reasons=["why 1 <x>", "why 2"], flags=["flag <y>"], confidence="Enough evidence: 40"),
            dict(campaign_id="D", name="n", verdict="Too early", label="Too early", reasons=[], flags=[], confidence="Too early: 5 of 14 days")]
    html = ui.verdict_table(rows)
    assert "<b>C" not in html and "&lt;b&gt;C" in html and "&lt;x&gt;" in html and "&lt;y&gt;" in html and "&lt;i&gt;" in html
    for heading in ("Campaign", "Verdict", "Why", "Flags", "Evidence"):
        assert f"<th>{heading}</th>" in html
    assert html.count("<li>") == 3 and "✕" in html and "\n" not in html
    assert ui.verdict_table([]).startswith('<div class="gt-empty">')


def test_css_aligns_table_cells_to_the_top_so_long_reasons_do_not_float():
    assert "vertical-align: top" in ui.CSS and ".gt-list" in ui.CSS
