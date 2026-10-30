import { AlertMessage, LoadingScreen } from "./SystemFeedback";
import { feedbackFetch as fetch } from "./requestFeedback.mjs";
import { getApiErrorMessage, getUserFacingError } from "./errorMessages.mjs";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FaCheck, FaChevronLeft, FaHome, FaSpinner, FaStar } from "react-icons/fa";
import "./GuestFeedback.css";

const API_URL = (
  (typeof window !== "undefined" && window.__THE_VILLA_API_BASE__) ||
  import.meta.env.VITE_API_URL ||
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

function readApiError(response) {
  return response
    .json()
    .then((payload) => getApiErrorMessage(payload, response.status))
    .catch(() => getApiErrorMessage({}, response.status));
}

async function apiRequest(path, options = {}) {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
  });

  if (!response.ok) {
    throw new Error(await readApiError(response));
  }

  return response.json();
}

function RatingRow({ label, value, onChange, required = true }) {
  return (
    <fieldset className="feedback-rating-row">
      <legend>
        <span>{label}</span>
        {required ? <small>Required</small> : null}
      </legend>

      <div className="feedback-stars" role="group" aria-label={label}>
        {[1, 2, 3, 4, 5].map((rating) => (
          <button
            type="button"
            key={rating}
            className={rating <= value ? "selected" : ""}
            aria-label={`${rating} out of 5`}
            aria-pressed={rating === value}
            onClick={() => onChange(rating)}
          >
            <FaStar />
          </button>
        ))}
        <span className="feedback-rating-value">
          {value ? `${value}/5` : "Select"}
        </span>
      </div>
    </fieldset>
  );
}

