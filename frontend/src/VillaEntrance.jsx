import { useEffect, useState } from "react";
import "./VillaEntrance.css";

const SESSION_KEY = "theVillaHeroEntranceSeen:v15";
const INTRO_DURATION = 3600;
const STATIC_INTRO_DURATION = 2400;

function initialPhase() {
  const phase = window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ? "static"
    : "playing";
  try {
    return window.sessionStorage.getItem(SESSION_KEY) ? "complete" : phase;
  } catch {
    return phase;
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
    const handleMotionChange = () => {
      if (motion.matches) {
        setPhase((current) => current === "playing" ? "static" : current);
      }
    };
    motion.addEventListener("change", handleMotionChange);
    window.addEventListener("keydown", handleKey);
    return () => {
      motion.removeEventListener("change", handleMotionChange);
      window.removeEventListener("keydown", handleKey);
    };
  }, [phase]);

  useEffect(() => {
    if (phase === "complete") return undefined;
    try {
      window.sessionStorage.setItem(SESSION_KEY, "1");
    } catch {
      // Playback and dismissal never depend on storage being available.
    }
    const timer = window.setTimeout(
      () => setPhase("complete"),
      phase === "static" ? STATIC_INTRO_DURATION : INTRO_DURATION + 100
    );
    return () => window.clearTimeout(timer);
  }, [phase]);

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
        <img className="villa-intro-photo" src={photoSrc} alt="" fetchPriority="high" />
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
