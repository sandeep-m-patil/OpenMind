import { NavLink, Route, Routes } from "react-router-dom";

import { IncidentPage } from "./pages/IncidentPage";
import { IncidentsPage } from "./pages/IncidentsPage";
import { KnowledgePage } from "./pages/KnowledgePage";

export function App() {
  return (
    <>
      <header className="topbar">
        <span className="brand">🧠 OpsMind <span className="muted">· human-in-the-loop SRE copilot</span></span>
        <nav>
          <NavLink to="/" end>Incidents</NavLink>
          <NavLink to="/learning">Learning</NavLink>
        </nav>
      </header>
      <Routes>
        <Route path="/" element={<IncidentsPage />} />
        <Route path="/incidents/:id" element={<IncidentPage />} />
        <Route path="/learning" element={<KnowledgePage />} />
      </Routes>
    </>
  );
}
