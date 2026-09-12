import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Box from "@mui/material/Box";
import { Sidebar } from "./components/layout/Sidebar";
import { PageTransition } from "./components/layout/PageTransition";
import { FlowsTablePage } from "./pages/FlowsTablePage";
import { MatrixPage } from "./pages/MatrixPage";
import { DashboardPage } from "./pages/DashboardPage";
import { ImportPage } from "./pages/ImportPage";
import { HistoryPage } from "./pages/HistoryPage";
import { ValidationCyclePage } from "./pages/ValidationCyclePage";
import { RecommendationsPage } from "./pages/RecommendationsPage";
import { AclProposalsPage } from "./pages/AclProposalsPage";
import { NetworkPoliciesPage } from "./pages/NetworkPoliciesPage";

function App() {
  return (
    <BrowserRouter>
      <Box sx={{ display: "flex" }}>
        <Sidebar />
        <Box component="main" sx={{ flex: 1, minWidth: 0, height: "100vh", overflowY: "auto" }}>
          <PageTransition>
            <Routes>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/import" element={<ImportPage />} />
              <Route path="/matrix" element={<MatrixPage />} />
              <Route path="/flows" element={<FlowsTablePage />} />
              <Route path="/history" element={<HistoryPage />} />
              <Route path="/validation-cycle" element={<ValidationCyclePage />} />
              <Route path="/recommendations" element={<RecommendationsPage />} />
              <Route path="/acl-proposals" element={<AclProposalsPage />} />
              <Route path="/network-policies" element={<NetworkPoliciesPage />} />
            </Routes>
          </PageTransition>
        </Box>
      </Box>
    </BrowserRouter>
  );
}

export default App;
