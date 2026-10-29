import {useCallback,useEffect,useRef,useState} from 'react';
import './MobileCarousel.css';

export default function MobileCarousel({children,className='',label,count}) {
  const track=useRef(null);
  const [index,setIndex]=useState(0);
  const updatePosition=useCallback(()=>{
    const element=track.current;
    if(!element?.children.length)return;
    const items=[...element.children];
    const origin=items[0].offsetLeft;
    const nearest=items.reduce((best,item,i)=>Math.abs(item.offsetLeft-origin-element.scrollLeft)<Math.abs(items[best].offsetLeft-origin-element.scrollLeft)?i:best,0);
    setIndex(nearest);
    items.forEach((item, i) => {
      const distance = Math.min(Math.abs(item.offsetLeft-origin-element.scrollLeft) / Math.max(element.clientWidth, 1), 1);
      item.style.setProperty('--swipe-scale', String(1 - distance * 0.035));
      item.style.setProperty('--swipe-opacity', String(1 - distance * 0.3));
      item.classList.toggle('is-current-slide', i === nearest);
    });
    element.style.setProperty('--carousel-height',`${Math.ceil(items[nearest].getBoundingClientRect().height)}px`);
  },[]);
  useEffect(()=>{
    const element=track.current;
    if(!element)return;
    updatePosition();
    const observer=new ResizeObserver(updatePosition);
    observer.observe(element);
    for(const item of element.children)observer.observe(item);
    return()=>observer.disconnect();
  },[count,updatePosition]);
  function move(direction) {
    const element=track.current;
    const next=Math.min(Math.max(index+direction,0),count-1);
    const item=element?.children[next];
    if(!item)return;
    element.scrollTo({left:item.offsetLeft-element.children[0].offsetLeft,behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});
  }
  return <div className="mobile-carousel-shell">
    <div ref={track} className={`${className} mobile-swipe-track`} role="region" aria-label={`Browse ${label}`} tabIndex={0} onScroll={updatePosition}>{children}</div>
    {count>1 && <div className="mobile-carousel-navigation"><button type="button" aria-label={`Previous ${label}`} disabled={index===0} onClick={()=>move(-1)}>‹</button><span aria-live="polite">{Math.min(index+1,count)} / {count}</span><button type="button" aria-label={`Next ${label}`} disabled={index>=count-1} onClick={()=>move(1)}>›</button></div>}
  </div>;
}
