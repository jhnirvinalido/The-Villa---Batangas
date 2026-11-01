import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
} from "react-router-dom";

import App from "./App";
import BookForm from "./BookForm";
import ProtectedRoute from "./ProtectedRoute";
import AdminLogin from "./AdminLogin";
import AdminDashboard from "./AdminDashboard";
import FrontDeskDashboard from "./FrontDeskDashboard";
import StaffDashboard from "./staffDashboard";

export default function AppRoutes() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public guest pages */}
        <Route path="/" element={<App />} />
        <Route path="/book" element={<BookForm />} />

        {/* Remove the old customer login and dashboard routes. */}
        <Route
          path="/register"
          element={<Navigate to="/book" replace />}
        />
        <Route
          path="/dashboard"
          element={<Navigate to="/book" replace />}
        />

        {/* Admin and staff remain protected. */}
        <Route path="/login" element={<AdminLogin />} />
        <Route path="/maintenance/*" element={<ProtectedRoute allowedRoles={["maintenance"]}><StaffDashboard /></ProtectedRoute>} />
        <Route
          path="/admin-login"
          element={<AdminLogin />}
        />

        <Route
          path="/admin-dashboard/*"
          element={
            <ProtectedRoute allowedRoles={["admin"]}>
              <AdminDashboard />
            </ProtectedRoute>
          }
        />

        <Route
          path="/staff/*"
          element={
            <ProtectedRoute allowedRoles={["staff"]}>
              <StaffDashboard />
            </ProtectedRoute>
          }
        />

        <Route
          path="/front-desk-login"
          element={<Navigate to="/login" replace />}
        />

        <Route
          path="/front-desk/*"
          element={
            <ProtectedRoute allowedRoles={["front_desk"]}>
              <FrontDeskDashboard />
            </ProtectedRoute>
          }
        />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
