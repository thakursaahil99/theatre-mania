"use client";

import { AnimatePresence, motion } from "framer-motion";
import type Hls from "hls.js";
import {
  ArrowLeft, Check, Gauge, LoaderCircle, Maximize, Minimize, Pause, PictureInPicture2, Play, RotateCcw, RotateCw,
  Settings2, SkipForward, Subtitles, Volume1, Volume2, VolumeX,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { api, beacon } from "@/lib/api";
import type { Playback } from "@/lib/types";
import { clock, cn } from "@/lib/utils";

const SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 2];
const HEARTBEAT_MS = 15_000;
const HIDE_CONTROLS_MS = 2800;
const PREFS_KEY = "cv.player";

type Menu = "quality" | "speed" | "subs" | null;
interface Level { index: number; height: number; bitrate: number }
interface Prefs { volume: number; muted: boolean; rate: number; subs: string | null }

function loadPrefs(): Prefs {
  try {
    return { volume: 1, muted: false, rate: 1, subs: null, ...JSON.parse(localStorage.getItem(PREFS_KEY) ?? "{}") };
  } catch {
    return { volume: 1, muted: false, rate: 1, subs: null };
  }
}
function savePrefs(p: Partial<Prefs>) {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify({ ...loadPrefs(), ...p }));
  } catch {
    /* private mode */
  }
}

