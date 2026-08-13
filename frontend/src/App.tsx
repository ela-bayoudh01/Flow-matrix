import { BrowserRouter, Routes, Route, Link, useLocation } from "react-router-dom";
import AppBar from "@mui/material/AppBar";
import Toolbar from "@mui/material/Toolbar";
import Tabs from "@mui/material/Tabs";
import Tab from "@mui/material/Tab";
import { FlowsTablePage } from "./pages/FlowsTablePage";
import { MatrixPage } from "./pages/MatrixPage";

// DashboardPage et HistoryPage ajoutées au fur et à mesure (voir docs/frontend/).
function Navigation() {
  const location = useLocation();
  return (
    <AppBar position="static" color="default" elevation={1}>
      <Toolbar variant="dense">
        <Tabs value={location.pathname}>
          <Tab label="Matrice" value="/" component={Link} to="/" />
          <Tab label="Table des flux" value="/flows" component={Link} to="/flows" />
        </Tabs>
      </Toolbar>
    </AppBar>
  );
}

function App() {
  return (
    <BrowserRouter>
      <Navigation />
      <Routes>
        <Route path="/" element={<MatrixPage />} />
        <Route path="/flows" element={<FlowsTablePage />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
