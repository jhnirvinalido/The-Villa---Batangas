import {useState} from 'react';
import './LandingReviews.css';

export function ReviewStars({rating}) {
  return <span className="landing-review-stars" role="img" aria-label={`${rating} out of 5 stars`}>{[1,2,3,4,5].map(value=><span key={value} aria-hidden="true" className={value<=Math.round(rating)?'filled':''}>★</span>)}</span>;
}

export function ReviewTicker({reviews,step=0}) {
  const entries=reviews.filter(review=>review.comment);
  if(!entries.length)return null;
  const active=((step%entries.length)+entries.length)%entries.length;
  return <div className="landing-review-ticker" role="region" aria-label="Guest review previews">
    <div className="landing-ticker-window">{entries.map((review,index)=><div key={review.id} aria-hidden={index!==active} className={`landing-ticker-comment ${index===active?'is-active':''}`}><span className="landing-ticker-quote">“{review.comment}”</span><span className="landing-ticker-author">{review.author}<ReviewStars rating={review.rating}/></span></div>)}</div>
  </div>;
}

function WrittenReview({review}) {
  const [expanded,setExpanded]=useState(false);
  const long=Boolean(review.comment && review.comment.length>240);
  return <article className="landing-written-review"><header><span className="landing-review-avatar" aria-hidden="true">{review.author?.charAt(0)?.toUpperCase() || 'G'}</span><div><h3>{review.author}</h3>{review.date && <small>{review.date}</small>}</div><ReviewStars rating={review.rating}/></header>{review.comment && <p id={`review-comment-${review.id}`} className={long && !expanded?'mobile-review-short':''}>{review.comment}</p>}{long && <button type="button" className="mobile-review-expand" aria-expanded={expanded} aria-controls={`review-comment-${review.id}`} onClick={()=>setExpanded(value=>!value)}>{expanded?'Read less':'Read more'}</button>}</article>;
}

export default function LandingReviews({reviews}) {
  if(!reviews.length)return null;
  return <div className="landing-review-pages">
    <div className="landing-written-reviews" role="region" aria-label="Scrollable guest reviews" tabIndex={0}>{reviews.map(review=><WrittenReview review={review} key={review.id}/>)}</div>
  </div>;
}
