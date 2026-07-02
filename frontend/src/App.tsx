import { Routes, Route, Navigate } from 'react-router-dom';
import { I18nProvider } from './i18n';
import LoginPage from './pages/Login';
import Dashboard from './pages/Dashboard';

/** 检查是否已登录（本地有令牌） */
function isAuthenticated(): boolean {
  return !!localStorage.getItem('access_token');
}

/** 受保护路由包装器 */
function ProtectedRoute({ children }: { children: JSX.Element }) {
  if (!isAuthenticated()) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

export default function App() {
  return (
    <I18nProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Dashboard />
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </I18nProvider>
  );
}
