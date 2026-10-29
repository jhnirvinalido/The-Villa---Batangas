import {useEffect,useRef,useState} from 'react';

import LandingLoader from './LandingLoader';

export default function VillaVideoPreview({onOpen}) {
  const video=useRef(null);
  const [pending,setPending]=useState(true);
  useEffect(()=>{
    const player=video.current;
    function reset() {
      if(document.fullscreenElement===player)return;
      player.muted=true;player.controls=false;player.loop=true;
    }
    document.addEventListener('fullscreenchange',reset);
    player.addEventListener('webkitendfullscreen',reset);
    return()=>{document.removeEventListener('fullscreenchange',reset);player.removeEventListener('webkitendfullscreen',reset);};
  },[]);
  async function open() {
    const player=video.current;
    if(document.fullscreenElement===player || player.webkitDisplayingFullscreen)return;
    player.muted=false;player.controls=true;
    try {
      if(player.requestFullscreen)await player.requestFullscreen();
      else if(player.webkitEnterFullscreen)player.webkitEnterFullscreen();
      else throw new Error('Fullscreen unavailable');
      player.play().catch(()=>{});
    } catch {
      player.muted=true;player.controls=false;
      onOpen();
    }
  }
  return <button type="button" className="about-film-preview" onClick={open} aria-label="Play The Villa film in fullscreen with sound"><video onLoadStart={()=>setPending(true)} onWaiting={()=>setPending(true)} onCanPlay={()=>setPending(false)} onPlaying={()=>setPending(false)} onError={()=>setPending(false)} onStalled={()=>setPending(false)} ref={video} src="/ads.mp4" poster="/image3.jpg" autoPlay muted loop playsInline preload="metadata"/>{pending && <LandingLoader overlay label="Loading video" />}<span className="about-film-shade"/><span className="about-film-label">THE VILLA · A CLOSER LOOK</span><span className="about-film-prompt"><span className="about-film-play" aria-hidden="true">▶</span><span>Tap to play in fullscreen<small>Watch with sound</small></span></span></button>;
}
