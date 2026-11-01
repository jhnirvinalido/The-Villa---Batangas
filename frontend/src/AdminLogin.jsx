import { AlertMessage } from "./SystemFeedback";
import { feedbackFetch as fetch } from "./requestFeedback.mjs";
import { getApiErrorMessage, getUserFacingError } from "./errorMessages.mjs";
import { staffLoginReturnPath } from "./staffNotificationFeed.mjs";
import { LEGACY_FRONT_DESK_SESSION_KEY, portalLoginDestination } from "./portalRouting.mjs";
import { useState } from "react";
import {
  Eye,
  EyeOff,
  KeyRound,
  Mail,
} from "lucide-react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import "./AdminLogin.css";

const API_URL = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const REMEMBERED_EMAIL_KEY = "theVillaRememberedLoginEmail";
const PORTAL_SESSION_KEY =
  "theVillaPortalAuth";

const CUSTOMER_SESSION_KEY =
  "theVillaAuth";

function clearOldPortalSessions() {
  const keys = [
    "theVillaAdminAuth",
    "theVillaStaffAuth",
    "theVillaAuthToken",
    "theVillaApiToken",
    "theVillaRefreshToken",
    PORTAL_SESSION_KEY,
    LEGACY_FRONT_DESK_SESSION_KEY,
  ];

  keys.forEach((key) => {
    localStorage.removeItem(key);
    sessionStorage.removeItem(key);
  });
}

function savePortalSession(session) {
  /*
  |--------------------------------------------------------------------------
  | SHARED LOGIN, ROLE-BASED WORKSPACES
  |--------------------------------------------------------------------------
  |
  | Each signed-in account opens its own workspace. Remembering an email does not
  | remember its login tokens.
  |
  */

  clearOldPortalSessions();

  sessionStorage.setItem(
    PORTAL_SESSION_KEY,
    JSON.stringify(session)
  );
}


