import { useState } from "react";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import IntakeScreen from "./intake/IntakeScreen";
import OrderScreen from "./orders/OrderScreen";
import OrdersScreen from "./orders/OrdersScreen";

const tab = ({ isActive }: { isActive: boolean }) =>
  `px-3 py-1.5 rounded-sm text-sm font-semibold ${isActive ? "bg-panel text-ink" : "text-muted hover:text-ink"}`;

export default function App() {
  // The intake keeps its form while you're on it. Clicking "New intake" while already there
  // changes no route, so React Router does nothing: bump a key to start the screen over.
  const [intakeKey, setIntakeKey] = useState(0);
  const { pathname } = useLocation();
  return (
    <div className="min-h-screen">
      <header className="bg-header text-ink border-b border-line">
        <div className="mx-auto max-w-[1400px] px-4 h-11 flex items-center gap-6">
          <span className="font-bold tracking-wide">CounterWrench</span>
          <nav className="flex gap-1">
            <NavLink to="/" end className={tab}
              onClick={() => pathname === "/" && setIntakeKey((k) => k + 1)}>New intake</NavLink>
            <NavLink to="/orders" className={tab}>Orders</NavLink>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-[1400px] px-4 py-4">
        <Routes>
          <Route path="/" element={<IntakeScreen key={intakeKey} />} />
          <Route path="/orders" element={<OrdersScreen />} />
          <Route path="/orders/:id" element={<OrderScreen />} />
        </Routes>
      </main>
    </div>
  );
}
