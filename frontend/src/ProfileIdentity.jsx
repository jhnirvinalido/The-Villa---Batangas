import { useState } from 'react';

export function ProfilePhoto({name = 'Staff', src, size = 34}) {
  const [failedSrc, setFailedSrc] = useState('');
  const letters = name.trim().split(/\s+/).map(word => word[0]).slice(0,2).join('').toUpperCase() || 'ST';
  const showImage = src && src !== failedSrc;
  return <span className="team-profile-photo" style={{width:size,height:size,minWidth:size}}>{showImage ? <img src={src} alt="" onError={()=>setFailedSrc(src)}/> : letters}</span>;
}

