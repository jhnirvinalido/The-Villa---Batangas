import SystemFeedback from "./SystemFeedback";
import ReactDOM from "react-dom/client";
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";

import "bootstrap/dist/css/bootstrap.min.css";
import "./App.css";
import "./tailwind.css";

import App from "./App.jsx";
import BookForm from "./BookForm.jsx";
import GuestFeedback from "./GuestFeedback.jsx";
import MaintenanceResponse from "./MaintenanceResponse.jsx";
import AdminLogin from "./AdminLogin.jsx";
import AdminDashboard from "./AdminDashboard.jsx";
import StaffDashboard from "./staffDashboard.jsx";
import ProtectedRoute from "./ProtectedRoute.jsx";

/*
  Redirect old customer routes to the new public booking form.

  The query string is preserved so a URL such as:

  /dashboard?payment=success&booking=123

  becomes:

  /book?payment=success&booking=123
*/
function LegacyBookingRedirect() {
  const location = useLocation();

  return (
    <Navigate
      to={{
        pathname: "/book",
        search: location.search,
        hash: location.hash,
      }}
      replace
    />
  );
}

const rootElement =
  document.getElementById("root");

if (!rootElement) {
  throw new Error(
    "The root element was not found."
  );
}

ReactDOM.createRoot(
  rootElement
).render(
  <BrowserRouter>
    <SystemFeedback/>
    <Routes>
      {/* Public landing page */}
      <Route
        path="/"
        element={<App />}
      />

      <Route path="/feedback" element={<GuestFeedback />} />
      <Route path="/maintenance-response" element={<MaintenanceResponse />} />

      {/* Public modern booking form */}
      <Route
        path="/book"
        element={<BookForm />}
      />

      {/*
        Old customer routes are retained as redirects
        so existing links and PayMongo return URLs
        will continue to work.
      */}
      <Route
        path="/register"
        element={
          <LegacyBookingRedirect />
        }
      />

      <Route
        path="/dashboard"
        element={
          <LegacyBookingRedirect />
        }
      />

      {/* Admin authentication */}
      <Route
        path="/admin-login"
        element={<AdminLogin />}
      />

      {/* Protected administrator dashboard */}
      <Route
        path="/admin-dashboard"
        element={
          <ProtectedRoute
            allowedRoles={["admin"]}
          >
            <AdminDashboard />
          </ProtectedRoute>
        }
      />

      <Route
        path="/admin"
        element={
          <Navigate
            to="/admin-dashboard"
            replace
          />
        }
      />

      {/* Protected staff dashboard */}
      <Route
        path="/staff"
        element={
          <ProtectedRoute
            allowedRoles={["staff"]}
          >
            <StaffDashboard />
          </ProtectedRoute>
        }
      />

      {/* Unknown URL */}
      <Route
        path="*"
        element={
          <Navigate
            to="/"
            replace
          />
        }
      />
    </Routes>
  </BrowserRouter>
);