export default function GuestFeedback() {
  const navigate = useNavigate();
  const params = useMemo(() => new URLSearchParams(window.location.search), []);
  const bookingId = params.get("booking") || "";
  const isCompanion = params.get("companion") === "1";
  const feedbackPath = `/public-bookings/${encodeURIComponent(bookingId)}/feedback${isCompanion ? "/companion" : ""}`;
  const token = useMemo(() => new URLSearchParams(window.location.hash.slice(1)).get("token") || params.get("token") || "", [params]);

  const [booking, setBooking] = useState(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [invitations, setInvitations] = useState(null);
  const [inviting, setInviting] = useState(false);
  const [inviteError, setInviteError] = useState("");
  const [copiedSlot, setCopiedSlot] = useState(null);

  const [ratings, setRatings] = useState({
    overall: 0,
    cleanliness: 0,
    service: 0,
    villa: 0,
    value: 0,
  });
  const [wouldRecommend, setWouldRecommend] = useState(null);
  const [comments, setComments] = useState("");
  const [privateNote, setPrivateNote] = useState("");
  const [hideIdentity, setHideIdentity] = useState(false);

  useEffect(() => {
    document.title = "Share your stay | The Villa";
    const meta = document.createElement("meta");
    meta.name = "referrer"; meta.content = "no-referrer";
    document.head.appendChild(meta);
    // Fragments survive reloads but are never sent to the server or as referrers.
    window.history.replaceState(null,"",`${window.location.pathname}?booking=${encodeURIComponent(bookingId)}${isCompanion ? "&companion=1" : ""}#token=${encodeURIComponent(token)}`);


    let active = true;

    async function loadFeedback() {
      if (!bookingId || !token) {
        if (active) {
          setError("This feedback link is incomplete.");
          setLoading(false);
        }
        return;
      }

      try {
        const result = await apiRequest(
          feedbackPath,
          { headers: { "X-Feedback-Token": token }, cache: "no-store" }
        );

        if (!active) return;

        setBooking(result?.booking || null);
        setSubmitted(Boolean(result?.submitted));
      } catch (requestError) {
        if (!active) return;
        setError(
          getUserFacingError(requestError, "This feedback link could not be opened.")
        );
      } finally {
        if (active) setLoading(false);
      }
    }

    loadFeedback();

    return () => {
      active = false;
      meta.remove();
    };
  }, [bookingId, token, isCompanion, feedbackPath]);

  function setRating(field, value) {
    setRatings((current) => ({ ...current, [field]: value }));
  }

  async function submitFeedback(event) {
    event.preventDefault();
    setError("");

    if (!ratings.overall) {
      setError("Please select an overall rating from 1 to 5.");
      return;
    }

    if (comments.trim().length < 20 || comments.trim().split(/\s+/).filter(Boolean).length < 4) {
      setError("Please write at least 20 characters and four words describing your stay.");
      return;
    }
    setSubmitting(true);

    try {
      const result = await apiRequest(
        feedbackPath,
        {
          method: "POST",
          body: JSON.stringify({
            token,
            overall_rating: ratings.overall,
            cleanliness_rating: ratings.cleanliness || null,
            service_rating: ratings.service || null,
            villa_rating: ratings.villa || null,
            value_rating: ratings.value || null,
            would_recommend: wouldRecommend,
            comments: comments.trim(),
            hide_identity: isCompanion || hideIdentity,
            private_note: privateNote.trim() || null,
          }),
        }
      );

      setSubmitted(true);
      setError("");
      if (result?.message) {
        setBooking((current) => current || {});
      }
    } catch (requestError) {
      setError(getUserFacingError(requestError, "Your feedback could not be submitted."));
    } finally {
      setSubmitting(false);
    }
  }

  async function createInvitations() {
    setInviting(true); setInviteError("");
    try {
      const result = await apiRequest(`/public-bookings/${encodeURIComponent(bookingId)}/feedback/companions`, {
        method: "POST", body: JSON.stringify({ token }),
      });
      setInvitations(result.invitations || []);
    } catch (requestError) { setInviteError(getUserFacingError(requestError, "Feedback invitations could not be created.")); }
    finally { setInviting(false); }
  }

  async function copyInvitation(invitation) {
    try {
      await navigator.clipboard.writeText(invitation.url);
      setCopiedSlot(invitation.slot);
    } catch { setInviteError("Copy the link from its text field to share it."); }
  }

  if (loading) return <LoadingScreen message="Loading your feedback form…"/>;

  if (error && !booking) {
    return (
      <main className="feedback-page">
        <section className="feedback-card feedback-error-card">
          <div className="feedback-brand">
            <img src="/favicon.png" alt="The Villa" />
            <div>
              <strong>The Villa</strong>
              <span>Batangas Private Staycation</span>
            </div>
          </div>
          <div className="feedback-error-icon">!</div>
          <span className="feedback-kicker">Feedback link</span>
          <h1>We could not open this form.</h1>
          <AlertMessage message={error}/>
          <button type="button" className="feedback-primary" onClick={() => navigate("/")}>
            <FaHome /> Return home
          </button>
        </section>
      </main>
    );
  }

  if (submitted) {
    return (
      <main className="feedback-page">
        <section className="feedback-card feedback-success-card">
          <div className="feedback-brand">
            <img src="/favicon.png" alt="The Villa" />
            <div>
              <strong>The Villa</strong>
              <span>Batangas Private Staycation</span>
            </div>
          </div>

          <div className="feedback-success-icon"><FaCheck /></div>
          <span className="feedback-kicker">Thank you</span>
          <h1>Thank you for sharing your stay.</h1>
          <p>Thank you for taking a moment to share your experience with The Villa.</p>

          {!isCompanion && <section className="feedback-companions" aria-labelledby="companion-heading">
            <span className="feedback-kicker">A shared stay, individual experiences</span>
            <h2 id="companion-heading">Invite your companions</h2>
            <p>Let the other guests tell us about their stay. Each person gets a separate, single-use link. Their feedback goes to our team and does not affect the public villa rating.</p>
            <button type="button" className="feedback-primary" disabled={inviting} onClick={createInvitations}>
              {inviting ? "Preparing links…" : invitations ? "Refresh guest links" : "Create guest links"}
            </button>
            {inviteError && <AlertMessage message={inviteError} />}
            {invitations?.length === 0 && <p>This reservation has no companion places available.</p>}
            {invitations && invitations.length > 0 && <>
              <p>Share one different link with each companion. Links expire with your feedback invitation.</p>
              <ul className="feedback-invite-list">{invitations.map(invitation => <li key={invitation.slot}>
                <div><strong>Companion {invitation.slot}</strong><span>{invitation.submitted ? "Feedback received" : "Ready to share"}</span></div>
                {!invitation.submitted && <><label className="feedback-link-label">Private invitation link<input readOnly value={invitation.url} onFocus={event => event.target.select()} /></label>
                <button type="button" onClick={() => copyInvitation(invitation)}>{copiedSlot === invitation.slot ? "Copied!" : "Copy link"}</button></>}
              </li>)}</ul>
              <p role="status">{copiedSlot ? `Companion ${copiedSlot} link copied. Send it through your preferred messaging app.` : "Only share these links with people who stayed with you."}</p>
            </>}
          </section>}

          {booking?.booking_code ? (
            <div className="feedback-reference">
              <span>Booking reference</span>
              <strong>{booking.booking_code}</strong>
            </div>
          ) : null}

          <button type="button" className="feedback-primary" onClick={() => navigate("/")}>
            <FaHome /> Return home
          </button>
        </section>
      </main>
    );
  }

  return (
    <main className="feedback-page">
      <section className="feedback-shell">
        <header className="feedback-header">
          <button type="button" className="feedback-back" onClick={() => navigate("/")}>
            <FaChevronLeft /> Home
          </button>

          <div className="feedback-brand centered">
            <img src="/favicon.png" alt="The Villa" />
            <div>
              <strong>The Villa</strong>
              <span>Batangas Private Staycation</span>
            </div>
          </div>
        </header>

        <div className="feedback-content">
          <div className="feedback-intro">
            <span className="feedback-kicker">{isCompanion ? "Companion feedback · For our team" : "Your stay, in your words"}</span>
            <h1>How was your stay?</h1>
            <p>{isCompanion ? "You were invited by the booking guest. Share your own experience privately with The Villa team." : "A few thoughtful words help us make the next stay even better. This takes about two minutes."}</p>
          </div>

          {booking ? (
            <div className="feedback-stay-card">
              <div>
                <span>Your stay</span>
                <strong>{isCompanion ? "Invited companion" : "Booking guest"}</strong>
              </div>
              <div>
                <span>Villa</span>
                <strong>{booking.villa_name || "The Villa"}</strong>
              </div>
              <div>
                <span>Checkout date</span>
                <strong>{booking.check_out_date || "Completed stay"}</strong>
              </div>
            </div>
          ) : null}

          <form className="feedback-form" onSubmit={submitFeedback}>
            <section className="feedback-section">
              <div className="feedback-section-heading">
                <span>01</span>
                <div>
                  <h2>Rate your experience</h2>
                  <p>Select one overall rating from 1 to 5, then share your experience below.</p>
                </div>
              </div>

              <div className="feedback-rating-list">
                <RatingRow label="Overall star rating" value={ratings.overall} onChange={(value) => setRating("overall", value)} />
                <details className="feedback-optional-ratings"><summary>Add optional detailed ratings</summary>
                <RatingRow required={false} label="Cleanliness" value={ratings.cleanliness} onChange={(value) => setRating("cleanliness", value)} />
                <RatingRow required={false} label="Service" value={ratings.service} onChange={(value) => setRating("service", value)} />
                <RatingRow required={false} label="Villa and facilities" value={ratings.villa} onChange={(value) => setRating("villa", value)} />
                <RatingRow required={false} label="Value for your stay" value={ratings.value} onChange={(value) => setRating("value", value)} />
                </details>
              </div>
            </section>

            <section className="feedback-section">
              <div className="feedback-section-heading">
                <span>02</span>
                <div>
                  <h2>Would you recommend us? <small>(optional)</small></h2>
                  <p>You may skip this question. Your overall rating and comment are the required fields.</p>
                </div>
              </div>

              <div className="feedback-choice-grid">
                <button
                  type="button"
                  aria-pressed={wouldRecommend === true}
                  className={wouldRecommend === true ? "active" : ""}
                  onClick={() => setWouldRecommend(true)}
                >
                  Yes, I would
                </button>
                <button
                  type="button"
                  aria-pressed={wouldRecommend === false}
                  className={wouldRecommend === false ? "active" : ""}
                  onClick={() => setWouldRecommend(false)}
                >
                  Not at this time
                </button>
              </div>
            </section>

            <section className="feedback-section">
              <div className="feedback-section-heading">
                <span>03</span>
                <div>
                  <h2>Tell us more</h2>
                  <p>Share anything that would help us understand your stay.</p>
                </div>
              </div>

              <label className="feedback-field">
                <span>Tell us what went well and what could improve (required)</span>
                <textarea
                  required
                  minLength={20}
                  value={comments}
                  onChange={(event) => setComments(event.target.value)}
                  maxLength={3000}
                  rows={5}
                  placeholder="Describe your experience in at least four words and 20 characters."
                />
              </label>

              <p className="feedback-character-count">{comments.trim().length}/3,000 characters · Minimum 20 characters and four words</p>
              <label className="feedback-field">
                <span>Anything you would like us to know privately?</span>
                <textarea
                  value={privateNote}
                  onChange={(event) => setPrivateNote(event.target.value)}
                  maxLength={3000}
                  rows={4}
                  placeholder="Optional private note"
                />
              </label>
              {!isCompanion && <label className="feedback-identity-option"><input type="checkbox" checked={hideIdentity} onChange={event => setHideIdentity(event.target.checked)} /><span>Show my public review as Anonymous guest.</span></label>}
              <p className="feedback-privacy-note">{isCompanion ? 'Your feedback is for our team only. It is shown as Anonymous guest in the dashboard and is excluded from public reviews and ratings.' : hideIdentity?'Your review will appear as “Anonymous” on the website and feedback dashboard.':'Your review will display your booking name on the website and feedback dashboard.'} Contact details and booking references stay private. The system retains a restricted booking association to verify your stay. Avoid identifying details in your comments.</p>
              <p className="feedback-privacy-note">Private notes are stored separately, excluded from the feedback dashboard and AI analysis, and are not published.</p>
            </section>

            {error ? <AlertMessage message={error}/> : null}

            <button type="submit" className="feedback-submit" disabled={submitting}>
              {submitting ? <FaSpinner className="feedback-spinner" /> : <FaCheck />}
              {submitting ? "Sending feedback" : "Submit feedback"}
            </button>

            <p className="feedback-privacy-note">
              Your feedback is connected to this reservation and is used by The Villa to review the guest experience.
            </p>
          </form>
        </div>
      </section>
    </main>
  );
}
