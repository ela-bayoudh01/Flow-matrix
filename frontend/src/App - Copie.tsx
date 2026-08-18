import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Box from "@mui/material/Box";
import { Sidebar } from "./components/layout/Sidebar";
import { PageTransition } from "./components/layout/PageTransition";
import { FlowsTablePage } from "./pages/FlowsTablePage";
import { MatrixPage } from "./pages/MatrixPage";
import { DashboardPage } from "./pages/DashboardPage";
import { HistoryPage } from "./pages/HistoryPage";
import { RecommendationsPage } from "./pages/RecommendationsPage";
import { AclProposalsPage } from "./pages/AclProposalsPage";

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
              <Route path="/matrix" element={<MatrixPage />} />
              <Route path="/flows" element={<FlowsTablePage />} />
              <Route path="/history" element={<HistoryPage />} />
              <Route path="/recommendations" element={<RecommendationsPage />} />
              <Route path="/acl-proposals" element={<AclProposalsPage />} />
            </Routes>
          </PageTransition>
        </Box>
      </Box>
    </BrowserRouter>
  );
}

export default App;
