"""FFmpeg → HLS adaptive-bitrate pipeline.

Produces one H.264/AAC MPEG-TS rendition per ladder rung (never upscaling), with
keyframes forced on segment boundaries so every rendition switches cleanly. The master
playlist is written by us (not ffmpeg) using measured peak/average bitrates, which keeps
BANDWIDTH accurate for ABR decisions.
"""

import json
import logging
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx

from app.core.config import settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Rung:
    name: str
    height: int
    video_bitrate: str
    maxrate: str
    bufsize: str
    audio_bitrate: str


LADDER: tuple[Rung, ...] = (
    Rung("360p", 360, "800k", "856k", "1200k", "96k"),
    Rung("480p", 480, "1400k", "1498k", "2100k", "128k"),
    Rung("720p", 720, "2800k", "2996k", "4200k", "128k"),
    Rung("1080p", 1080, "5000k", "5350k", "7500k", "192k"),
)


@dataclass
class ProbeResult:
    duration: float
    width: int
    height: int
    has_audio: bool


class TranscodeError(Exception):
    pass


# ----------------------------------------------------------------------------- probing


def probe(src: Path) -> ProbeResult:
    proc = subprocess.run(
        [settings.FFPROBE_BIN, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(src)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise TranscodeError(f"ffprobe failed: {proc.stderr[-2000:]}")
    info = json.loads(proc.stdout)
    video = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    if video is None:
        raise TranscodeError("No video stream found")
    duration = float(info.get("format", {}).get("duration") or video.get("duration") or 0)
    if duration <= 0:
        raise TranscodeError("Could not determine duration")
    return ProbeResult(
        duration=duration,
        width=int(video["width"]),
        height=int(video["height"]),
        has_audio=any(s.get("codec_type") == "audio" for s in info.get("streams", [])),
    )


def select_ladder(source_height: int) -> list[Rung]:
    rungs = [r for r in LADDER if r.height <= source_height * 1.05]
    return rungs or [LADDER[0]]


# ----------------------------------------------------------------------------- ffmpeg


def build_ffmpeg_command(src: Path, out_dir: Path, rungs: list[Rung], has_audio: bool) -> list[str]:
    seg = settings.HLS_SEGMENT_SECONDS
    n = len(rungs)
    filters = [f"[0:v]split={n}" + "".join(f"[s{i}]" for i in range(n))]
    filters += [f"[s{i}]scale=-2:{r.height}:flags=lanczos,format=yuv420p[v{i}]" for i, r in enumerate(rungs)]

    cmd = [settings.FFMPEG_BIN, "-hide_banner", "-nostdin", "-y", "-i", str(src), "-filter_complex", ";".join(filters)]
    for i, r in enumerate(rungs):
        cmd += ["-map", f"[v{i}]", f"-b:v:{i}", r.video_bitrate, f"-maxrate:v:{i}", r.maxrate, f"-bufsize:v:{i}", r.bufsize]
    if has_audio:
        for i, r in enumerate(rungs):
            cmd += ["-map", "0:a:0", f"-b:a:{i}", r.audio_bitrate]
        cmd += ["-c:a", "aac", "-ar", "48000", "-ac", "2"]

    stream_map = " ".join(
        f"v:{i},a:{i},name:{r.name}" if has_audio else f"v:{i},name:{r.name}" for i, r in enumerate(rungs)
    )
    cmd += [
        "-c:v", "libx264",
        "-preset", settings.X264_PRESET,
        "-profile:v", "main",
        "-sc_threshold", "0",
        "-force_key_frames", f"expr:gte(t,n_forced*{seg})",
        "-f", "hls",
        "-hls_time", str(seg),
        "-hls_playlist_type", "vod",
        "-hls_flags", "independent_segments",
        "-hls_segment_type", "mpegts",
        "-hls_segment_filename", str(out_dir / "%v" / "seg_%05d.ts"),
        "-var_stream_map", stream_map,
        "-progress", "pipe:1",
        "-nostats",
        str(out_dir / "%v" / "index.m3u8"),
    ]  # fmt: skip
    return cmd


def run_ffmpeg(cmd: list[str], duration: float, on_progress: Callable[[int], None], log_path: Path) -> None:
    log.info("ffmpeg: %s", " ".join(cmd))
    last_pct = -1
    with log_path.open("w") as stderr_file:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=stderr_file, text=True)
        assert proc.stdout is not None
        for line in proc.stdout:
            key, _, value = line.strip().partition("=")
            # out_time_ms is (confusingly) also microseconds in ffmpeg.
            if key in {"out_time_us", "out_time_ms"} and value.isdigit():
                pct = min(99, int(int(value) / 1_000_000 / duration * 100))
                if pct >= last_pct + 2:
                    last_pct = pct
                    on_progress(pct)
        code = proc.wait()
    if code != 0:
        tail = log_path.read_text(errors="replace")[-3000:]
        raise TranscodeError(f"ffmpeg exited with {code}: {tail}")


def extract_thumbnail(src: Path, dest: Path, at_seconds: float) -> bool:
    proc = subprocess.run(
        [settings.FFMPEG_BIN, "-hide_banner", "-nostdin", "-y", "-ss", f"{at_seconds:.2f}", "-i", str(src),
         "-frames:v", "1", "-vf", "scale=1280:-2", "-q:v", "3", str(dest)],
        capture_output=True,
        timeout=120,
    )  # fmt: skip
    return proc.returncode == 0 and dest.exists()


# ----------------------------------------------------------------------------- playlists


def measure_variant(variant_dir: Path) -> tuple[int, int]:
    """(peak_bps, average_bps) from segment sizes and EXTINF durations."""
    playlist = (variant_dir / "index.m3u8").read_text().splitlines()
    peak, total_bits, total_dur, pending = 0, 0, 0.0, None
    for line in playlist:
        if line.startswith("#EXTINF:"):
            pending = float(line[8:].split(",")[0])
        elif line and not line.startswith("#") and pending:
            bits = (variant_dir / line.strip()).stat().st_size * 8
            peak = max(peak, int(bits / pending))
            total_bits += bits
            total_dur += pending
            pending = None
    if total_dur == 0:
        raise TranscodeError(f"Empty rendition in {variant_dir.name}")
    return peak, int(total_bits / total_dur)


def write_master_playlist(out_dir: Path, rungs: list[Rung], src: ProbeResult) -> list[dict]:
    lines = ["#EXTM3U", "#EXT-X-VERSION:3", "#EXT-X-INDEPENDENT-SEGMENTS"]
    renditions = []
    for r in rungs:
        peak, avg = measure_variant(out_dir / r.name)
        width = int(round(src.width * r.height / src.height / 2) * 2)
        lines.append(f"#EXT-X-STREAM-INF:BANDWIDTH={peak},AVERAGE-BANDWIDTH={avg},RESOLUTION={width}x{r.height},NAME=\"{r.name}\"")
        lines.append(f"{r.name}/index.m3u8")
        renditions.append({"name": r.name, "height": r.height, "width": width, "bandwidth": peak, "average_bandwidth": avg,
                           "playlist": f"{r.name}/index.m3u8"})  # fmt: skip
    (out_dir / "master.m3u8").write_text("\n".join(lines) + "\n")
    return renditions


# ----------------------------------------------------------------------------- remote import


def host_allowed(host: str | None) -> bool:
    if not host:
        return False
    host = host.lower().rstrip(".")
    for allowed in settings.import_allowed_hosts:
        if allowed.startswith("."):
            if host.endswith(allowed):
                return True
        elif host == allowed:
            return True
    return False


def download(url: str, dest: Path, on_progress: Callable[[int], None]) -> None:
    """Stream a remote file to disk, following redirects only to allow-listed hosts (SSRF guard)."""
    timeout = httpx.Timeout(30.0, read=180.0)
    headers = {"User-Agent": "TheatreManiaImporter/1.0"}
    with httpx.Client(timeout=timeout, follow_redirects=False, headers=headers) as client:
        for _ in range(8):
            parts = urlsplit(url)
            if parts.scheme not in {"http", "https"} or not host_allowed(parts.hostname):
                raise TranscodeError(f"Import host not allowed: {parts.hostname}")
            with client.stream("GET", url) as resp:
                if resp.is_redirect:
                    url = urljoin(url, resp.headers["location"])
                    continue
                if resp.status_code != 200:
                    raise TranscodeError(f"Download failed: HTTP {resp.status_code}")
                total = int(resp.headers.get("content-length") or 0)
                done, last = 0, -1
                with dest.open("wb") as fh:
                    for chunk in resp.iter_bytes(1024 * 1024):
                        fh.write(chunk)
                        done += len(chunk)
                        if total:
                            pct = int(done / total * 100)
                            if pct >= last + 5:
                                last = pct
                                on_progress(pct)
                return
        raise TranscodeError("Too many redirects")
