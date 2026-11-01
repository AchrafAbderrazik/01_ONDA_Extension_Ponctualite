import React, { useEffect, useState } from "react";
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, Scatter, ComposedChart,
  BarChart, Bar, Legend,
} from "recharts";

const AIRPORTS = ["", "EWR", "JFK", "LGA"];
const pct = (x, d = 1) => (x == null ? "—" : `${(x * 100).toLocaleString("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d })}\u00a0%`);
const num = (x) => (x == null ? "—" : x.toLocaleString("fr-FR"));
const dec = (x, d) => (x == null ? "—" : x.toLocaleString("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d }));

async function getJSON(url, opts) {
  const r = await fetch(url, opts);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.error || body.message || `HTTP ${r.status}`);
  return body;
}

function useApi(url, deps) {
  const [state, set] = useState({ data: null, error: null, loading: true });
  useEffect(() => {
    let live = true;
    set((s) => ({ ...s, loading: true }));
    getJSON(url).then((d) => live && set({ data: d, error: null, loading: false }))
      .catch((e) => live && set({ data: null, error: e.message, loading: false }));
    return () => { live = false; };
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps
  return state;
}

function Status({ s }) {
  if (s.loading) return <p className="muted">Chargement…</p>;
  if (s.error) return <p className="error">Erreur : {s.error}</p>;
  return null;
}

function AirportSelect({ value, onChange }) {
  return (
    <label className="filter">Aéroport&nbsp;
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {AIRPORTS.map((a) => <option key={a} value={a}>{a || "Tous"}</option>)}
      </select>
    </label>
  );
}

function Kpi({ label, value, hint }) {
  return <div className="kpi"><div className="kpi-value">{value}</div><div className="kpi-label">{label}</div>{hint && <div className="kpi-hint">{hint}</div>}</div>;
}

function Overview() {
  const [airport, setAirport] = useState("");
  const q = airport ? `?airport=${airport}` : "";
  const k = useApi(`/api/kpis${q}`, [airport]);
  const ts = useApi(`/api/kpis/timeseries${q}${q ? "&" : "?"}granularity=day`, [airport]);
  const an = useApi(`/api/anomalies${q}${q ? "&" : "?"}limit=8`, [airport]);
  const series = (ts.data?.series || []).map((d) => ({ ...d, anomalyPoint: d.anomaly ? d.disruption_rate : null }));
  const o = k.data?.overall;
  return (
    <section>
      <div className="toolbar"><AirportSelect value={airport} onChange={setAirport} /></div>
      <Status s={k} />
      {o && (
        <div className="kpis">
          <Kpi label="Vols programmés" value={num(o.flights)} />
          <Kpi label="Ponctualité (OTP15)" value={pct(o.otp15)} hint="départ < 15 min après l'horaire" />
          <Kpi label="Retard moyen au départ" value={`${o.avg_dep_delay.toLocaleString("fr-FR")}\u00a0min`} />
          <Kpi label="Taux d'annulation" value={pct(o.cancel_rate, 2)} />
          <Kpi label="Taux de perturbation" value={pct(o.disruption_rate)} hint="retard ≥ 15 min ou annulation" />
        </div>
      )}
      <h3>Taux de perturbation journalier (points rouges : journées anormales détectées)</h3>
      <Status s={ts} />
      <ResponsiveContainer width="100%" height={300}>
        <ComposedChart data={series} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis dataKey="period" minTickGap={40} tick={{ fontSize: 11 }} />
          <YAxis tickFormatter={(v) => `${Math.round(v * 100)}%`} domain={[0, 1]} tick={{ fontSize: 11 }} />
          <Tooltip formatter={(v) => pct(v)} />
          <Line type="monotone" dataKey="disruption_rate" name="Taux de perturbation" stroke="#0B4A6F" dot={false} strokeWidth={1.4} isAnimationActive={false} />
          <Scatter dataKey="anomalyPoint" name="Anomalie" fill="#C0392B" isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
      <h3>Journées les plus anormales</h3>
      <Status s={an} />
      <table>
        <thead><tr><th>Date</th><th>Aéroport</th><th>Vols</th><th>Perturbation</th><th>Référence</th><th>z robuste</th><th>Cause probable</th></tr></thead>
        <tbody>
          {(an.data?.anomalies || []).map((a) => (
            <tr key={a.origin + a.date_key}><td>{a.date_key}</td><td>{a.origin}</td><td>{a.flights}</td><td>{pct(a.disruption_rate)}</td>
              <td>{pct(a.baseline)}</td><td>{dec(a.robust_z, 1)}</td><td>{a.likely_cause}</td></tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function Delays() {
  const [airport, setAirport] = useState("");
  const q = airport ? `?airport=${airport}` : "";
  const byHour = useApi(`/api/delays/by-hour${q}`, [airport]);
  const k = useApi(`/api/kpis${q}`, [airport]);
  const carriers = (k.data?.by_carrier || []).filter((c) => c.flights >= 500);
  return (
    <section>
      <div className="toolbar"><AirportSelect value={airport} onChange={setAirport} /></div>
      <h3>Ponctualité et perturbation par heure de départ programmée</h3>
      <Status s={byHour} />
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={byHour.data?.series || []}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis dataKey="hour" tickFormatter={(h) => `${h}h`} tick={{ fontSize: 11 }} />
          <YAxis tickFormatter={(v) => `${Math.round(v * 100)}%`} tick={{ fontSize: 11 }} />
          <Tooltip formatter={(v) => pct(v)} labelFormatter={(h) => `${h}h`} />
          <Legend />
          <Bar dataKey="disruption_rate" name="Taux de perturbation" fill="#0B4A6F" />
        </BarChart>
      </ResponsiveContainer>
      <h3>Ponctualité (OTP15) par compagnie (≥ 500 vols)</h3>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={carriers} layout="vertical" margin={{ left: 40 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis type="number" domain={[0.5, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} tick={{ fontSize: 11 }} />
          <YAxis type="category" dataKey="carrier" tick={{ fontSize: 11 }} />
          <Tooltip formatter={(v) => pct(v)} labelFormatter={(c) => carriers.find((x) => x.carrier === c)?.name || c} />
          <Bar dataKey="otp15" name="OTP15" fill="#2E86AB" />
        </BarChart>
      </ResponsiveContainer>
    </section>
  );
}

function Risk() {
  const [date, setDate] = useState("2013-12-05");
  const [airport, setAirport] = useState("");
  const s = useApi(`/api/flights/risk?date=${date}&limit=60${airport ? `&airport=${airport}` : ""}`, [date, airport]);
  return (
    <section>
      <div className="toolbar">
        <label className="filter">Date (période de validation et de test)&nbsp;
          <input type="date" min="2013-10-01" max="2013-12-31" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <AirportSelect value={airport} onChange={setAirport} />
      </div>
      <p className="muted">Vols classés par probabilité de perturbation estimée avant le départ. La colonne « Observé » montre ce qui s'est réellement passé (données historiques).</p>
      <Status s={s} />
      <table>
        <thead><tr><th>Horaire</th><th>Vol</th><th>Liaison</th><th>Probabilité</th><th>Niveau</th><th>Facteurs de contexte</th><th>Observé</th></tr></thead>
        <tbody>
          {(s.data?.flights || []).map((f) => (
            <tr key={f.flight_id}>
              <td>{f.sched_dep_local.slice(11)}</td><td>{f.carrier} {f.flight_no}</td><td>{f.origin} → {f.dest}</td>
              <td>{pct(f.proba)}</td><td><span className={`badge ${f.risk_level}`}>{f.risk_level}</span></td>
              <td className="small">{f.factors.join(" · ")}</td>
              <td>{f.observed_disruption ? "perturbé" : "à l'heure"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function Quality() {
  const s = useApi("/api/quality", []);
  return (
    <section>
      <h3>Règles de qualité appliquées lors du dernier chargement</h3>
      <Status s={s} />
      {s.data && <p className="muted">Exécution {s.data.run.run_id} — {num(s.data.run.rows_flight)} vols, {num(s.data.run.rows_weather)} observations météo.</p>}
      <table>
        <thead><tr><th>Règle</th><th>Table</th><th>Contrôle</th><th>Gravité</th><th>Contrôlées</th><th>Violations</th><th>Action</th></tr></thead>
        <tbody>
          {(s.data?.rules || []).map((r, i) => (
            <tr key={i} className={r.violations ? "warn" : ""}><td>{r.rule_id}</td><td>{r.table_name}</td><td>{r.description}</td>
              <td>{r.severity}</td><td>{num(r.checked)}</td><td>{num(r.violations)}</td><td>{r.action}</td></tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function Model() {
  const s = useApi("/api/model/metrics", []);
  const m = s.data;
  return (
    <section>
      <Status s={s} />
      {m && (<>
        <h3>Résultats sur le test (nov.–déc. 2013, {num(m.n.test)} vols) — modèle retenu : {m.model}</h3>
        <table>
          <thead><tr><th>Modèle</th><th>ROC-AUC</th><th>PR-AUC</th><th>Brier</th><th>Précision top 10 %</th><th>Lift top 10 %</th></tr></thead>
          <tbody>
            {Object.entries(m.test).map(([name, t]) => (
              <tr key={name} className={name === m.model ? "best" : ""}><td>{name}</td><td>{dec(t.roc_auc, 3)}</td><td>{dec(t.pr_auc, 3)}</td>
                <td>{dec(t.brier, 4)}</td><td>{pct(t.top10.precision)}</td><td>{dec(t.top10.lift, 2)}</td></tr>
            ))}
          </tbody>
        </table>
        <p className="muted">Découpage temporel : entraînement {m.split.train}, validation {m.split.valid}, test {m.split.test}. Seuils de niveau de risque fixés sur la validation : modéré ≥ {pct(m.thresholds.modere)}, élevé ≥ {pct(m.thresholds.eleve)}.</p>
        <div className="figs">
          {["roc_pr.png", "calibration.png", "importance.png"].map((f) => <img key={f} src={`/api/model/figures/${f}`} alt={f} />)}
        </div>
      </>)}
    </section>
  );
}

const TABS = [["Vue d'ensemble", Overview], ["Retards", Delays], ["Vols à risque", Risk], ["Qualité des données", Quality], ["Modèle", Model]];

export default function App() {
  const [tab, setTab] = useState(0);
  const health = useApi("/api/health", []);
  const View = TABS[tab][1];
  return (
    <div className="app">
      <header>
        <div>
          <h1>Ponctualité &amp; prédiction des retards</h1>
          <p className="sub">Extension data/IA d'une plateforme aéroportuaire — démonstration sur données publiques</p>
        </div>
        <span className={`dot ${health.data?.status === "ok" ? "ok" : "ko"}`}>{health.data?.status === "ok" ? "API connectée" : "API indisponible"}</span>
      </header>
      <nav>{TABS.map(([label], i) => <button key={label} className={i === tab ? "active" : ""} onClick={() => setTab(i)}>{label}</button>)}</nav>
      <main><View /></main>
      <footer>{health.data?.disclaimer || "Projet personnel sur données publiques (nycflights13 / US BTS 2013). Non affilié à l'ONDA."}</footer>
    </div>
  );
}
