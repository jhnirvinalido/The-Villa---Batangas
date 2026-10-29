import { useEffect, useState } from "react";
import "./VillaEntrance.css";

const SESSION_KEY = "theVillaHeroEntranceSeen:v14";
const INTRO_DURATION = 3600;

function initialPhase() {
  try {
    return window.matchMedia("(prefers-reduced-motion: no-preference)").matches
      && !window.sessionStorage.getItem(SESSION_KEY) ? "preparing" : "complete";
  } catch {
    return "complete";
  }
}

export default function VillaEntrance({ photoSrc }) {
  const [phase, setPhase] = useState(initialPhase);
  const [logoFailed, setLogoFailed] = useState(false);

  useEffect(() => {
    if (phase === "complete") return undefined;
    const finish = () => setPhase("complete");
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const handleKey = (event) => {
      if (event.key === "Escape" || event.key === "Tab") finish();
    };
    motion.addEventListener("change", finish);
    window.addEventListener("keydown", handleKey);
    if (motion.matches) finish();
    return () => {
      motion.removeEventListener("change", finish);
      window.removeEventListener("keydown", handleKey);
    };
  }, [phase]);

  useEffect(() => {
    if (phase !== "preparing") return undefined;
    let cancelled = false;
    try {
      window.sessionStorage.setItem(SESSION_KEY, "1");
    } catch {
      // Playback and dismissal never depend on storage writes succeeding.
    }
    // Decode before starting motion; a slow or broken photo skips the intro.
    const photo = new Image();
    const finish = () => { if (!cancelled) setPhase("complete"); };
    const timer = window.setTimeout(finish, 700);
    photo.onload = async () => {
      try {
        if (photo.decode) await photo.decode();
        if (!cancelled) {
          window.clearTimeout(timer);
          setPhase("playing");
        }
      } catch { finish(); }
    };
    photo.onerror = finish;
    photo.src = photoSrc;
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      photo.onload = null;
      photo.onerror = null;
    };
  }, [phase, photoSrc]);

  useEffect(() => {
    if (phase !== "playing") return undefined;
    // Independent fallback in case animationend never fires.
    const timer = window.setTimeout(() => setPhase("complete"), INTRO_DURATION + 100);
    return () => window.clearTimeout(timer);
  }, [phase]);

  if (phase === "complete") return null;

  return (
    <div className={`villa-intro is-${phase}`} role="presentation"
      onAnimationEnd={(event) => {
        if (event.target === event.currentTarget && event.animationName === "villa-intro-dissolve") setPhase("complete");
      }}>
      <div className="villa-intro-film" aria-hidden="true">
        <img className="villa-intro-photo" src={photoSrc} alt="" />
        <div className="villa-intro-shade" />
      </div>
      <div className="villa-intro-frame" aria-hidden="true" />
      <div className="villa-intro-arch" aria-hidden="true" />
      <div className="villa-intro-lockup" aria-hidden="true">
        <span className="villa-intro-kicker">A LITTLE CLOSER TO CALM</span>
        <div className="villa-intro-mark">
          {!logoFailed ? (
            <img src="/favicon.png" alt="" width="500" height="500" onError={() => setLogoFailed(true)} />
          ) : <span>The Villa</span>}
        </div>
        <span className="villa-intro-divider" />
        <span className="villa-intro-title">Your own little escape.</span>
        <span className="villa-intro-place">PRIVATE STAYCATION <span>·</span> BATANGAS</span>
      </div>
      <div className="villa-intro-progress" aria-hidden="true"><span /></div>
      <button type="button" className="villa-intro-skip" onClick={() => setPhase("complete")}
        aria-label="Skip the introduction">Skip intro <span aria-hidden="true">↗</span></button>
    </div>
  );
}
