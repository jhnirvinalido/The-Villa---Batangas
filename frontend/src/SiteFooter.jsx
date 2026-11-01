import { Link } from "react-router-dom";
import "./PublicPages.css";

export default function SiteFooter() {
  return <footer className="public-footer">
    <div className="container content-container public-footer-grid">
      <div className="public-footer-intro">
        <Link className="public-footer-brand" to="/"><img src="/favicon.png" alt="" width="48" height="48"/><span>The Villa</span></Link>
        <p>Room to unwind. Space to reconnect.<br/>Your own little escape awaits.</p>
        <Link className="public-footer-book" to="/book">Book your stay <span aria-hidden="true">↗</span></Link>
      </div>
      <nav aria-label="Footer explore"><h2>Explore</h2><Link to="/">Home</Link><Link to="/villas">Our villas</Link><Link to="/about">About The Villa</Link><Link to="/reviews">Guest reviews</Link></nav>
      <nav aria-label="Footer plan your stay"><h2>Plan your stay</h2><Link to="/book">Check availability</Link><Link to="/faqs">FAQs</Link><Link to="/policies">Booking policies</Link><Link to="/location">Location & directions</Link></nav>
      <div className="public-footer-location"><h2>Find us</h2><address>The Villa<br/>San Jose, Batangas<br/>Philippines</address><a href="https://www.google.com/maps/dir/?api=1&destination=13.9210228%2C121.1062011&travelmode=driving" target="_blank" rel="noreferrer">Open Google Maps ↗</a></div>
    </div>
    <div className="container content-container public-footer-bottom"><span>© {new Date().getFullYear()} The Villa. All rights reserved.</span><Link to="/policies">Reservation terms</Link></div>
  </footer>;
}
