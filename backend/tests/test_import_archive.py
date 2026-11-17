import uuid

from app.models import AssetStatus, License, LicenseType, Movie, MovieStatus, VideoAsset
from scripts.import_archive import Candidate, clean_description, clean_title, pick_feature, rights_for


def item(title="Metropolis", files=None, **meta):
    return {
        "metadata": {"title": title, "year": "1927", "collection": ["feature_films"], **meta},
        "files": files if files is not None else [
            {"name": "metropolis.avi", "source": "original"},
            {"name": "metropolis.mp4", "format": "h.264", "length": "6900.5", "size": "900000000", "source": "derivative"},
            {"name": "metropolis_512kb.mp4", "format": "512Kb MPEG4", "length": "6900.5", "size": "300000000"},
        ],
    }  # fmt: skip


def test_picks_the_best_feature_file():
    c = pick_feature("metropolis1927", item(), downloads=5000)
    assert c and c.file_name == "metropolis.mp4" and c.year == 1927 and round(c.seconds) == 6900
    assert c.playback_url == "https://archive.org/download/metropolis1927/metropolis.mp4"
    assert c.poster_url == "https://archive.org/services/img/metropolis1927"


def test_rejects_shorts_rips_trailers_and_multipart():
    short = item(files=[{"name": "a.mp4", "format": "h.264", "length": "900"}])
    assert pick_feature("x", short) is None  # 15 min: not a feature
    assert pick_feature("x", item(title="Metropolis 1080p BluRay x264-YTS")) is None
    assert pick_feature("x", item(collection=["movie_trailers"])) is None
    multi = item(files=[{"name": "p1.mpeg", "source": "original"}, {"name": "p2.mpeg", "source": "original"},
                        {"name": "a.mp4", "format": "h.264", "length": "5000"}])  # fmt: skip
    assert pick_feature("x", multi) is None
    assert pick_feature("x", item(title="")) is None


def test_cleaning():
    assert clean_title("Nosferatu (1922)") == "Nosferatu"
    assert clean_title("The General [1926]") == "The General"
    assert clean_description("<p>A &amp; B</p>\n\n  c") == "A & B c"
    assert len(clean_description("x" * 5000)) == 1200


def test_rights_rules():
    c = Candidate("id", "T", 1928, None, "f.mp4", 4000, 1, "")
    assert rights_for("date", c)[0] == LicenseType.public_domain
    c.licenseurl = "http://creativecommons.org/publicdomain/mark/1.0/"
    lt, notes = rights_for("asserted", c)
    assert lt == LicenseType.public_domain and "NOT independently verified" in notes
    c.licenseurl = "https://creativecommons.org/licenses/by-sa/4.0/"
    assert rights_for("asserted", c)[0] == LicenseType.creative_commons


async def test_direct_source_streams_as_mp4(user_client, session_factory):
    async with session_factory() as db:
        movie = Movie(
            external_id="ia:metropolis1927", slug="metropolis-1927", title="Metropolis", in_library=True,
            status=MovieStatus.published,
        )  # fmt: skip
        movie.licenses = [License(license_type=LicenseType.public_domain, territories=["US"])]
        movie.assets = [VideoAsset(id=uuid.uuid4(), status=AssetStatus.ready,
                                   playback_url="https://archive.org/download/metropolis1927/metropolis.mp4")]  # fmt: skip
        db.add(movie)
        await db.commit()

    free = (await user_client.get("/api/v1/movies/list/free")).json()
    assert [m["id"] for m in free["results"]] == ["metropolis-1927"]
    pb = (await user_client.post("/api/v1/playback/metropolis-1927/start")).json()
    assert pb["stream_type"] == "mp4"
    assert pb["master_url"] == "https://archive.org/download/metropolis1927/metropolis.mp4"


def test_asserted_licence_filter():
    from scripts.import_archive import ASSERTED_LICENCE

    ok = ["http://creativecommons.org/publicdomain/mark/1.0/", "https://creativecommons.org/publicdomain/zero/1.0/",
          "http://creativecommons.org/licenses/by/3.0/", "https://creativecommons.org/licenses/by-sa/4.0/"]  # fmt: skip
    bad = ["http://creativecommons.org/licenses/by-nc/3.0/", "http://creativecommons.org/licenses/by-nd/4.0/",
           "http://creativecommons.org/licenses/by-nc-sa/3.0/", ""]  # fmt: skip
    assert all(ASSERTED_LICENCE.search(u) for u in ok)
    assert not any(ASSERTED_LICENCE.search(u) for u in bad)
