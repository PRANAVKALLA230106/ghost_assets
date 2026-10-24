import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import "./index.css";
import CaseLayout from "./pages/CaseLayout";
import CasePage from "./pages/CasePage";
import ClaimsPage from "./pages/ClaimsPage";
import DevPage from "./pages/DevPage";
import NewCasePage from "./pages/NewCasePage";
import ProofPage from "./pages/ProofPage";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route path="/" element={<NewCasePage />} />
        <Route path="/case/:id" element={<CaseLayout />}>
          <Route index element={<CasePage />} />
          <Route path="claims" element={<ClaimsPage />} />
          <Route path="proof" element={<ProofPage />} />
        </Route>
        <Route path="/dev" element={<DevPage />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
);
