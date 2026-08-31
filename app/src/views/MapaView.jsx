import { useEffect, useMemo, useState } from "react";
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from "react-leaflet";
import { FAIXAS, FAIXA_COR, FAIXA_CHIP, FAIXA_DOT, brl, num, recenciaTexto } from "../lib/format";
import MapAutoSize from "../components/MapAutoSize";
import FichaCliente from "./FichaCliente";
import NovoClienteModal from "./NovoClienteModal";
import { api } from "../lib/api";

const FXKEY = { Ouro: "gold", Prata: "silver", Bronze: "bronze" };

// mediana — ignora outliers (clientes isolados em SP/NE) no enquadramento
function mediana(arr) {
  const s = [...arr].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

// Ajusta o mapa para enquadrar o NÚCLEO dos pontos visíveis (sem outliers)
function FitBounds({ pontos }) {
  const map = useMap();
  useEffect(() => {
    if (!pontos.length) return;
    const lats = pontos.map((p) => p.lat);
    const lngs = pontos.map((p) => p.lng);
    const cLat = mediana(lats);
    const cLng = mediana(lngs);
    // mantém só o que está a ~150km do centro mediano -> ignora outliers distantes
    const perto = pontos.filter(
      (p) => Math.abs(p.lat - cLat) < 1.4 && Math.abs(p.lng - cLng) < 1.4
    );
    const base = perto.length ? perto : pontos;
    const la = base.map((p) => p.lat);
    const ln = base.map((p) => p.lng);
    map.fitBounds(
      [
        [Math.min(...la), Math.min(...ln)],
        [Math.max(...la), Math.max(...ln)],
      ],
      { padding: [50, 50], maxZoom: 14 }
    );
  }, [pontos.length]); // refit quando muda o conjunto
  return null;
}

function raio(faixa) {
  return faixa === "Ouro" ? 7.5 : faixa === "Prata" ? 6 : 5;
}

export default function MapaView({ clientes, aoAtualizarCliente, visitaPendente, aoIniciarVisita, aoFinalizarVisita, aoCancelarVisita, usuario }) {
  const [faixasOn, setFaixasOn] = useState({ Ouro: true, Prata: true, Bronze: true });
  const [soRisco, setSoRisco] = useState(false);
  const [cidade, setCidade] = useState("Todas");
  const [busca, setBusca] = useState("");
  const [sel, setSel] = useState(null);
  const [fichaAberta, setFichaAberta] = useState(false);
  const [novoClienteAberto, setNovoClienteAberto] = useState(false);
  // Só importa em telas pequenas (a media query decide se o botão aparece):
  // no mobile painel e mapa não cabem juntos, então alterna qual ocupa a tela.
  // Começa em "painel" (filtro) — decisão explícita do usuário.
  const [modoMobile, setModoMobile] = useState("painel");

  const [incluirInativos, setIncluirInativos] = useState(false);
  const [clientesInativos, setClientesInativos] = useState(null); // null = ainda não buscou

  useEffect(() => {
    if (!incluirInativos || clientesInativos !== null) return;
    api.get("/api/clientes?incluirInativos=true")
      .then((todos) => setClientesInativos(todos.filter((c) => c.status === "inativo")))
      .catch(() => setClientesInativos([]));
  }, [incluirInativos, clientesInativos]);

  const baseClientes = useMemo(
    () => (incluirInativos && clientesInativos ? [...clientes, ...clientesInativos] : clientes),
    [clientes, incluirInativos, clientesInativos]
  );

  const cidades = useMemo(() => {
    const c = [...new Set(baseClientes.map((d) => d.cidade).filter(Boolean))];
    c.sort((a, b) => a.localeCompare(b));
    return ["Todas", ...c];
  }, [baseClientes]);

  const filtrados = useMemo(() => {
    const q = busca.trim().toLowerCase();
    return baseClientes.filter((d) => {
      if (!faixasOn[d.faixa]) return false;
      if (soRisco && !d.emRisco) return false;
      if (cidade !== "Todas" && d.cidade !== cidade) return false;
      if (q && !d.nome.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [baseClientes, faixasOn, soRisco, cidade, busca]);

  // reflete a atualização vinda da ficha no card lateral, na lista principal
  // do App e na lista local de inativos (some/aparece conforme o status novo)
  function aplicarAtualizacao(atualizado) {
    setSel(atualizado);
    aoAtualizarCliente(atualizado);
    setClientesInativos((lista) => {
      if (!lista) return lista;
      const semEsse = lista.filter((c) => c.id !== atualizado.id);
      return atualizado.status === "inativo" ? [...semEsse, atualizado] : semEsse;
    });
  }

  const contagem = useMemo(() => {
    const c = { Ouro: 0, Prata: 0, Bronze: 0, risco: 0 };
    for (const d of filtrados) {
      c[d.faixa] = (c[d.faixa] || 0) + 1;
      if (d.emRisco) c.risco++;
    }
    return c;
  }, [filtrados]);

  return (
    <div className={"mapa-layout" + (modoMobile === "mapa" ? " modo-mapa-mobile" : " modo-painel-mobile")}>
      {/* Só visível em telas pequenas (media query) — no mobile painel e mapa
          não cabem juntos numa altura usável, então cada um ocupa a tela
          inteira por vez, com esse botão pra alternar entre os dois. */}
      <button
        type="button"
        className="btn-alternar-mobile"
        onClick={() => setModoMobile((m) => (m === "mapa" ? "painel" : "mapa"))}
      >
        {modoMobile === "mapa" ? "☰ Ver filtros" : "🗺️ Ver mapa"}
      </button>

      {/* ---------- PAINEL LATERAL ---------- */}
      <aside className="painel">
        <div className="painel-head">
          <h3>Mapa da carteira</h3>
          <p className="muted" style={{ fontSize: 13 }}>
            {num(filtrados.length)} clientes visíveis
          </p>
        </div>

        <div className="field search">
          <svg className="search-ico" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
            <circle cx="11" cy="11" r="7" /><line x1="21" y1="21" x2="16.7" y2="16.7" />
          </svg>
          <input
            className="input input-search"
            placeholder="Buscar cliente…"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
          />
        </div>

        <button className="btn btn-ghost" style={{ width: "100%", justifyContent: "center" }} onClick={() => setNovoClienteAberto(true)}>
          + Cliente novo
        </button>

        <div className="filtro-grupo">
          <span className="filtro-titulo">Faixa RFM</span>
          <div className="medais">
            {FAIXAS.map((f) => {
              const k = FXKEY[f];
              const total = filtrados.length || 1;
              const share = Math.round((100 * contagem[f]) / total);
              return (
                <button
                  key={f}
                  className={"medal medal-" + k + (faixasOn[f] ? "" : " off")}
                  onClick={() => setFaixasOn((s) => ({ ...s, [f]: !s[f] }))}
                  aria-pressed={faixasOn[f]}
                >
                  <span className={"coin coin-" + k} />
                  <span className="medal-body">
                    <span className="medal-top">
                      <span className="medal-name">{f}</span>
                      <span className="medal-count">{num(contagem[f])}</span>
                    </span>
                    <span className="medal-bar"><i className={"fill-" + k} style={{ width: share + "%" }} /></span>
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        <button
          className={"risco-card" + (soRisco ? " on" : "")}
          onClick={() => setSoRisco((v) => !v)}
          aria-pressed={soRisco}
        >
          <span className="risco-pulse" />
          <span className="risco-body">
            <span className="risco-label">Só clientes em risco</span>
            <span className="risco-sub">contas grandes esfriando</span>
          </span>
          <b className="risco-count">{num(contagem.risco)}</b>
        </button>

        <div className="filtro-grupo">
          <span className="filtro-titulo">Cidade</span>
          <select className="input" value={cidade} onChange={(e) => setCidade(e.target.value)}>
            {cidades.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </div>

        <label className="ficha-radio" style={{ fontSize: 13 }}>
          <input
            type="checkbox"
            checked={incluirInativos}
            onChange={(e) => setIncluirInativos(e.target.checked)}
          />
          Considerar inativos
        </label>

        {/* card do cliente selecionado */}
        {sel && (
          <div className="cliente-card">
            <div className="stat-top">
              <span className={"chip " + FAIXA_CHIP[sel.faixa]}>
                <span className={"dot " + FAIXA_DOT[sel.faixa]} /> {sel.faixa}
              </span>
              {sel.emRisco && <span className="chip chip-risk"><span className="dot dot-risk" /> Em risco</span>}
              {sel.status === "inativo" && <span className="chip chip-inativo">Inativo</span>}
            </div>
            <h4 style={{ marginTop: 12, fontSize: 16 }}>{sel.nome}</h4>
            <p className="muted" style={{ fontSize: 13, marginTop: 4 }}>
              {sel.endereco}{sel.bairro ? `, ${sel.bairro}` : ""}<br />
              {sel.cidade}/{sel.uf}
            </p>
            <div className="kv">
              <div><span>Faturamento</span><b>{brl(sel.fat)} {sel.temPromessaPendente && <span title="Tem promessa pendente">🎁</span>}</b></div>
              <div><span>Compras</span><b>{num(sel.compras)}</b></div>
              <div><span>Ticket médio</span><b>{brl(sel.ticket)}</b></div>
              <div><span>Última compra</span><b>{recenciaTexto(sel.recencia)}</b></div>
              <div><span>Cadência</span><b>{sel.cadencia ? `a cada ${sel.cadencia} dias` : "—"}</b></div>
              {sel.porte && <div><span>Porte</span><b>{sel.porte}</b></div>}
              <div><span>Score RFM</span><b>{sel.score} <small className="faint">(R{sel.R} F{sel.F} M{sel.M})</small></b></div>
            </div>
            <button
              className="btn btn-primary"
              style={{ width: "100%", justifyContent: "center", marginTop: 12 }}
              onClick={() => setFichaAberta(true)}
            >
              Ver ficha completa
            </button>
          </div>
        )}
      </aside>

      {fichaAberta && sel && (
        <FichaCliente
          cliente={sel}
          aoFechar={() => setFichaAberta(false)}
          aoAtualizar={aplicarAtualizacao}
          visitaPendente={visitaPendente}
          aoIniciarVisita={aoIniciarVisita}
          aoFinalizarVisita={aoFinalizarVisita}
          aoCancelarVisita={aoCancelarVisita}
          usuario={usuario}
        />
      )}

      {/* ---------- MAPA ---------- */}
      <div className="mapa-wrap">
        <MapContainer
          center={[-25.095, -50.16]}
          zoom={12}
          preferCanvas
          style={{ height: "100%", width: "100%" }}
        >
          <TileLayer
            url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
            attribution='&copy; OpenStreetMap &copy; CARTO'
            subdomains="abcd"
          />
          <MapAutoSize />
          <FitBounds pontos={filtrados} />
          {filtrados.map((d) => (
            <CircleMarker
              key={d.id}
              center={[d.lat, d.lng]}
              radius={raio(d.faixa)}
              pathOptions={{
                color: d.emRisco ? "#e8543f" : "#ffffff",
                weight: d.emRisco ? 2 : 1.2,
                fillColor: d.status === "inativo" ? "#9aa0a6" : FAIXA_COR[d.faixa],
                fillOpacity: d.status === "inativo" ? 0.5 : 0.92,
              }}
              eventHandlers={{ click: () => { setSel(d); setModoMobile("painel"); } }}
            >
              <Popup>
                <b>{d.nome}</b>
                <br />
                {d.status === "inativo" ? "Inativo · " : ""}{d.faixa}{d.emRisco ? " · em risco" : ""} · {brl(d.fat)}
              </Popup>
            </CircleMarker>
          ))}
        </MapContainer>
      </div>

      {novoClienteAberto && (
        <NovoClienteModal
          aoFechar={() => setNovoClienteAberto(false)}
          aoCriado={(novo) => { aoAtualizarCliente(novo); setSel(novo); }}
        />
      )}
    </div>
  );
}
