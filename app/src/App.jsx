import { useEffect, useState } from "react";
import "leaflet/dist/leaflet.css";
import "./App.css";
import MapaView from "./views/MapaView";
import PlanoView from "./views/PlanoView";

const ABAS = ["Mapa", "Plano da Semana", "Carteira", "Painel"];

export default function App() {
  const [aba, setAba] = useState("Mapa");
  const [clientes, setClientes] = useState(null);
  const [logoOk, setLogoOk] = useState(true);

  useEffect(() => {
    fetch("/clientes.json")
      .then((r) => r.json())
      .then(setClientes)
      .catch(() => setClientes([]));
  }, []);

  return (
    <div className="app">
      <header className="nav">
        <div className="nav-inner">
          <div className="brand">
            {logoOk ? (
              <img
                src="/ppg-logo.webp"
                alt="PPG Parafusos e Ferramentas"
                className="brand-logo"
                onError={() => setLogoOk(false)}
              />
            ) : (
              <div className="brand-wordmark">
                <span>PPG</span>
                <small>Parafusos e Ferramentas</small>
              </div>
            )}
          </div>
          <nav className="tabs">
            {ABAS.map((t) => (
              <button key={t} className={"tab" + (aba === t ? " active" : "")} onClick={() => setAba(t)}>
                {t}
              </button>
            ))}
          </nav>
          <div className="nav-right">
            <span className="muted" style={{ fontSize: 13 }}>
              {clientes ? `${clientes.length.toLocaleString("pt-BR")} clientes` : "carregando…"}
            </span>
          </div>
        </div>
      </header>

      <main className="conteudo">
        {!clientes ? (
          <div className="vazio">Carregando carteira…</div>
        ) : aba === "Mapa" ? (
          <MapaView clientes={clientes} />
        ) : aba === "Plano da Semana" ? (
          <PlanoView clientes={clientes} />
        ) : (
          <div className="vazio">
            <h3>{aba}</h3>
            <p className="muted">Em construção — próxima etapa.</p>
          </div>
        )}
      </main>
    </div>
  );
}
