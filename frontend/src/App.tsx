import { NavLink, Route, Routes } from "react-router-dom";
import IntakeScreen from "./intake/IntakeScreen";

const tab = ({ isActive }: { isActive: boolean }) =>
  `px-3 py-1.5 rounded-sm text-sm font-semibold ${isActive ? "bg-panel text-ink" : "text-muted hover:text-ink"}`;

export default function App() {
  return (
    <div className="min-h-screen">
      <header className="bg-header text-ink border-b border-line">
        <div className="mx-auto max-w-[1400px] px-4 h-11 flex items-center gap-6">
          <span className="font-bold tracking-wide">CounterWrench</span>
          <nav className="flex gap-1">
            <NavLink to="/" end className={tab}>New intake</NavLink>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-[1400px] px-4 py-4">
        <Routes>
          <Route path="/" element={<IntakeScreen />} />
        </Routes>
      </main>
    </div>
  );
}