export default function VillaLogin() {
  const navigate = useNavigate();
  const location = useLocation();
  const rememberedEmailKey = REMEMBERED_EMAIL_KEY;

  const [email, setEmail] = useState(() => {
    try {
      return localStorage.getItem(rememberedEmailKey) || "";
    } catch {
      return "";
    }
  });
  const [password, setPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(Boolean(email));
  const [showPassword, setShowPassword] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isResetting, setIsResetting] = useState(false);

  function validateForm() {
    const normalizedEmail = email.trim().toLowerCase();
    if (!normalizedEmail) return "Please enter your email address.";
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalizedEmail)) {
      return "Please enter a valid email address.";
    }
    if (!password) return "Please enter your password.";
    if (password.length < 6) return "Your password must contain at least 6 characters.";
    return "";
  }

  async function handleLogin(event) {
    event.preventDefault();

    const validationError =
      validateForm();

    if (validationError) {
      setErrorMessage(
        validationError
      );
      return;
    }

    setErrorMessage("");
    setSuccessMessage("");
    setIsSubmitting(true);

    /*
    |--------------------------------------------------------------------------
    | REMOVE STALE PORTAL TOKENS BEFORE LOGIN
    |--------------------------------------------------------------------------
    */

    clearOldPortalSessions();

    try {
      const normalizedEmail =
        email.trim().toLowerCase();

      const response = await fetch(
        `${API_URL}/staff-auth/login`,
        {
          method: "POST",
          headers: {
            Accept: "application/json",
            "Content-Type":
              "application/json",
          },
          body: JSON.stringify({
            email: normalizedEmail,
            password,
          }),
        }
      );

      const data = await response
        .json()
        .catch(() => ({}));

      if (!response.ok) {
        throw new Error(
          data?.detail ||
            data?.message ||
            "Incorrect email address or password."
        );
      }

      const accessToken =
        typeof data?.access_token ===
        "string"
          ? data.access_token.trim()
          : "";

      const refreshToken =
        typeof data?.refresh_token ===
        "string"
          ? data.refresh_token.trim()
          : "";

      if (
        !accessToken ||
        !refreshToken
      ) {
        throw new Error(
          "The server returned an incomplete login session."
        );
      }

      /*
      |--------------------------------------------------------------------------
      | /staff-auth/login ALREADY APPLIES PORTAL RBAC
      |--------------------------------------------------------------------------
      */

      const returnedUser =
        data?.user ||
        {};

      const role = String(
        returnedUser?.role || ""
      )
        .trim()
        .toLowerCase();

      if (
        role !== "admin" &&
        role !== "staff" &&
        role !== "front_desk" &&
        role !== "maintenance"
      ) {
        throw new Error(
          "This account is not authorized for the management portal."
        );
      }

      const session = {
        authenticated: true,

        user: {
          ...returnedUser,

          id:
            returnedUser?.id ||
            "",

          staffId:
            returnedUser?.staffId ||
            returnedUser?.id ||
            "",

          staff_account_id:
            returnedUser
              ?.staff_account_id ||
            returnedUser?.id ||
            "",

          auth_user_id:
            returnedUser
              ?.auth_user_id ||
            returnedUser
              ?.authUserId ||
            "",

          authUserId:
            returnedUser
              ?.authUserId ||
            returnedUser
              ?.auth_user_id ||
            "",

          name:
            returnedUser
              ?.name ||
            returnedUser
              ?.fullName ||
            returnedUser
              ?.full_name ||
            "",

          fullName:
            returnedUser
              ?.fullName ||
            returnedUser
              ?.full_name ||
            returnedUser
              ?.name ||
            "",

          full_name:
            returnedUser
              ?.full_name ||
            returnedUser
              ?.fullName ||
            returnedUser
              ?.name ||
            "",

          role,

          portalRole:
            role,
        },

        id:
          returnedUser?.id ||
          "",

        authUserId:
          returnedUser
            ?.auth_user_id ||
          returnedUser
            ?.authUserId ||
          "",

        employeeCode:
          returnedUser
            ?.employee_code ||
          returnedUser
            ?.employeeCode ||
          "",

        name:
          returnedUser
            ?.full_name ||
          returnedUser
            ?.fullName ||
          returnedUser?.name ||
          "",

        full_name:
          returnedUser
            ?.full_name ||
          returnedUser
            ?.fullName ||
          returnedUser?.name ||
          "",

        fullName:
          returnedUser
            ?.fullName ||
          returnedUser
            ?.full_name ||
          returnedUser?.name ||
          "",

        portalRole:
          role,

        email:
          returnedUser?.email ||
          normalizedEmail,

        role,

        department:
          returnedUser
            ?.department ||
          "",

        position:
          returnedUser
            ?.position ||
          "",

        access_token:
          accessToken,

        refresh_token:
          refreshToken,

        expires_in:
          data?.expires_in ||
          null,

        token_type:
          data?.token_type ||
          "bearer",

        signed_in_at:
          new Date().toISOString(),
      };

      /*
      |--------------------------------------------------------------------------
      | PREVENT A MIXED CUSTOMER + PORTAL SECURITY CONTEXT
      |--------------------------------------------------------------------------
      */

      localStorage.removeItem(
        CUSTOMER_SESSION_KEY
      );

      sessionStorage.removeItem(
        CUSTOMER_SESSION_KEY
      );

      savePortalSession(
        session,
      );

      if (rememberMe) {
        localStorage.setItem(
          rememberedEmailKey,
          normalizedEmail
        );
      } else {
        localStorage.removeItem(
          rememberedEmailKey
        );
      }

      navigate(
        role === "staff"
          ? staffLoginReturnPath(location.state?.from)
          : portalLoginDestination(role, location.state?.from),
        {
          replace: true,
        }
      );
    } catch (error) {
      clearOldPortalSessions();

      setErrorMessage(
        getUserFacingError(error, "Unable to sign in.")
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleForgotPassword() {
    const normalizedEmail = email.trim().toLowerCase();
    setErrorMessage("");
    setSuccessMessage("");

    if (!normalizedEmail || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalizedEmail)) {
      setErrorMessage("Enter your authorized email address first.");
      return;
    }

    setIsResetting(true);
    try {
      const response = await fetch(`${API_URL}/staff-auth/forgot-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: normalizedEmail }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(getApiErrorMessage(data, response.status));
      setSuccessMessage(data.message || "Check your email for the password reset link.");
    } catch (error) {
      setErrorMessage(getUserFacingError(error, "Unable to request password recovery."));
    } finally {
      setIsResetting(false);
    }
  }

  return (
    <main className="villa-login-page">
      <section className="villa-login-brand-panel" aria-label="The Villa">
        <img className="villa-login-property-image" src="/image2.jpg" alt="The Villa in San Jose, Batangas" />
        <div className="villa-login-brand-content">
          <Link to="/" className="villa-login-brand">
            <img src="/favicon.png" alt="" />
            <strong>The Villa</strong>
          </Link>
          <div className="villa-login-brand-copy">
            <span>SAN JOSE, BATANGAS</span>
            <h2>Behind every<br />well-kept stay.</h2>
            <p>The workspace for our people and our property.</p>
          </div>
        </div>
      </section>

      <section className="villa-login-panel" aria-label="Sign in">
        <div className="villa-login-content">
          <Link to="/" className="villa-login-back">← Back to the website</Link>
          <div className="villa-login-mobile-brand">
            <img src="/favicon.png" alt="" />
            <strong>The Villa</strong>
          </div>
          <header className="villa-login-heading">
            <span className="villa-login-kicker">THE VILLA / TEAM PORTAL</span>
            <h1>Sign in to your workspace</h1>
            <p>Use the work account provided by your administrator.</p>
          </header>

          {errorMessage && <AlertMessage message={errorMessage}/>}
          {successMessage && <AlertMessage message={successMessage} type="success"/>}

          <form className="villa-login-form" onSubmit={handleLogin} aria-busy={isSubmitting || isResetting}>
            <label className="villa-login-field">
              <span>Email address</span>
              <div className="villa-login-input">
                <span className="villa-login-input-icon"><Mail size={18} /></span>
                <input
                  type="email"
                  name="email"
                  required
                  spellCheck={false}
                  value={email}
                  onChange={(event) => {
                    setEmail(event.target.value);
                    setErrorMessage("");
                    setSuccessMessage("");
                  }}
                  placeholder="Enter your work email"
                  autoComplete="email"
                  inputMode="email"
                  disabled={isSubmitting || isResetting}
                />
              </div>
            </label>

            <label className="villa-login-field">
              <span>Password</span>
              <div className="villa-login-input">
                <span className="villa-login-input-icon"><KeyRound size={18} /></span>
                <input
                  type={showPassword ? "text" : "password"}
                  name="password"
                  required
                  value={password}
                  onChange={(event) => {
                    setPassword(event.target.value);
                    setErrorMessage("");
                  }}
                  placeholder="Your password"
                  autoComplete="current-password"
                  disabled={isSubmitting || isResetting}
                />
                <button
                  type="button"
                  className="villa-password-toggle"
                  onClick={() => setShowPassword((current) => !current)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  disabled={isSubmitting || isResetting}
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </label>

            <div className="villa-login-options">
              <label className="villa-remember-option">
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(event) => setRememberMe(event.target.checked)}
                  disabled={isSubmitting || isResetting}
                />
                <span>Remember email</span>
              </label>

              <button
                type="button"
                className="villa-forgot-password"
                onClick={handleForgotPassword}
                disabled={isSubmitting || isResetting}
              >
                {isResetting ? "Sending..." : "Forgot password?"}
              </button>
            </div>

            <button type="submit" className="villa-login-submit" disabled={isSubmitting || isResetting}>
              {isSubmitting ? (
                <><span className="villa-login-spinner" /> Verifying account...</>
              ) : "Sign in"}
            </button>
          </form>
          <p className="villa-login-help">Need access? Contact your administrator.</p>
        </div>
      </section>
    </main>
  );
}
