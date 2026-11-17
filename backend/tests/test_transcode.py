from pathlib import Path

from app.workers import transcode as tx


def test_ladder_never_upscales():
    assert [r.name for r in tx.select_ladder(480)] == ["360p", "480p"]
    assert [r.name for r in tx.select_ladder(1080)] == ["360p", "480p", "720p", "1080p"]
    assert [r.name for r in tx.select_ladder(240)] == ["360p"]  # always at least one rung


def test_ffmpeg_command_maps_every_rung(tmp_path: Path):
    rungs = tx.select_ladder(720)
    cmd = tx.build_ffmpeg_command(Path("in.mp4"), tmp_path, rungs, has_audio=True)
    joined = " ".join(cmd)
    assert "split=3" in joined
    assert "v:0,a:0,name:360p v:1,a:1,name:480p v:2,a:2,name:720p" in joined
    assert cmd.count("0:a:0") == 3
    silent = " ".join(tx.build_ffmpeg_command(Path("in.mp4"), tmp_path, rungs, has_audio=False))
    assert "a:0" not in silent and "-c:a" not in silent


def test_master_playlist_uses_measured_bandwidth(tmp_path: Path):
    rung = tx.LADDER[0]
    d = tmp_path / rung.name
    d.mkdir()
    (d / "seg_00000.ts").write_bytes(b"x" * 600_000)  # 4.8 Mbit over 6s = 800 kbps
    (d / "seg_00001.ts").write_bytes(b"x" * 150_000)  # 1.2 Mbit over 3s = 400 kbps
    (d / "index.m3u8").write_text("#EXTM3U\n#EXTINF:6.0,\nseg_00000.ts\n#EXTINF:3.0,\nseg_00001.ts\n#EXT-X-ENDLIST\n")
    renditions = tx.write_master_playlist(tmp_path, [rung], tx.ProbeResult(60, 640, 480, True))
    assert renditions[0]["bandwidth"] == 800_000
    assert renditions[0]["average_bandwidth"] == 666_666
    master = (tmp_path / "master.m3u8").read_text()
    assert "RESOLUTION=480x360" in master and "360p/index.m3u8" in master


def test_import_host_allowlist():
    assert tx.host_allowed("archive.org")
    assert tx.host_allowed("ia800300.us.archive.org")
    assert not tx.host_allowed("archive.org.evil.com")
    assert not tx.host_allowed("169.254.169.254")
    assert not tx.host_allowed(None)
