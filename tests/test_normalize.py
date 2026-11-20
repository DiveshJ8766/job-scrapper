from pipeline.cities import canonical_city, city_supported_by, find_cities, mentions_remote
from pipeline.normalize import (
    canonicalize_url, content_hash, dedupe_key, html_to_text, normalize_company, normalize_title,
)


def test_canonicalize_strips_tracking_and_www():
    a = canonicalize_url("https://www.Example.com/jobs/123/?utm_source=x&gh_src=abc#apply")
    b = canonicalize_url("http://example.com/jobs/123")
    assert a == b == "https://example.com/jobs/123"


def test_canonicalize_keeps_identifying_params():
    assert canonicalize_url("https://acme.com/careers?gh_jid=42&utm_medium=x") == \
        "https://acme.com/careers?gh_jid=42"


def test_canonicalize_adzuna_uses_path_only():
    assert canonicalize_url("https://www.adzuna.in/jobs/land/ad/555?se=abc&v=123") == \
        "https://adzuna.in/jobs/land/ad/555"


def test_company_normalization():
    assert normalize_company("Razorpay Software Pvt. Ltd.") == "razorpay software"
    assert normalize_company("Google India Private Limited") == "google"
    assert normalize_company("AT&T Inc") == "at and t"


def test_title_normalization():
    assert normalize_title("Sr. Software Engg - Backend") == "senior software engineer backend"


def test_dedupe_key_uses_canonical_city():
    assert dedupe_key("Acme Pvt Ltd", "SDE 1", "Bangalore, Karnataka") == \
        dedupe_key("ACME", "sde-1", "Bengaluru")


def test_dedupe_key_distinguishes_cities():
    assert dedupe_key("Acme", "SDE", "Pune") != dedupe_key("Acme", "SDE", "Mumbai")


def test_content_hash_ignores_whitespace_but_not_content():
    h1 = content_hash("A", "B", "Pune", None, "hello  world")
    assert h1 == content_hash("A", "B", "Pune", None, "hello world")
    assert h1 != content_hash("A", "B", "Pune", None, "hello there")


def test_html_to_text_unescapes_greenhouse_content():
    raw = "&lt;p&gt;Build &amp;amp; ship&lt;/p&gt;&lt;ul&gt;&lt;li&gt;React&lt;/li&gt;&lt;/ul&gt;"
    assert html_to_text(raw) == "Build & ship\n\nReact"


def test_city_helpers():
    assert canonical_city("Bangalore") == "Bengaluru"
    assert canonical_city("gurgaon") == "Gurugram"
    assert find_cities("Navi Mumbai / New Delhi / Hyderabad") == ["Mumbai", "Delhi", "Hyderabad"]
    assert mentions_remote("Remote - India")
    assert not mentions_remote("Hybrid, Pune")
    assert city_supported_by("Bengaluru", "Office: Bangalore")
    assert not city_supported_by("Chennai", "Bangalore", "We are a Bangalore startup")
