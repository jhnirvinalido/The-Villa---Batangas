import { useState } from "react";
import "./LandingLoader.css";

export default function LandingLoader({ label = "Loading", compact = false, overlay = false }) {
  return <span className={`${overlay ? "landing-loader-overlay" : "landing-loader"}${compact ? " compact" : ""}`} role="status" aria-label={label}><span className="landing-spinner animate-spin" aria-hidden="true" /></span>;
}

export function LoadingImage({ active = true, ...props }) {
  const [pending, setPending] = useState(true);
  return <><img {...props} ref={node => { if (node?.complete) setPending(false); }} onLoad={() => setPending(false)} onError={() => setPending(false)} />{pending && active && <LandingLoader overlay label="Loading photo" />}</>;
}

export function LoadingVideo(props) {
  const [pending, setPending] = useState(true);
  return <><video {...props} onLoadStart={() => setPending(true)} onWaiting={() => setPending(true)} onCanPlay={() => setPending(false)} onPlaying={() => setPending(false)} onError={() => setPending(false)} onStalled={() => setPending(false)} />{pending && <LandingLoader overlay label="Loading video" />}</>;
}