export function VideoPlayer({ playback, onRenew, onBack }: {
  playback: Playback;
  onRenew: () => Promise<unknown>;
  onBack: () => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const hlsRef = useRef<Hls | null>(null);
  const lastTime = useRef(playback.resume_position_sec);
  const lastDuration = useRef<number | null>(playback.duration_seconds);
  const heartbeatRef = useRef<(useBeacon?: boolean) => void>(() => undefined);
  const seekTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const watched = useRef(0);
  const prevTick = useRef<number | null>(null);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const renewing = useRef(false);

  const [playing, setPlaying] = useState(false);
  const [waiting, setWaiting] = useState(true);
  const [time, setTime] = useState(playback.resume_position_sec);
  const [duration, setDuration] = useState(playback.duration_seconds ?? 0);
  const [buffered, setBuffered] = useState(0);
  const [volume, setVolume] = useState(1);
  const [muted, setMuted] = useState(false);
  const [rate, setRate] = useState(1);
  const [levels, setLevels] = useState<Level[]>([]);
  const [level, setLevel] = useState(-1);
  const [autoHeight, setAutoHeight] = useState<number | null>(null);
  const [subs, setSubs] = useState<string | null>(null);
  const [menu, setMenu] = useState<Menu>(null);
  const [controls, setControls] = useState(true);
  const [fullscreen, setFullscreen] = useState(false);
  const [osd, setOsd] = useState<{ id: number; node: ReactNode } | null>(null);
  const [flash, setFlash] = useState<{ id: number; play: boolean } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showRemaining, setShowRemaining] = useState(false);

  const showOsd = useCallback((node: ReactNode) => setOsd({ id: Date.now(), node }), []);
  useEffect(() => {
    if (!osd) return;
    const t = setTimeout(() => setOsd(null), 900);
    return () => clearTimeout(t);
  }, [osd]);

  // ------------------------------------------------------------------ source / hls.js
  useEffect(() => {
    const el = video.current;
    if (!el) return;
    const prefs = loadPrefs();
    el.volume = prefs.volume;
    el.muted = prefs.muted;
    el.playbackRate = prefs.rate;
    setVolume(prefs.volume);
    setMuted(prefs.muted);
    setRate(prefs.rate);
    setSubs((current) => current ?? prefs.subs ?? playback.subtitles.find((s) => s.is_default)?.id ?? null);
    setError(null);

    let destroyed = false;
    const startAt = lastTime.current > 0 ? lastTime.current : -1;

    (async () => {
      if (playback.stream_type === "mp4") {
        // Direct public-domain source (archive.org): plain progressive MP4, no hls.js.
        const onError = () => setError("This film couldn't be loaded from its source. Please try again later.");
        el.addEventListener("error", onError, { once: true });
        el.addEventListener("loadedmetadata", () => {
          if (startAt > 0) el.currentTime = startAt;
          el.play().catch(() => setPlaying(false));
        }, { once: true });
        el.src = playback.master_url;
        return;
      }
      const { default: HlsLib } = await import("hls.js"); // code-split: only loaded on /watch
      if (destroyed) return;
      if (HlsLib.isSupported()) {
        const hls = new HlsLib({ capLevelToPlayerSize: true, maxBufferLength: 30, enableWorker: true, startPosition: startAt });
        hlsRef.current = hls;
        hls.loadSource(playback.master_url);
        hls.attachMedia(el);
        hls.on(HlsLib.Events.MANIFEST_PARSED, (_e, data) => {
          setLevels(data.levels.map((l, index) => ({ index, height: l.height, bitrate: l.bitrate })).sort((a, b) => b.height - a.height));
          el.play().catch(() => setPlaying(false));
        });
        hls.on(HlsLib.Events.LEVEL_SWITCHED, (_e, d) => setAutoHeight(hls.levels[d.level]?.height ?? null));
        hls.on(HlsLib.Events.ERROR, (_e, d) => {
          if (!d.fatal) return;
          const code = (d.response as { code?: number } | undefined)?.code;
          if (d.type === HlsLib.ErrorTypes.NETWORK_ERROR && (code === 403 || code === 401) && !renewing.current) {
            // Token or signed segment URL expired: renew in place (same session, no new "view").
            renewing.current = true;
            void onRenew().finally(() => (renewing.current = false));
          } else if (d.type === HlsLib.ErrorTypes.NETWORK_ERROR) {
            hls.startLoad();
          } else if (d.type === HlsLib.ErrorTypes.MEDIA_ERROR) {
            hls.recoverMediaError();
          } else {
            setError("Playback failed. Please try again.");
          }
        });
      } else if (el.canPlayType("application/vnd.apple.mpegurl")) {
        el.src = playback.master_url; // Safari / iOS native HLS
        el.addEventListener("loadedmetadata", () => {
          if (startAt > 0) el.currentTime = startAt;
          el.play().catch(() => setPlaying(false));
        }, { once: true });
      } else {
        setError("Your browser can't play this stream.");
      }
    })();

    return () => {
      destroyed = true;
      hlsRef.current?.destroy();
      hlsRef.current = null;
      if (playback.stream_type === "mp4") {
        el.removeAttribute("src"); // stop the progressive download when leaving
        el.load();
      }
    };
  }, [playback.master_url, playback.stream_type, playback.subtitles, onRenew]);

  // ------------------------------------------------------------------ media events
  useEffect(() => {
    const el = video.current;
    if (!el) return;
    const onTime = () => {
      setTime(el.currentTime);
      lastTime.current = el.currentTime;
      const now = el.currentTime;
      if (prevTick.current !== null && !el.paused) {
        const delta = now - prevTick.current;
        if (delta > 0 && delta < 2) watched.current += delta / el.playbackRate; // ignore seeks
      }
      prevTick.current = now;
    };
    const onProgress = () => el.buffered.length && setBuffered(el.buffered.end(el.buffered.length - 1));
    const handlers: [keyof HTMLVideoElementEventMap, () => void][] = [
      ["timeupdate", onTime],
      ["progress", onProgress],
      ["durationchange", () => {
        if (!Number.isFinite(el.duration)) return;
        lastDuration.current = el.duration;
        setDuration(el.duration);
      }],
      // Persist a resume point right after a seek, not only on the 15s cadence.
      ["seeked", () => {
        if (seekTimer.current) clearTimeout(seekTimer.current);
        seekTimer.current = setTimeout(() => heartbeatRef.current(), 1200); // debounce scrubbing
      }],
      ["play", () => setPlaying(true)],
      ["pause", () => setPlaying(false)],
      ["waiting", () => setWaiting(true)],
      ["playing", () => setWaiting(false)],
      ["canplay", () => setWaiting(false)],
      ["seeking", () => (prevTick.current = null)],
      ["volumechange", () => { setVolume(el.volume); setMuted(el.muted); }],
      ["ratechange", () => setRate(el.playbackRate)],
      ["ended", () => setControls(true)],
    ];
    handlers.forEach(([ev, fn]) => el.addEventListener(ev, fn));
    return () => handlers.forEach(([ev, fn]) => el.removeEventListener(ev, fn));
  }, []);

  // ------------------------------------------------------------------ heartbeats
  // Reads refs, not the <video> element: on unmount React detaches refs *before* effect
  // cleanups run, so the final "flush" heartbeat would otherwise be silently dropped.
  const sendHeartbeat = useCallback((useBeacon = false) => {
    const el = video.current;
    const position = el ? el.currentTime : lastTime.current;
    if (!position && !watched.current) return; // nothing played yet
    const body = { position_sec: position, duration_sec: lastDuration.current,
      watched_delta_sec: Math.round(watched.current) };
    watched.current = 0;
    const path = `/playback/sessions/${playback.session_id}/heartbeat`;
    if (useBeacon) beacon(path, body);
    else void api(path, { method: "POST", json: body }).catch(() => undefined);
  }, [playback.session_id]);
  heartbeatRef.current = sendHeartbeat;

  /** Every seek goes through here so the resume point is known even before `timeupdate`. */
  const seekTo = useCallback((t: number) => {
    const el = video.current;
    if (!el) return;
    const target = Math.min(Math.max(0, t), Number.isFinite(el.duration) ? el.duration : Infinity);
    el.currentTime = target;
    lastTime.current = target;
    prevTick.current = null;
  }, []);

  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => sendHeartbeat(), HEARTBEAT_MS);
    return () => clearInterval(id);
  }, [playing, sendHeartbeat]);

  useEffect(() => {
    const flush = () => sendHeartbeat(true);
    const onVisibility = () => document.visibilityState === "hidden" && flush();
    window.addEventListener("pagehide", flush);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      flush();
      window.removeEventListener("pagehide", flush);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [sendHeartbeat]);

  // ------------------------------------------------------------------ subtitles
  useEffect(() => {
    const el = video.current;
    if (!el) return;
    const apply = () => {
      for (let i = 0; i < el.textTracks.length; i++) {
        const track = el.textTracks[i];
        track.mode = track.id === subs ? "showing" : "disabled";
      }
    };
    apply();
    el.textTracks.addEventListener?.("addtrack", apply);
    return () => el.textTracks.removeEventListener?.("addtrack", apply);
  }, [subs, playback.subtitles]);

  // ------------------------------------------------------------------ actions
  const togglePlay = useCallback(() => {
    const el = video.current;
    if (!el) return;
    if (el.paused) void el.play();
    else {
      el.pause();
      sendHeartbeat();
    }
    setFlash({ id: Date.now(), play: el.paused });
  }, [sendHeartbeat]);

  const seekBy = useCallback((delta: number) => {
    const el = video.current;
    if (!el) return;
    seekTo(el.currentTime + delta);
    showOsd(<span className="flex items-center gap-2">{delta < 0 ? <RotateCcw className="size-5" /> : <RotateCw className="size-5" />}
      {delta > 0 ? "+" : ""}{delta}s</span>);
  }, [showOsd]);

  const setVol = useCallback((v: number) => {
    const el = video.current;
    if (!el) return;
    el.volume = Math.min(1, Math.max(0, v));
    el.muted = el.volume === 0;
    savePrefs({ volume: el.volume, muted: el.muted });
  }, []);

  const toggleMute = useCallback(() => {
    const el = video.current;
    if (!el) return;
    el.muted = !el.muted;
    if (!el.muted && el.volume === 0) el.volume = 0.5;
    savePrefs({ muted: el.muted, volume: el.volume });
    showOsd(el.muted ? "Muted" : `Volume ${Math.round(el.volume * 100)}%`);
  }, [showOsd]);

  const setSpeed = useCallback((r: number) => {
    if (!video.current) return;
    video.current.playbackRate = r;
    savePrefs({ rate: r });
    showOsd(`${r}× speed`);
  }, [showOsd]);

  const chooseLevel = (index: number) => {
    setLevel(index);
    if (hlsRef.current) hlsRef.current.currentLevel = index; // -1 = auto (ABR)
    setMenu(null);
  };

  const chooseSubs = (id: string | null) => {
    setSubs(id);
    savePrefs({ subs: id });
    setMenu(null);
  };

  const toggleFullscreen = useCallback(async () => {
    const el = container.current as (HTMLDivElement & { webkitRequestFullscreen?: () => void }) | null;
    const v = video.current as (HTMLVideoElement & { webkitEnterFullscreen?: () => void }) | null;
    if (document.fullscreenElement) return void (await document.exitFullscreen());
    if (el?.requestFullscreen) await el.requestFullscreen().catch(() => undefined);
    else if (v?.webkitEnterFullscreen) v.webkitEnterFullscreen(); // iOS
  }, []);

  const togglePip = useCallback(async () => {
    const v = video.current;
    if (!v || !document.pictureInPictureEnabled) return;
    if (document.pictureInPictureElement) await document.exitPictureInPicture();
    else await v.requestPictureInPicture().catch(() => undefined);
  }, []);

  const inIntro =
    playback.intro_end_sec !== null && time >= (playback.intro_start_sec ?? 0) && time < playback.intro_end_sec - 1;
  const skipIntro = useCallback(() => {
    if (playback.intro_end_sec !== null) seekTo(playback.intro_end_sec);
  }, [playback.intro_end_sec]);

  useEffect(() => {
    const onFs = () => setFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", onFs);
    return () => document.removeEventListener("fullscreenchange", onFs);
  }, []);

  // ------------------------------------------------------------------ keyboard shortcuts
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target.closest("input, textarea, select, [contenteditable]") || e.metaKey || e.ctrlKey || e.altKey) return;
      const el = video.current;
      if (!el) return;
      switch (e.key) {
        case " ": case "k": case "K": togglePlay(); break;
        case "ArrowLeft": case "j": case "J": seekBy(-10); break;
        case "ArrowRight": case "l": case "L": seekBy(10); break;
        case "ArrowUp": setVol(el.volume + 0.05); showOsd(`Volume ${Math.round(Math.min(1, el.volume + 0.05) * 100)}%`); break;
        case "ArrowDown": setVol(el.volume - 0.05); showOsd(`Volume ${Math.round(Math.max(0, el.volume - 0.05) * 100)}%`); break;
        case "m": case "M": toggleMute(); break;
        case "f": case "F": void toggleFullscreen(); break;
        case "p": case "P": void togglePip(); break;
        case "s": case "S": if (inIntro) skipIntro(); break;
        case "c": case "C": {
          const next = subs ? null : playback.subtitles[0]?.id ?? null;
          chooseSubs(next);
          showOsd(next ? "Subtitles on" : "Subtitles off");
          break;
        }
        case ">": setSpeed(SPEEDS[Math.min(SPEEDS.indexOf(el.playbackRate) + 1, SPEEDS.length - 1)] ?? 1); break;
        case "<": setSpeed(SPEEDS[Math.max(SPEEDS.indexOf(el.playbackRate) - 1, 0)] ?? 1); break;
        case "Home": seekTo(0); break;
        case "End": seekTo(el.duration - 1); break;
        case "Escape": if (menu) setMenu(null); else return; break;
        default:
          if (/^[0-9]$/.test(e.key) && el.duration) {
            seekTo((Number(e.key) / 10) * el.duration);
            break;
          }
          return;
      }
      e.preventDefault();
      poke();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  // ------------------------------------------------------------------ controls visibility
  const poke = useCallback(() => {
    setControls(true);
    if (hideTimer.current) clearTimeout(hideTimer.current);
    hideTimer.current = setTimeout(() => {
      if (video.current && !video.current.paused) {
        setControls(false);
        setMenu(null);
      }
    }, HIDE_CONTROLS_MS);
  }, []);
  useEffect(() => {
    if (!playing) setControls(true);
    else poke();
  }, [playing, poke]);

  // Double-tap left/right thirds to seek on touch devices; single tap toggles controls.
  const lastTap = useRef(0);
  const onSurfaceClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if ((e.nativeEvent as PointerEvent).pointerType === "touch") {
      const now = Date.now();
      const rect = e.currentTarget.getBoundingClientRect();
      const x = (e.clientX - rect.left) / rect.width;
      if (now - lastTap.current < 300 && (x < 0.35 || x > 0.65)) seekBy(x < 0.35 ? -10 : 10);
      else if (controls) setControls(false);
      else poke();
      lastTap.current = now;
      return;
    }
    togglePlay();
  };

  const autoLabel = autoHeight ? `Auto (${autoHeight}p)` : "Auto";
  const remaining = Math.max(0, duration - time);

  return (
    <div
      ref={container}
      className={cn("fixed inset-0 z-50 select-none bg-black text-white", !controls && playing && "cursor-none")}
      onPointerMove={(e) => e.pointerType === "mouse" && poke()}
      data-testid="player"
    >
      <video ref={video} className="absolute inset-0 size-full object-contain" playsInline
        crossOrigin={playback.stream_type === "mp4" ? undefined : "anonymous"}
        preload="auto" aria-label={playback.movie.title}>
        {playback.subtitles.map((s) => (
          <track key={s.id} id={s.id} kind="subtitles" src={s.url} srcLang={s.language} label={s.label} default={s.id === subs} />
        ))}
      </video>

      {/* Click / tap surface */}
      <div className="absolute inset-0" onClick={onSurfaceClick} onDoubleClick={(e) => {
        if ((e.nativeEvent as PointerEvent).pointerType !== "touch") void toggleFullscreen();
      }} />

      {/* Buffering */}
      {waiting && !error && (
        <div className="pointer-events-none absolute inset-0 grid place-items-center">
          <LoaderCircle className="size-14 animate-spin text-white/80" />
        </div>
      )}

      {/* Play/pause flash */}
      <AnimatePresence>
        {flash && (
          <motion.div key={flash.id} className="pointer-events-none absolute inset-0 grid place-items-center"
            initial={{ opacity: 0.9, scale: 0.6 }} animate={{ opacity: 0, scale: 1.4 }} transition={{ duration: 0.6 }}
            onAnimationComplete={() => setFlash(null)}>
            <span className="grid size-20 place-items-center rounded-full bg-black/50">
              {flash.play ? <Play className="size-9 fill-current" /> : <Pause className="size-9 fill-current" />}
            </span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* On-screen display */}
      <AnimatePresence>
        {osd && (
          <motion.div key={osd.id} role="status" className="pointer-events-none absolute left-1/2 top-[18%] -translate-x-1/2 rounded-full bg-black/70 px-5 py-2.5 text-sm font-medium backdrop-blur"
            initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            {osd.node}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Skip intro */}
      <AnimatePresence>
        {inIntro && (
          <motion.button onClick={skipIntro} className="btn-primary absolute bottom-28 right-6 z-20 md:right-12"
            initial={{ opacity: 0, x: 40 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 40 }}>
            <SkipForward className="size-4" /> Skip Intro
          </motion.button>
        )}
      </AnimatePresence>

      {error && (
        <div className="absolute inset-0 z-30 grid place-items-center bg-black/80 p-6 text-center">
          <div>
            <p className="text-lg">{error}</p>
            <button className="btn-primary mt-6" onClick={() => void onRenew()}>Retry</button>
          </div>
        </div>
      )}

      {/* Chrome */}
      <motion.div className="pointer-events-none absolute inset-0 z-10" animate={{ opacity: controls ? 1 : 0 }}
        transition={{ duration: 0.3 }}>
        <div className="absolute inset-x-0 top-0 h-40 bg-linear-to-b from-black/80 to-transparent" />
        <div className="absolute inset-x-0 bottom-0 h-56 bg-linear-to-t from-black/90 to-transparent" />

        <div className={cn("absolute inset-x-0 top-0 flex items-center gap-4 p-4 md:p-6", controls && "pointer-events-auto")}>
          <button onClick={onBack} aria-label="Back" className="grid size-11 place-items-center rounded-full transition hover:bg-white/10">
            <ArrowLeft className="size-6" />
          </button>
          <div className="min-w-0">
            <p className="text-xs uppercase tracking-[0.25em] text-white/50">Now playing</p>
            <h1 className="truncate font-display text-2xl tracking-wide md:text-3xl">{playback.movie.title}</h1>
          </div>
        </div>

        <div className={cn("absolute inset-x-0 bottom-0 space-y-2 px-4 pb-4 md:px-8 md:pb-6", controls && "pointer-events-auto")}>
          <Scrubber time={time} duration={duration} buffered={buffered}
            intro={playback.intro_end_sec !== null ? [playback.intro_start_sec ?? 0, playback.intro_end_sec] : null}
            onSeek={seekTo} onActivity={poke} />

          <div className="flex items-center gap-1 md:gap-2">
            <IconButton label={playing ? "Pause (k)" : "Play (k)"} onClick={togglePlay}>
              {playing ? <Pause className="size-6 fill-current" /> : <Play className="size-6 fill-current" />}
            </IconButton>
            <IconButton label="Back 10 seconds (j)" onClick={() => seekBy(-10)}><RotateCcw className="size-5" /></IconButton>
            <IconButton label="Forward 10 seconds (l)" onClick={() => seekBy(10)}><RotateCw className="size-5" /></IconButton>

            <div className="group/vol flex items-center">
              <IconButton label="Mute (m)" onClick={toggleMute}>
                {muted || volume === 0 ? <VolumeX className="size-5" /> : volume < 0.5 ? <Volume1 className="size-5" /> : <Volume2 className="size-5" />}
              </IconButton>
              <input type="range" min={0} max={1} step={0.01} value={muted ? 0 : volume} aria-label="Volume"
                onChange={(e) => setVol(Number(e.target.value))}
                className="hidden h-1 w-0 cursor-pointer accent-white transition-all duration-300 group-hover/vol:w-24 md:block" />
            </div>

            <button onClick={() => setShowRemaining((r) => !r)} className="ml-2 font-mono text-xs tabular-nums text-white/80 md:text-sm">
              {showRemaining ? `-${clock(remaining)}` : clock(time)} <span className="text-white/40">/ {clock(duration)}</span>
            </button>

            <div className="ml-auto flex items-center gap-1 md:gap-2">
              {playback.subtitles.length > 0 && (
                <MenuButton label="Subtitles (c)" icon={<Subtitles className={cn("size-5", subs && "text-accent")} />}
                  open={menu === "subs"} onToggle={() => setMenu(menu === "subs" ? null : "subs")}>
                  <MenuItem active={subs === null} onClick={() => chooseSubs(null)}>Off</MenuItem>
                  {playback.subtitles.map((s) => (
                    <MenuItem key={s.id} active={subs === s.id} onClick={() => chooseSubs(s.id)}>{s.label}</MenuItem>
                  ))}
                </MenuButton>
              )}
              <MenuButton label="Playback speed" icon={<Gauge className="size-5" />} open={menu === "speed"}
                onToggle={() => setMenu(menu === "speed" ? null : "speed")}>
                {SPEEDS.map((s) => (
                  <MenuItem key={s} active={rate === s} onClick={() => { setSpeed(s); setMenu(null); }}>
                    {s === 1 ? "Normal" : `${s}×`}
                  </MenuItem>
                ))}
              </MenuButton>
              {levels.length > 0 && (
                <MenuButton label="Quality" icon={<Settings2 className="size-5" />} open={menu === "quality"}
                  onToggle={() => setMenu(menu === "quality" ? null : "quality")}>
                  <MenuItem active={level === -1} onClick={() => chooseLevel(-1)}>{autoLabel}</MenuItem>
                  {levels.map((l) => (
                    <MenuItem key={l.index} active={level === l.index} onClick={() => chooseLevel(l.index)}>
                      {l.height}p {l.height >= 720 && <span className="ml-1 rounded bg-white/15 px-1 text-[10px]">HD</span>}
                    </MenuItem>
                  ))}
                </MenuButton>
              )}
              <IconButton label="Picture in picture (p)" onClick={() => void togglePip()} className="hidden sm:grid">
                <PictureInPicture2 className="size-5" />
              </IconButton>
              <IconButton label="Fullscreen (f)" onClick={() => void toggleFullscreen()}>
                {fullscreen ? <Minimize className="size-5" /> : <Maximize className="size-5" />}
              </IconButton>
            </div>
          </div>
        </div>
      </motion.div>
    </div>
  );
}

// ---------------------------------------------------------------------- pieces

function IconButton({ label, onClick, children, className }: { label: string; onClick: () => void; children: ReactNode; className?: string }) {
  return (
    <button onClick={onClick} aria-label={label} title={label}
      className={cn("grid size-10 place-items-center rounded-full transition hover:bg-white/10 active:scale-90 md:size-11", className)}>
      {children}
    </button>
  );
}

function MenuButton({ label, icon, open, onToggle, children }: {
  label: string; icon: ReactNode; open: boolean; onToggle: () => void; children: ReactNode;
}) {
  return (
    <div className="relative">
      <IconButton label={label} onClick={onToggle}>{icon}</IconButton>
      <AnimatePresence>
        {open && (
          <motion.div role="menu" aria-label={label}
            className="absolute bottom-full right-0 mb-3 min-w-44 overflow-hidden rounded-2xl glass p-1.5 shadow-2xl"
            initial={{ opacity: 0, y: 8, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 6 }}
            transition={{ duration: 0.16 }}>
            <p className="px-3 pb-1 pt-2 text-[10px] uppercase tracking-[0.2em] text-white/40">{label.replace(/ \(.\)$/, "")}</p>
            {children}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function MenuItem({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button role="menuitemradio" aria-checked={active} onClick={onClick}
      className={cn("flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm transition hover:bg-white/10",
        active ? "text-white" : "text-white/65")}>
      <Check className={cn("size-4", active ? "opacity-100" : "opacity-0")} />
      {children}
    </button>
  );
}

function Scrubber({ time, duration, buffered, intro, onSeek, onActivity }: {
  time: number; duration: number; buffered: number; intro: [number, number] | null;
  onSeek: (t: number) => void; onActivity: () => void;
}) {
  const bar = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<number | null>(null);
  const [drag, setDrag] = useState<number | null>(null);
  const pct = (t: number) => (duration ? `${Math.min(100, (t / duration) * 100)}%` : "0%");

  const ratioAt = (clientX: number) => {
    const r = bar.current!.getBoundingClientRect();
    return Math.min(1, Math.max(0, (clientX - r.left) / r.width));
  };

  const shown = drag ?? time;
  return (
    <div
      ref={bar}
      role="slider"
      tabIndex={0}
      aria-label="Seek"
      aria-valuemin={0}
      aria-valuemax={Math.round(duration)}
      aria-valuenow={Math.round(shown)}
      aria-valuetext={`${clock(shown)} of ${clock(duration)}`}
      className="group/scrub relative flex h-5 cursor-pointer touch-none items-center"
      onPointerDown={(e) => {
        e.currentTarget.setPointerCapture(e.pointerId);
        setDrag(ratioAt(e.clientX) * duration);
      }}
      onPointerMove={(e) => {
        const t = ratioAt(e.clientX) * duration;
        setHover(t);
        if (drag !== null) setDrag(t);
        onActivity();
      }}
      onPointerUp={(e) => {
        if (drag !== null) onSeek(ratioAt(e.clientX) * duration);
        setDrag(null);
      }}
      onPointerLeave={() => setHover(null)}
    >
      <div className="relative h-1 w-full overflow-hidden rounded-full bg-white/20 transition-[height] duration-200 group-hover/scrub:h-1.5">
        <div className="absolute inset-y-0 left-0 bg-white/30" style={{ width: pct(buffered) }} />
        {intro && (
          <div className="absolute inset-y-0 bg-gold/40" style={{ left: pct(intro[0]), width: pct(intro[1] - intro[0]) }} />
        )}
        <div className="absolute inset-y-0 left-0 brand-gradient" style={{ width: pct(shown) }} />
      </div>
      <div className="absolute size-3.5 -translate-x-1/2 scale-0 rounded-full bg-white shadow-lg transition-transform group-hover/scrub:scale-100"
        style={{ left: pct(shown) }} />
      {hover !== null && (
        <div className="pointer-events-none absolute bottom-6 -translate-x-1/2 rounded-md bg-black/80 px-2 py-1 font-mono text-xs"
          style={{ left: pct(hover) }}>
          {clock(hover)}
        </div>
      )}
    </div>
  );
}
