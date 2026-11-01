import {useEffect, useRef, useState, useSyncExternalStore} from 'react';
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

function subscribeToReviewLayout(callback) {
  const queries = [window.matchMedia('(max-width: 767px)'), window.matchMedia('(max-width: 1099px)')];
  queries.forEach(query => query.addEventListener('change', callback));
  return () => queries.forEach(query => query.removeEventListener('change', callback));
}

function reviewPageSize() {
  if (window.matchMedia('(max-width: 767px)').matches) return 1;
  return window.matchMedia('(max-width: 1099px)').matches ? 2 : 3;
}

function WrittenReview({review, onRead}) {
  return <article className="landing-written-review">
    <header>
      <span className="landing-review-avatar" aria-hidden="true">{review.author?.charAt(0)?.toUpperCase() || 'G'}</span>
      <div><h3>{review.author || 'Guest'}</h3>{review.date && <small>{review.date}</small>}</div>
    </header>
    <ReviewStars rating={review.rating}/>
    <p className="review-comment-collapsed">{review.comment || 'This guest left a rating without a written review.'}</p>
    {review.comment && <button type="button" className="mobile-review-expand" onClick={() => onRead(review)} aria-haspopup="dialog">Read full review <span aria-hidden="true">↗</span></button>}
  </article>;
}

export default function LandingReviews({reviews}) {
  const [offset, setOffset] = useState(0);
  const [selectedReview, setSelectedReview] = useState(null);
  const dialog = useRef(null);
  const pageSize = useSyncExternalStore(subscribeToReviewLayout, reviewPageSize, () => 3);
  const pageCount = Math.ceil(reviews.length / pageSize);
  const currentPage = Math.min(Math.floor(offset / pageSize), Math.max(0, pageCount - 1));
  const firstReview = currentPage * pageSize;
  const visibleReviews = reviews.slice(firstReview, firstReview + pageSize);

  useEffect(() => {
    const element = dialog.current;
    if (!selectedReview || !element || !reviews.length) return undefined;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    element.showModal();
    return () => {
      element.close();
      document.body.style.overflow = previousOverflow;
    };
  }, [selectedReview, reviews.length]);

  if (!reviews.length) return null;
  return <div className="landing-review-pages">
    <nav className="landing-review-page-footer" aria-label="Guest review pages">
      <span aria-live="polite" aria-atomic="true">Showing {firstReview + 1}–{Math.min(firstReview + pageSize, reviews.length)} of {reviews.length} reviews</span>
      {pageCount > 1 && <div className="landing-review-pagination">
        <button type="button" onClick={() => setOffset((currentPage - 1) * pageSize)} disabled={currentPage === 0} aria-label="Previous reviews">← Previous</button>
        <span>Page {currentPage + 1} of {pageCount}</span>
        <button type="button" onClick={() => setOffset((currentPage + 1) * pageSize)} disabled={currentPage === pageCount - 1} aria-label="Next reviews">Next →</button>
      </div>}
    </nav>
    <div className="landing-written-reviews" role="region" aria-label="Guest reviews">{visibleReviews.map(review => <WrittenReview review={review} onRead={setSelectedReview} key={review.id}/>)}</div>
    <dialog ref={dialog} className="review-detail-dialog" aria-labelledby="review-detail-title" onCancel={() => setSelectedReview(null)} onClose={() => setSelectedReview(null)}>
      {selectedReview && <>
        <header><div><span className="section-label">Guest experience</span><h2 id="review-detail-title">{selectedReview.author || 'Guest'}</h2>{selectedReview.date && <small>{selectedReview.date}</small>}</div><button type="button" className="review-dialog-close" onClick={() => setSelectedReview(null)} aria-label="Close full review">×</button></header>
        <ReviewStars rating={selectedReview.rating}/>
        <p>{selectedReview.comment}</p>
      </>}
    </dialog>
  </div>;
}
